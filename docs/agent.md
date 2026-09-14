# Agent — Helper Layer & Strands Agent

How the autonomous agent for Health & Habit Guardian is structured, what it
can do today, and how to run it.

## Overview

The agent monitors the data pipeline (via DynamoDB run records), reads modelled
health features (Databricks gold layer), reasons about risk flags, and — in a
later phase — notifies users. It runs on a local model (`qwen2.5-coder-7b-instruct`)
served by **LM Studio** through the Strands Agents SDK.

Everything is layered so the agent's tools never touch AWS SDK calls or SQL
directly:

```text
Strands Agent (agent.py)
        │  calls
        ▼
   Tools (tools.py)        ← @tool functions, LLM-callable
        │  wraps
        ▼
 Helper functions
  ├── dynamodb.py      ← boto3 wrapper (pipeline_runs, anomalies, user_preferences, agent_sessions)
  ├── databricks.py    ← Databricks SQL connector (gold + silver.data_quality)
  ├── notifications.py ← notification service (console channel, quiet hours)
  └── memory.py        ← session memory backed by agent_sessions
```

The LLM only ever sees the tool layer (`tools.py`). It never knows about
DynamoDB table names, partition keys, SQL, or connection strings.

## Current status / roadmap

| Phase | Scope | Status |
|---|---|---|
| **1** | `get_pipeline_status`, `get_risk_flags`, `get_quality_metrics`, `update_anomaly_status`, `get_user_preferences` | ✅ Implemented & registered |
| **2** | `send_notification` | 🚧 Implemented in `tools.py`, **not yet registered** (one-line change in `agent.py`) |
| **3** (stretch) | `flag_or_quarantine` — composite tool that records an anomaly and notifies | 🔮 Planned |

## Directory structure

```text
agent/
├── __init__.py        # package marker
├── agent.py           # Strands Agent: LM Studio model + tool registration + REPL loop
├── tools.py           # @tool definitions the LLM can call
├── dynamodb.py        # boto3 wrappers over the 4 DynamoDB tables
├── databricks.py      # Databricks SQL helper over gold tables + silver.data_quality
├── notifications.py   # console notification service with quiet-hours gating
└── memory.py          # agent session persistence (agent_sessions table)
```

## Module reference

### `agent.py` — entry point

- Constructs `OpenAIModel` pointing at LM Studio's OpenAI-compatible endpoint
  (`LM_STUDIO_URL`), model `qwen2.5-coder-7b-instruct` (`LM_STUDIO_MODEL`),
  `temperature=0.3`, `max_tokens=1024`.
  - Uses **`strands.models.openai.OpenAIModel`**, *not* `OllamaModel` — LM Studio
    speaks the OpenAI `/v1` protocol, not Ollama's `/api/chat`.
  - `api_key` can be any non-empty value; LM Studio does not validate it.
- Registers exactly the Phase 1 tools in the `TOOLS` list.
- Runs an interactive REPL: prompts for `user_id`, starts a session, and for each
  message appends the exchange to session memory (`memory.py`).

```bash
python -m agent.agent
```

### `tools.py` — LLM-callable surface

Each function is decorated with Strands' `@tool`. The docstring **is** the
function schema description the model sees, so wording matters (when to call,
what args to pass).

| Tool | Backing helper | Purpose |
|---|---|---|
| `get_pipeline_status()` | `dynamodb.get_latest_pipeline_run` | Most recent pipeline run: status, tables affected, rows processed, error |
| `get_risk_flags(user_id, date?)` | `databricks.get_risk_flags` | Gold risk flags for a user (SLEEP_DEBT, LOW_SLEEP, …) |
| `get_quality_metrics(table_name?)` | `databricks.get_quality_metrics` | Latest `silver.data_quality` rows (PASS / WARNING / FAIL / EMPTY) |
| `update_anomaly_status(anomaly_id, status)` | `dynamodb.update_anomaly_status` | Mark an anomaly `open` / `resolved` |
| `get_user_preferences(user_id)` | `dynamodb.get_user_preferences` | User's targets, notification channel, quiet hours |
| `send_notification(user_id, message)` | `notifications.send_notification` | **Phase 2** — defined but unregistered |

To enable Phase 2, add `send_notification` to `TOOLS` in `agent/agent.py`.

### `dynamodb.py` — DynamoDB helper layer

Thin, stateless wrapper over `boto3`. No other module touches boto3. All write
functions return `bool` (success/failure); reads return `dict | None` or `list`.

Table names are configurable via env vars, defaulting to the physical names.

