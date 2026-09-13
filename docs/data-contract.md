# Data Contract — Silver Layer

Catalog: `health_and_habit_guardian` (Unity Catalog, managed Delta).

This contract describes the Silver tables produced by the transform notebooks under
`databricks/notebooks/silver/`, the idempotent upsert behaviour, the timezone
convention, and how late-arriving data is handled.

## Conventions

### 1. Timezones

- All event timestamps — `timestamp`, `sleep_start`, `sleep_end` — are stored in
  **UTC**. Source CSV timestamps carry a `Z` (UTC) suffix (e.g.
  `2026-07-31T21:36:00.000Z`) and are written to Bronze as-is.
- Each Silver transform pins the Spark session to UTC
  (`spark.conf.set("spark.sql.session.timeZone", "UTC")`) so that
  `_processed_at` (`current_timestamp()`) and any timestamp casts are
  consistently emitted in UTC.
- `date` columns are **event calendar dates** as reported by the source, not
  derived from ingestion time.
- Downstream (Gold) consumers that need local time should convert UTC using a
  per-user `source_timezone` value. The synthetic seed data does not record one
  per user, so none is emitted by Bronze/Silver today.

### 2. Ingestion vs. event time (late-arriving data)

There are three distinct time columns:

| Column | Meaning | Written by |
|---|---|---|
| `date` / `timestamp` | Event date / event timestamp (UTC) | Bronze → Silver |
| `_ingested_at` | When the row entered Bronze (UTC) | Bronze |
| `_processed_at` | When the row was transformed into Silver (UTC) | Silver |

Records may arrive after their event date (wearables sync late). The Silver
write path treats this as a first-class case:

- The **business key** (below) is the only identity used for the upsert.
- Within a single batch, when multiple rows share a business key, only the row
  with the **latest `_ingested_at`** is written to Silver (row_number over the
  key ordered by `_ingested_at` descending).
- Quarantine tables keep **every** invalid row, including duplicates.

### 3. Write semantics

Every Silver table is written with an idempotent Delta `MERGE`:

```sql
CREATE TABLE IF NOT EXISTS <catalog>.silver.<table>
USING DELTA
AS SELECT * FROM <updates_view> WHERE 1 = 0;

MERGE INTO <catalog>.silver.<table> AS target
USING (
    SELECT <cols>
    FROM (
        SELECT *,
               ROW_NUMBER() OVER (
                   PARTITION BY <business key cols>
                   ORDER BY _ingested_at DESC NULLS LAST
               ) AS _rn
        FROM <updates_view>
    )
    WHERE _rn = 1
) AS source
ON <business key match>
WHEN MATCHED THEN UPDATE SET *
WHEN NOT MATCHED THEN INSERT *;
```

The `USING` clause deduplicates the source by the business key (latest
`_ingested_at` wins) so the upsert cannot fail with
`DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE`, no matter what the
upstream batch contains.

Consequences:

- Re-running a notebook is safe (idempotent upsert, no duplicates).
- Late-arriving rows for an existing key update the Silver row in place.
- An empty valid batch **does not truncate** the table (this is a behavioural
  change vs. the previous `mode("overwrite")` write).

> Migration note: tables created by the earlier `mode("overwrite")` runs may
> already contain duplicate business keys (they were written without any
> dedup). Since Silver is fully derivable from Bronze, the clean way to migrate
> is to `DELETE` all rows from each Silver table and re-run the transform
> notebooks once; the `MERGE` will repopulate them with one row per key.

Master data and column lineage live in the notebooks; the schema fragments
below are the contractual surface.

## Tables

### `silver.activity`

Business key (merge/upsert): `(user_id, date)`

| Column | Type | Notes |
|---|---|---|
| `user_id` | string | not null for valid rows |
| `date` | date | event date |
| `steps` | int | |
| `active_minutes` | int | |
| `calories_burned` | int | |
| `resting_hr` | int | |
| `missing_required` | boolean | diagnostic: null `user_id`/`date` |
| `invalid_steps` | boolean | diagnostic |
| `invalid_active_minutes` | boolean | diagnostic |
| `invalid_calories` | boolean | diagnostic |
| `invalid_resting_hr` | boolean | diagnostic |
| `_quality_status` | string | `VALID` / `INVALID` |
| `_processed_at` | timestamp | UTC |
| `_ingested_at` | timestamp | UTC |
| `_source_file` | string | |

