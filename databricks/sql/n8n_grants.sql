-- n8n Databricks read-only grants
--
-- Applies least-privilege Unity Catalog permissions for the `n8n-gold-reader`
-- service principal so that n8n's native Databricks node can run arbitrary
-- SELECT queries against the Gold layer and nothing else.
--
-- Run as a metastore admin (or workspace admin with CATALOG MANAGE on the
-- catalog) in a Databricks SQL editor / notebook:
--
--     %sql
--     %run ./n8n_grants.sql
--
-- Re-running is safe: Unity Catalog treats repeat GRANTs as idempotent.
--
-- Pre-requisites (Databricks account console):
--   1. Create service principal `n8n-gold-reader` and add it to the workspace.
--   2. Grant the "Databricks SQL" access entitlement to the principal.
--   3. Generate an OAuth2 M2M secret (Client ID + Secret) for n8n's Databricks
--      credential, or use a Personal Access Token as a simpler fallback.

GRANT USE CATALOG   ON CATALOG  health_and_habit_guardian TO `n8n-gold-reader`;
GRANT USE SCHEMA    ON SCHEMA  health_and_habit_guardian.gold TO `n8n-gold-reader`;

GRANT SELECT ON TABLE health_and_habit_guardian.gold.daily_health   TO `n8n-gold-reader`;
GRANT SELECT ON TABLE health_and_habit_guardian.gold.weekly_trends  TO `n8n-gold-reader`;
GRANT SELECT ON TABLE health_and_habit_guardian.gold.risk_flags     TO `n8n-gold-reader`;

-- Intentional: no grants on bronze.*, silver.*, or any MODIFY/CREATE privilege.
-- Unity Catalog denies everything else by default, so arbitrary SQL from n8n
-- can only ever read these three Gold tables.
-- End of file
