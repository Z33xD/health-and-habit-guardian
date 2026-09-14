"""DynamoDB helper functions.

Thin wrapper so the agent never touches boto3 directly.
All functions are stateless — each call creates its own resource.
"""

import os

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()

TABLES = {
    "pipeline_runs": os.getenv("DYNAMODB_PIPELINE_TABLE", "pipeline_runs"),
    "anomalies": os.getenv("DYNAMODB_ANOMALY_TABLE", "anomalies"),
    "agent_sessions": os.getenv("DYNAMODB_AGENT_SESSION_TABLE", "agent_sessions"),
    "user_preferences": os.getenv("DYNAMODB_USER_PREFS_TABLE", "user_preferences"),
}


def _get_resource():
    return boto3.resource("dynamodb", region_name=os.getenv("AWS_REGION", "ap-south-1"))


def _get_table(table_name: str):
    return _get_resource().Table(table_name)


# ── Pipeline Runs ────────────────────────────────────────────────────────────

def get_pipeline_status(run_id: str) -> dict | None:
    try:
        resp = _get_table(TABLES["pipeline_runs"]).get_item(Key={"run_id": run_id})
        return resp.get("Item")
    except ClientError:
        return None


def save_pipeline_run(data: dict) -> bool:
    try:
        _get_table(TABLES["pipeline_runs"]).put_item(Item=data)
        return True
    except ClientError:
        return False


# ── Anomalies ────────────────────────────────────────────────────────────────

def get_anomalies(user_id: str, status: str | None = None) -> list[dict]:
    """Query anomalies by user_id.

    The anomalies table uses anomaly_id as partition key,
    so we scan with a filter on user_id (and optionally status).
    """
    table = _get_table(TABLES["anomalies"])
    scan_kwargs = {
        "FilterExpression": "user_id = :uid",
        "ExpressionAttributeValues": {":uid": user_id},
    }
    if status:
        scan_kwargs["FilterExpression"] += " AND #s = :st"
        scan_kwargs["ExpressionAttributeValues"][":st"] = status
        scan_kwargs["ExpressionAttributeNames"] = {"#s": "status"}

    items = []
    try:
        resp = table.scan(**scan_kwargs)
        items.extend(resp.get("Items", []))
        while "LastEvaluatedKey" in resp:
            resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **scan_kwargs)
            items.extend(resp.get("Items", []))
    except ClientError:
        pass
    return items


def create_anomaly(data: dict) -> bool:
    try:
        _get_table(TABLES["anomalies"]).put_item(Item=data)
        return True
    except ClientError:
        return False


def update_anomaly_status(anomaly_id: str, status: str) -> bool:
    try:
        _get_table(TABLES["anomalies"]).update_item(
            Key={"anomaly_id": anomaly_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": status},
        )
        return True
    except ClientError:
        return False


# ── User Preferences ─────────────────────────────────────────────────────────

def get_user_preferences(user_id: str) -> dict | None:
    try:
        resp = _get_table(TABLES["user_preferences"]).get_item(Key={"user_id": user_id})
        return resp.get("Item")
    except ClientError:
        return None


def save_user_preferences(data: dict) -> bool:
    try:
        _get_table(TABLES["user_preferences"]).put_item(Item=data)
        return True
    except ClientError:
        return False


# ── Agent Sessions ───────────────────────────────────────────────────────────

def get_agent_session(session_id: str) -> dict | None:
    try:
        resp = _get_table(TABLES["agent_sessions"]).get_item(Key={"session_id": session_id})
        return resp.get("Item")
    except ClientError:
        return None


def save_agent_session(data: dict) -> bool:
    try:
        _get_table(TABLES["agent_sessions"]).put_item(Item=data)
        return True
    except ClientError:
        return False
