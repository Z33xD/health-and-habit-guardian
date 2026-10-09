"""DynamoDB helper layer for the Health & Habit Guardian agent.

Thin, stateless boto3 wrapper over the four agent tables. This is the only
module that touches DynamoDB, so callers never see table names, keys, or
query expressions.

Reads return ``None`` only when a key is not found. Real AWS failures
raise ``botocore.exceptions.ClientError`` so they are not mistaken for
"no data". Timestamps are ISO-8601 UTC strings and therefore sort
lexicographically, which keeps them GSI-safe as sort keys.
"""

import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

__all__ = [
    "append_to_session",
    "create_anomaly",
    "get_anomalies",
    "get_latest_pipeline_run",
    "get_open_anomalies",
    "get_pipeline_run",
    "get_session",
    "get_user_preferences",
    "save_pipeline_run",
    "save_session",
    "save_user_preferences",
    "update_anomaly",
]

TABLES = {
    "pipeline_runs": os.getenv("DYNAMODB_PIPELINE_TABLE", "pipeline_runs"),
    "anomalies": os.getenv("DYNAMODB_ANOMALY_TABLE", "anomalies"),
    "agent_sessions": os.getenv("DYNAMODB_AGENT_SESSION_TABLE", "agent_sessions"),
    "user_preferences": os.getenv("DYNAMODB_USER_PREFS_TABLE", "user_preferences"),
}

ANOMALY_USER_INDEX = os.getenv("DYNAMODB_ANOMALY_USER_INDEX", "anomalies-by-user")


def _resource():
    return boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION"))


def _table(name: str):
    return _resource().Table(name)


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _serialize(value):
    """Convert floats to Decimals so boto3 can write them."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {key: _serialize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_serialize(val) for val in value]
    return value


def _deserialize(value):
    """Convert Decimals back to native numbers for JSON-friendly reads."""
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, dict):
        return {key: _deserialize(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_deserialize(val) for val in value]
    return value


def _scan_all(table, **kwargs) -> list[dict]:
    """Page through a scan, applying any filter kwargs on every page."""
    items = []
    resp = table.scan(**kwargs)
    items.extend(resp.get("Items", []))
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


# ── pipeline_runs ────────────────────────────────────────────────────────────


def save_pipeline_run(data: dict) -> str:
    """Persist a pipeline run record, returning its ``run_id``."""
    run_id = data.get("run_id") or str(uuid.uuid4())
    data["run_id"] = run_id
    _table(TABLES["pipeline_runs"]).put_item(Item=_serialize(data))
    return run_id


def get_pipeline_run(run_id: str) -> dict | None:
    """Fetch a single pipeline run by ``run_id``."""
    resp = _table(TABLES["pipeline_runs"]).get_item(Key={"run_id": run_id})
    item = resp.get("Item")
    return _deserialize(item) if item else None


def get_latest_pipeline_run() -> dict | None:
    """Return the pipeline run with the most recent ``started_at``."""
    items = _scan_all(_table(TABLES["pipeline_runs"]))
    items = [_deserialize(item) for item in items]
    if not items:
        return None
    return max(items, key=lambda row: row.get("started_at", "") or "")


# ── anomalies ────────────────────────────────────────────────────────────────


def create_anomaly(
    user_id: str,
    metric: str,
    severity: str,
    *,
    timestamp: str | None = None,
    status: str = "open",
    anomaly_id: str | None = None,
    **extra,
) -> str:
    """Create an anomaly record and return its ``anomaly_id``."""
    record = {
        "anomaly_id": anomaly_id or str(uuid.uuid4()),
        "user_id": user_id,
        "metric": metric,
        "severity": severity,
        "timestamp": timestamp or _now_utc(),
        "status": status,
    }
    record.update(extra)
    _table(TABLES["anomalies"]).put_item(Item=_serialize(record))
    return record["anomaly_id"]


def update_anomaly(anomaly_id: str, **changes) -> bool:
    """Update the provided attributes on an anomaly record."""
    if not changes:
        return True
    names = {f"#a{i}": key for i, key in enumerate(changes)}
    values = {f":a{i}": _serialize(val) for i, val in enumerate(changes.values())}
    assignments = ", ".join(
        f"{name} = {value}" for name, value in zip(names, values)
    )
    _table(TABLES["anomalies"]).update_item(
        Key={"anomaly_id": anomaly_id},
        UpdateExpression=f"SET {assignments}",
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )
    return True


def get_open_anomalies(user_id: str, limit: int = 50) -> list[dict]:
    """Return a user's anomalies whose ``status`` is ``open``."""
    return get_anomalies(user_id, status="open", limit=limit)


