# Pipeline — Notebook Structure & Job Flow

How the notebooks under `databricks/notebooks/{bronze,silver,gold}` fit together,
and the order the Databricks job runs them in.

Catalog: `health_and_habit_guardian` (Unity Catalog, managed Delta) with one
schema per layer: `bronze`, `silver`, `gold`.

## Job flow

```text
                    START
                      │
                      ▼
             ┌────────────────┐
             │ Bronze Ingest  │
             └───────┬────────┘
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
     Activity     HR          Sleep
         │           │           │
         └───────────┼───────────┘
                     ▼
             Silver Transform
                     │
         ┌───────────┼───────────┐
         ▼           ▼           ▼
     Activity     HR          Sleep
         │           │           │
         └───────────┼───────────┘
                     ▼
              Data Quality
                     │
                     ▼
             Gold Daily Health
                     │
                     ▼
             Gold Weekly Trends
                     │
                     ▼
               Risk Flags
                     │
                     ▼
                    END
```

Suggested job tasks and dependencies (task → notebook):

| # | Task | Notebook | Depends on |
|---|------|----------|------------|
| 1 | `bronze_activity` | `bronze/01_ingest_activity` | — |
| 2 | `bronze_heart_rate` | `bronze/02_ingest_heart_rate` | — |
| 3 | `bronze_sleep` | `bronze/03_ingest_sleep` | — |
| 4 | `silver_activity` | `silver/01_transform_activity` | bronze tasks |
| 5 | `silver_heart_rate` | `silver/02_transform_heart_rate` | bronze tasks |
| 6 | `silver_sleep` | `silver/03_transform_sleep` | bronze tasks |
| 7 | `gold_daily_health` | `gold/01_build_daily_health` | all silver tasks |
| 8 | `gold_weekly_trends` | `gold/02_build_weekly_trends` | `gold_daily_health` |
| 9 | `risk_flags` | `gold/03_build_risk_flags` | `gold_daily_health` |

Tasks 1–3 and 4–6 fan out in parallel; everything from `gold_daily_health`
downwards is strictly sequential. Each Silver transform also writes its own
Data Quality row (see § Silver), so there is no separate quality task —
"Data Quality" in the diagram is the `write_quality_summary` step at the end
of each Silver notebook.

## Global conventions

- **UTC everywhere.** Every notebook pins
  `spark.conf.set("spark.sql.session.timeZone", "UTC")`. Event timestamps are
  stored in UTC; `date` columns are event calendar dates, not ingestion dates.
- **Two processing timestamps.** `_ingested_at` is stamped by Bronze when a row
  lands; `_processed_at` is stamped by Silver/Gold when a row is transformed.
  Together with the event `date`/`timestamp` they explain late-arriving data:
  a wearable syncing days late keeps its event date but gets a new
  `_ingested_at`, and Silver's dedup (`row_number` over the business key
  ordered by `_ingested_at DESC`) lets the late row win.
- **Bronze appends, Silver/Gold upsert.** Bronze notebooks use
  `mode("append")` (re-running one re-ingests). Silver and Gold notebooks use
  an idempotent Delta `MERGE` on the table's business key, so re-runs are safe
  and late data updates rows in place.

## Bronze — raw ingest (`notebooks/bronze/`)

One notebook per source. Each follows the same shape:

1. Read the seed CSV from S3 (`spark.read … .csv` with header + inferred schema).
2. Stamp `_ingested_at` (`current_timestamp()`) and `_source_file`
   (`_metadata.file_path`).
3. Append to the Bronze Delta table.
4. `%sql` verification cells: sample rows, `DESCRIBE HISTORY`, row counts,
   null counts, duplicate checks.

| Notebook | S3 source | Table | Grain |
|----------|-----------|-------|-------|
| `01_ingest_activity` | `…/raw/public-seed/activity/activity.csv` | `bronze.activity` | one row per user per day |
| `02_ingest_heart_rate` | `…/raw/public-seed/heart_rate/heart_rate.csv` | `bronze.heart_rate` | many rows per user per day (timestamped) |
| `03_ingest_sleep` | `…/raw/public-seed/sleep/sleep.csv` | `bronze.sleep` | one row per user per night |

## Silver — clean & validate (`notebooks/silver/`)

- `00_quality_utils.ipynb` — shared helper, pulled into each transform via
  `%run ./00_quality_utils`. Creates `silver.data_quality` and exposes
  `write_quality_summary(df, table_name, date_col, dedup_cols)`, which appends
  one row per table per run (`total/valid/invalid` counts, null user ids,
  duplicates, min/max date, `PASS` / `WARNING` / `FAIL` / `EMPTY`).
