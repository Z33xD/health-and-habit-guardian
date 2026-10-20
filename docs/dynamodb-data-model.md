# Design for the DynamoDB tables

DynamoDB is intended to be used as the agent's memory and logging layer. They are designed to have considered reliable idempotency, notification cooldowns, and retries.

---

## `pipeline_runs`

| Attribute | Purpose |
| --------- | ------- |
| `run_id` (partition key) | Unique pipeline executions |
| `status` | RUNNING, SUCCESS, FAILED |
| `started_at`, `ended_at` | Execution timing |
| `tables_affected` | Gold tables updated on Databricks |
| `quality_summary` | Validation Results |

---

## `anomalies`

| Attribute | Purpose |
| --------- | ------- |
| `anomaly_id` (partition key) | Stable, deterministic signal ID |
| `user_id` | Owner of the signal |
| `metric` | Sleep, resting HR, activity, recovery, etc. |
| `severity` | LOW, MEDIUM, HIGH, or CRITICAL |
| `timestamp` | Time the signal was evaluated or observed |
| `status` | DETECTED, NOTIFIED, ACKNOWLEDGED, RESOLVED, SUPPRESSED | 
| `last_notified_at` | Last notification timestamp |
| `cooldown_until` | Earliest time another notification may be sent |
| `source_date` | Date of the underlying Gold record | 
| `reason` | Deterministic explanation from Gold/rules |
| `recommended_action` | Approved action or advice | 
| `updated_at` | Last state change |

> Here, a stable ID like `user_id#risk_type#source_date` can be used.

---

## `agent_session`

| Attribute | Purpose |
| --------- | ------- |
| `session_id` (partition key) | Conversation / Session ID |
| `user_id` | Owner |
| `created_at`, `updated_at` | Session timing |
| `conversation_context` | Minimal context needed for the conversation |

---

## `user_preferences`

| Attribute | Purpose |
| --------- | ------- |
| `user_id` (partition key) | User identifier |
| `target_sleep_hours` | Personalised sleep goal |
| `notifications_enabled` | Master notification switch |
| `notification_level` | Preferred notification intensity |

---

## `agent_runs`

| Attribute | Purpose |
| --------- | ------- |
| `run_id` (partition key) | Unique n8n execution |
| `started_at`, `ended_at | Execution timing |
| `status` | RUNNING, SUCCESS, PARTIAL, FAILED |
| `users_evaluated` | Number evaluated |
| `signals_found` | Number of actionable signals |
| `notifications_sent` | Number sent | 
| `notifications_suppressed` | Number suppressed |
| `error_summary` | Safe diagnostic information |

---