### `silver.heart_rate`

Business key (merge/upsert): `(user_id, timestamp, source)`

| Column | Type | Notes |
|---|---|---|
| `user_id` | string | not null for valid rows |
| `timestamp` | timestamp | UTC |
| `heart_rate_bpm` | int | |
| `activity_state` | string | one of `resting`, `walking`, `running`, `cycling`, `sleeping`, `unknown` |
| `source` | string | device/source identifier |
| `_invalid_activity_state` | boolean | diagnostic; feeds `_quality_status` |
| `_quality_status` | string | `VALID` / `INVALID` |
| `_processed_at` | timestamp | UTC |
| `_ingested_at` | timestamp | UTC |
| `_source_file` | string | |

### `silver.sleep`

Business key (merge/upsert): `(user_id, date)`

| Column | Type | Notes |
|---|---|---|
| `user_id` | string | not null for valid rows |
| `date` | date | event date |
| `sleep_start`, `sleep_end` | timestamp | UTC; `sleep_end > sleep_start` for valid rows |
| `sleep_duration_hours` | float | |
| `deep_sleep_hours` | float | |
| `light_sleep_hours` | float | |
| `rem_sleep_hours` | float | |
| `awake_hours` | float | |
| `awakenings` | int | |
| `sleep_stage_total` | float | deep + light + rem (diagnostic) |
| `_stage_duration_mismatch` | boolean | diagnostic; feeds `_quality_status` |
| `time_in_bed_hours` | float | `(sleep_end - sleep_start) / 3600` |
| `sleep_efficiency` | float | nullable; `sleep_duration / time_in_bed` |
| `_invalid_efficiency` | boolean | diagnostic |
| `missing_required`, `invalid_sleep_time`, `invalid_sleep_duration`, `invalid_deep_sleep`, `invalid_light_sleep`, `invalid_rem_sleep`, `invalid_awake_hours`, `invalid_awakenings` | boolean | diagnostic; feed `_quality_status` |
| `_quality_status` | string | `VALID` / `INVALID` |
| `_processed_at` | timestamp | UTC |
| `_ingested_at` | timestamp | UTC |
| `_source_file` | string | |

### `silver.quarantine_activity` / `quarantine_heart_rate` / `quarantine_sleep`

Same schema as the corresponding Silver table (all flags computed), but
append-only and containing only rows flagged `INVALID`. Quarantine writes use
`mode("append")` and are **not** deduplicated — every invalid row is preserved.

### `silver.data_quality`

Append-only history of one row per table per run. Produced by
`00_quality_utils.ipynb` (`write_quality_summary`) invoked at the end of each
transform notebook.

| Column | Type | Notes |
|---|---|---|
| `run_id` | string | Databricks job run id, or random uuid outside a job |
| `table_name` | string | `activity`, `heart_rate`, `sleep` |
| `run_timestamp` | timestamp | UTC |
| `total_rows` | long | rows evaluated (pre-dedup batch) |
| `valid_rows` | long | |
| `invalid_rows` | long | |
| `null_user_ids` | long | |
| `duplicate_rows` | long | rows beyond the first per business key in the batch |
| `min_date` / `max_date` | date | from `date` (or `timestamp` for heart rate) |
| `quality_status` | string | `PASS` if no invalid rows; `WARNING` if some invalid but below threshold; `FAIL` if any null `user_id` or invalid ratio > 5%; `EMPTY` if `total_rows = 0` |

## Data-quality thresholds

- `invalid_threshold = 0.05` (invalid ratio above this fails the run).
- Any null `user_id` fails the run regardless of ratio.

## Notebook entry points

| Notebook | Table | Business key |
|---|---|---|
| `01_transform_activity.ipynb` | `silver.activity` | `(user_id, date)` |
| `02_transform_heart_rate.ipynb` | `silver.heart_rate` | `(user_id, timestamp, source)` |
| `03_transform_sleep.ipynb` | `silver.sleep` | `(user_id, date)` |
| `00_quality_utils.ipynb` | shared helper (`%run`'d by the transforms) | — |