- Each transform (`01` activity, `02` heart_rate, `03` sleep) follows the same
  shape: canonical casts → diagnostic flag columns → `_quality_status`
  (`VALID`/`INVALID`) → `_processed_at` → dedup on the business key keeping
  the latest `_ingested_at` → append invalid rows to the quarantine table →
  `MERGE` valid rows into Silver → `write_quality_summary`.

| Notebook | Table | Business key | Quarantine table |
|----------|-------|--------------|------------------|
| `01_transform_activity` | `silver.activity` | `(user_id, date)` | `silver.quarantine_activity` |
| `02_transform_heart_rate` | `silver.heart_rate` | `(user_id, timestamp, source)` | `silver.quarantine_heart_rate` |
| `03_transform_sleep` | `silver.sleep` | `(user_id, date)` | `silver.quarantine_sleep` |

Notable per-table logic: heart-rate validates `heart_rate_bpm` range plus an
`activity_state` whitelist; sleep checks stage components sum to the reported
duration (±0.25h) and derives `time_in_bed_hours` and `sleep_efficiency`.
Column-level detail lives in `docs/data-contract.md`.

## Gold — modelled features (`notebooks/gold/`)

### `01_build_daily_health` → `gold.daily_health`

The most important Gold table. Grain: **one row per user per day**.

- Reads the three Silver tables (`VALID` rows only), aggregates activity
  (`sum`, robust to multi-record days) and heart-rate (`avg/min/max` per
  calendar date), takes sleep as-is, and `FULL OUTER` joins them so a day with
  only some sources present is kept.
- Adds `activity_missing` / `sleep_missing` / `heart_rate_missing` flags so
  consumers can tell "no data" apart from "bad night".
- Adds heuristic scores (0–100, **project-defined, not medical metrics**):
  `sleep_score` (70% duration + 30% efficiency), `activity_score` (step bands),
  `heart_rate_score` (resting-HR bands), `recovery_score` (0.5/0.3/0.2 weighted,
  renormalised over non-null components).
- Adds `sleep_debt_hours` (`max(0, target − sleep_hours)`), 7-day/28-day
  rolling windows, `steps_7d_avg`, `sleep_7d_avg`, `resting_hr_7d_avg`,
  `recovery_7d_avg`, and `activity_drop_pct` (7-day vs 28-day baseline).
- Two job parameters via widgets: `target_sleep_hours` (default 8.0),
  `step_goal` (default 8000, informational).
- `MERGE` on `(user_id, date)`.

> Notebook authoring note: cells execute top-to-bottom, so anything that
> consumes `recovery_score` (e.g. `recovery_7d_avg`) must live in a cell *after*
> the scores cell. A past `UNRESOLVED_COLUMN recovery_score` failure was caused
> by exactly this ordering issue.

### `02_build_weekly_trends` → `gold.weekly_trends`

Dashboard input. Grain: one row per user per calendar week (`week_start` =
Monday, UTC). Weekly averages of steps, active minutes, sleep, efficiency,
resting HR and recovery, summed `sleep_debt`, `days_observed`, plus
week-over-week `activity_change_pct` / `recovery_change_pct` via `lag()`.
`MERGE` on `(user_id, week_start)`.

### `03_build_risk_flags` → `gold.risk_flags`

Intervention signals for the future agent. Grain:
`(user_id, date, risk_type)`. Five heuristic rules over `gold.daily_health`,
`union`ed together — each emits `severity`, numeric `score`, human-readable
`reason`, and `recommended_action`, and each only fires when the underlying
data is present:

| `risk_type` | Fires when |
|-------------|------------|
| `SLEEP_DEBT` | 7-day rolling sleep debt ≥ 3.5h (HIGH ≥ 7h) |
| `LOW_SLEEP` | single night < 6h (HIGH < 5h) |
| `ACTIVITY_DROP` | 7-day steps down ≥ 30% vs 28-day baseline (HIGH ≥ 50%) |
| `ELEVATED_RESTING_HR` | resting HR ≥ 5 bpm above the user's 7-day average |
| `LOW_RECOVERY` | recovery score < 50 (HIGH < 35) |

`MERGE` on `(user_id, date, risk_type)`.

## Known issues / TODOs

1. **Delete the duplicate Bronze notebooks** (`02_heart_rate_activity`,
   `03_sleep_activity`) — double-ingest risk, see Bronze section.
2. **Heart-rate `activity_state` whitelist vs generator.** Silver only accepts
   `resting/walking/running/cycling/sleeping/unknown`, but
   `data/generate_synthetic_data.py` emits `sedentary` and `active`, which get
   quarantined — leaving Gold's `heart_rate_missing` true far too often. Fix by
   widening the whitelist or remapping generator states.
3. **`databricks/jobs/` is empty** (only `.gitkeep`) — the task graph above is
   currently defined in the Databricks UI. Consider checking in a Jobs-as-code
   definition so the flow in this doc can't drift from what's deployed.
