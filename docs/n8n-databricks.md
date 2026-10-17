# n8n → Databricks Gold access

Connecting the self-hosted n8n orchestration layer to the Databricks medallion
architecture without building (or exposing) a custom public API in front of
Databricks. n8n's built-in **Databricks** node drives the SQL Statement
Execution API directly, and Gold-table-only access is enforced by a
least-privileged Databricks service principal at the Unity Catalog layer.

## Architecture

```
n8n (self-hosted Docker)
      │  native "Databricks" node  (Databricks SQL → Execute Query)
      │  → Databricks SQL Statement Execution API  (HTTPS + bearer/OAuth2)
      ▼
Databricks SQL Warehouse
      ▼
Unity Catalog: health_and_habit_guardian.gold
   daily_health · weekly_trends · risk_flags   ← only tables the identity sees
```

- n8n never holds admin credentials. The Databricks credential is scoped to a
  dedicated service principal (`n8n-gold-reader`) whose only data permission is
  `SELECT` on the three Gold tables. Even an arbitrary `SELECT` cannot touch
  Bronze or Silver because the principal has no grants there.
- No custom public endpoint fronts Databricks — n8n reaches Databricks's own API
  directly over HTTPS with a token-scoped identity.
- The Databricks node is `usableAsTool: true`, so it can be exposed as a tool to
  the LM Studio agent inside an n8n AI Agent workflow without extra plumbing.

## What to set up (your end)

### 1. Databricks account console

Create a dedicated service principal:

1. Account console → User management → Service principals → Add
   `n8n-gold-reader` → add it to this workspace.
2. Grant the **Databricks SQL** access entitlement to `n8n-gold-reader`.
3. Secrets tab → Generate secret (OAuth2 M2M). Copy **Client ID** and **Secret**
   (shown once). Use a Personal Access Token instead if you prefer the simpler
   fallback.

### 2. Unity Catalog grants (Databricks SQL editor / notebook)

Run `databricks/sql/n8n_grants.sql` as a metastore admin:

```sql
%run ./databricks/sql/n8n_grants.sql
```

This grants `USE CATALOG`, `USE SCHEMA` on `gold`, and `SELECT` on
`gold.daily_health`, `gold.weekly_trends`, `gold.risk_flags` — and nothing else.

### 3. Warehouse permissions

Grant `n8n-gold-reader` **CAN USE** on a SQL warehouse. For a zero-budget project,
reuse your existing warehouse (the one behind `DATABRICKS_HTTP_PATH` in `.env`)
with **auto-stop on idle** enabled rather than provisioning Serverless compute,
since every warehouse minute is billed.

### 4. n8n credential

In n8n, create a **Databricks credential**:
- Host: your workspace URL (e.g. `https://dbc-....cloud.databricks.com`)
- Authentication: **OAuth2** → Grant Type: Client Credentials (Service Principal)
  → Client ID + Secret from step 1.
  - Fallback: **Access Token** → paste a PAT.

### 5. n8n workflow

Add the **Databricks node** → Databricks SQL → **Execute Query**. Configure:
- Warehouse: the SQL warehouse from step 3.
- Query: any `SELECT` against the gold schema, e.g.

```sql
SELECT user_id, date, sleep_score, activity_score, recovery_score
FROM health_and_habit_guardian.gold.daily_health
WHERE user_id = 'u1'
ORDER BY date DESC
LIMIT 14;
```

The node submits via `POST /api/2.0/sql/statements` (`warehouse_id`, `statement`,
`wait_timeout: 50s`, `on_wait_timeout: CONTINUE`), polls until `SUCCEEDED`, and
reassembles result chunks into rows — no polling logic needed in your workflow.

## Verification

Positive test (should return rows):

```sql
SELECT * FROM health_and_habit_guardian.gold.daily_health LIMIT 5;
```

Negative test (should fail with a permissions error, proving Gold-only is
enforced at the engine, not by query-text inspection):

```sql
SELECT * FROM health_and_habit_guardian.silver.activity LIMIT 5;
-- expected: INVALID_PARAMETER_VALUE / permission denied
```

## Repo changes

- `databricks/sql/n8n_grants.sql` — versioned, re-runnable grant script so the
  Unity Catalog setup cannot drift (cf. `docs/pipeline.md` TODO on checked-in
  job/task definitions).
- This document (`docs/n8n-databricks.md`).

No Python changes are required for the native-node path; the existing
`agent/tools/dynamodb.py` helpers are unaffected.