def get_anomalies(
    user_id: str, status: str | None = None, limit: int = 50
) -> list[dict]:
    """Return a user's anomalies, optionally filtered by ``status``."""
    return _query_anomalies_by_user(
        _table(TABLES["anomalies"]), user_id, status, limit
    )


def _query_anomalies_by_user(table, user_id: str, status: str | None, limit: int):
    kwargs = {
        "KeyConditionExpression": "user_id = :uid",
        "ExpressionAttributeValues": {":uid": user_id},
        "Limit": limit,
    }
    if status is not None:
        kwargs["FilterExpression"] = "#s = :st"
        kwargs["ExpressionAttributeNames"] = {"#s": "status"}
        kwargs["ExpressionAttributeValues"][":st"] = status
    try:
        resp = table.query(IndexName=ANOMALY_USER_INDEX, **kwargs)
        return [_deserialize(item) for item in resp.get("Items", [])][:limit]
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceNotFoundException":
            raise
    return _scan_anomalies_by_user(table, user_id, status, limit)


def _scan_anomalies_by_user(table, user_id: str, status: str | None, limit: int):
    kwargs = {
        "FilterExpression": "user_id = :uid",
        "ExpressionAttributeValues": {":uid": user_id},
        "Limit": limit,
    }
    if status is not None:
        kwargs["FilterExpression"] += " AND #s = :st"
        kwargs["ExpressionAttributeNames"] = {"#s": "status"}
        kwargs["ExpressionAttributeValues"][":st"] = status
    items = _scan_all(table, **kwargs)
    return [_deserialize(item) for item in items][:limit]


# ── user_preferences ─────────────────────────────────────────────────────────


def get_user_preferences(user_id: str) -> dict | None:
    """Fetch a user's preference record, or ``None`` if it does not exist."""
    resp = _table(TABLES["user_preferences"]).get_item(Key={"user_id": user_id})
    item = resp.get("Item")
    return _deserialize(item) if item else None


def save_user_preferences(data: dict) -> bool:
    """Upsert a user preferences record."""
    _table(TABLES["user_preferences"]).put_item(Item=_serialize(data))
    return True


# ── agent_sessions ───────────────────────────────────────────────────────────


def save_session(
    session_id: str | None = None,
    user_id: str | None = None,
    conversation_context: list | None = None,
) -> str:
    """Persist a session (full overwrite), returning its ``session_id``."""
    now = _now_utc()
    record = {
        "session_id": session_id or str(uuid.uuid4()),
        "user_id": user_id,
        "conversation_context": conversation_context or [],
        "created_at": now,
        "updated_at": now,
    }
    _table(TABLES["agent_sessions"]).put_item(Item=_serialize(record))
    return record["session_id"]


def get_session(session_id: str) -> dict | None:
    """Fetch a session, or ``None`` if it does not exist."""
    resp = _table(TABLES["agent_sessions"]).get_item(Key={"session_id": session_id})
    item = resp.get("Item")
    return _deserialize(item) if item else None


def append_to_session(session_id: str, message: dict) -> bool:
    """Append one message to a session's ``conversation_context`` list."""
    _table(TABLES["agent_sessions"]).update_item(
        Key={"session_id": session_id},
        UpdateExpression=(
            "SET conversation_context = "
            "list_append(if_not_exists(conversation_context, :empty), :msg), "
            "updated_at = :now"
        ),
        ExpressionAttributeValues={
            ":empty": [],
            ":msg": _serialize([message]),
            ":now": _now_utc(),
        },
    )
    return True