| Function | Table | Operation |
|---|---|---|
| `get_pipeline_status(run_id)` | `pipeline_runs` | `get_item` by `run_id` |
| `get_latest_pipeline_run()` | `pipeline_runs` | `scan`, picks latest `start_time` |
| `save_pipeline_run(data)` | `pipeline_runs` | `put_item` |
| `get_anomalies(user_id, status?)` | `anomalies` | `scan` + filter on `user_id` (paged) |
| `create_anomaly(data)` | `anomalies` | `put_item` |
| `update_anomaly_status(anomaly_id, status)` | `anomalies` | `update_item` on `status` |
| `get_user_preferences(user_id)` | `user_preferences` | `get_item` by `user_id` |
| `save_user_preferences(data)` | `user_preferences` | `put_item` |
| `get_agent_session(session_id)` | `agent_sessions` | `get_item` by `session_id` |
| `save_agent_session(data)` | `agent_sessions` | `put_item` |

### `databricks.py` — Databricks SQL helper layer

Connects with the `databricks-sql-connector` using `DATABRICKS_HOST`,
`DATABRICKS_HTTP_PATH`, `DATABRICKS_TOKEN`. Catalog is hard-coded to
`health_and_habit_guardian`. All queries are parameterised.

Intentionally **no arbitrary SQL execution** — the agent gets named, controlled
functions:

| Function | Table | Filters |
|---|---|---|
| `get_daily_health(user_id, date?, limit=30)` | `gold.daily_health` | `user_id`, optional `date` |
| `get_weekly_trends(user_id, weeks=4)` | `gold.weekly_trends` | `user_id` |
| `get_risk_flags(user_id, date?)` | `gold.risk_flags` | `user_id`, optional `date` |
| `get_quality_metrics(table_name?, limit=10)` | `silver.data_quality` | optional `table_name` (`activity` / `heart_rate` / `sleep`) |

### `notifications.py` — notification service

Phase 2 support, already plumbed:

- `is_quiet_hours(user_id)` — reads `quiet_hours_start` / `quiet_hours_end` (HH:MM),
  supports overnight ranges, compares against UTC now.
- `send_notification(user_id, message, channel?)` — bails if
  `notification_enabled=false` or during quiet hours; defaults to `console`
  (prints and logs).
- `send_anomaly_alert(anomaly)` — convenience wrapper formatting
  `[SEVERITY] metric: reason`.

### `memory.py` — session memory

DynamoDB-backed conversation persistence, used **inside the agent loop**, not
exposed as tools (keeps the tool surface small for the 7B model):

- `create_session(user_id)` → new `session_id` (uuid4) with empty history.
- `get_session(session_id)`.
- `append_to_session(session_id, role, content)` — appends a message to
  `conversation_history`, bumps `last_updated` and `last_action`.

## DynamoDB contract

| Table | Partition key | Notes |
|---|---|---|
| `pipeline_runs` | `run_id` | no sort key |
| `anomalies` | `anomaly_id` | queried by `user_id` via scan+filter (no GSI yet) |
| `agent_sessions` | `session_id` | hosts `conversation_history` |
| `user_preferences` | `user_id` | notification + target settings |

> `anomalies` and `agent_sessions` are scanned on `user_id`. For a larger
> dataset, add a GSI on `user_id` instead of scanning.

## Environment variables

`.env` (also mirrored in `.env.example`):

```dotenv
AWS_REGION=ap-south-1

DYNAMODB_PIPELINE_TABLE=
DYNAMODB_ANOMALY_TABLE=
DYNAMODB_AGENT_SESSION_TABLE=
DYNAMODB_USER_PREFS_TABLE=

DATABRICKS_HOST=
DATABRICKS_TOKEN=
DATABRICKS_HTTP_PATH=

LM_STUDIO_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=qwen2.5-coder-7b-instruct
```

`LM_STUDIO_MODEL` must match the model name loaded in LM Studio, and the URL's
`/v1` suffix is required (the SDK appends nothing).

## Setup

```bash
pip install -r requirements.txt
```

Key runtime deps: `strands-agents[openai]` (brings `openai`), `boto3`,
`databricks-sql-connector`, `python-dotenv`.

## Running

1. Start LM Studio, load `qwen2.5-coder-7b-instruct`, enable the local server on
   `localhost:1234`.
2. Fill in `.env` — DynamoDB table names, Databricks host/token/http path.
3. `python -m agent.agent`
4. Enter a `user_id`, then ask the agent questions (e.g. "what risks does my
   user have?", "did the pipeline succeed last night?").

## Design decisions

- **Tool count is small on purpose.** `qwen2.5-coder-7b-instruct` picks tools
  more reliably from 5–6 focused tools than a long list. Memory helpers and
  heavy convenience wrappers were removed from the tool surface.
- **LM Studio over Ollama.** The app runs against an OpenAI-compatible local
  server; `OllamaModel` only speaks Ollama's native protocol.
- **Specific queries over generic SQL.** The agent gets `get_risk_flags()`,
  not `query_gold_table(sql)` — controlled read-only access, no injection risk.
- **Tool → helper → SDK layering.** Swapping DynamoDB for another store, or
  Databricks for Lakehouse federation, only touches the helper files.
- **Boto3 on every call.** helpers create a fresh resource per call; fine for a
  hackathon, swap to a shared session/client if latency becomes an issue.