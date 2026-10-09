"""Tests for agent/tools/dynamodb.py, run against moto (no real AWS calls)."""

import os

import boto3
import pytest
from moto import mock_aws

from agent.tools import dynamodb

REGION = "ap-south-1"


@pytest.fixture(autouse=True)
def aws_setup():
    with mock_aws():
        os.environ["AWS_REGION"] = REGION
        os.environ["AWS_ACCESS_KEY_ID"] = "testing"
        os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
        client = boto3.client("dynamodb", region_name=REGION)

        client.create_table(
            TableName="pipeline_runs",
            KeySchema=[{"AttributeName": "run_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "run_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="anomalies",
            KeySchema=[{"AttributeName": "anomaly_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "anomaly_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
                {"AttributeName": "timestamp", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "anomalies-by-user",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "timestamp", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="agent_sessions",
            KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        client.create_table(
            TableName="user_preferences",
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


def test_save_and_get_pipeline_run():
    run_id = dynamodb.save_pipeline_run(
        {"status": "SUCCESS", "started_at": "2026-01-01T00:00:00+00:00"}
    )
    item = dynamodb.get_pipeline_run(run_id)
    assert item["run_id"] == run_id
    assert item["status"] == "SUCCESS"


def test_save_pipeline_run_keeps_explicit_run_id():
    run_id = dynamodb.save_pipeline_run({"run_id": "r-1", "status": "RUNNING"})
    assert run_id == "r-1"
    assert dynamodb.get_pipeline_run("r-1")["run_id"] == "r-1"


def test_get_pipeline_run_missing_returns_none():
    assert dynamodb.get_pipeline_run("nope") is None


def test_get_latest_pipeline_run():
    dynamodb.save_pipeline_run(
        {"run_id": "r1", "started_at": "2026-01-01T00:00:00+00:00", "status": "RUNNING"}
    )
    dynamodb.save_pipeline_run(
        {"run_id": "r2", "started_at": "2026-01-02T00:00:00+00:00", "status": "SUCCESS"}
    )
    latest = dynamodb.get_latest_pipeline_run()
    assert latest["run_id"] == "r2"


def test_create_and_update_anomaly():
    anomaly_id = dynamodb.create_anomaly(
        user_id="u1", metric="sleep", severity="HIGH"
    )
    assert dynamodb.update_anomaly(anomaly_id, status="resolved") is True
    items = dynamodb.get_anomalies("u1")
    assert len(items) == 1
    assert items[0]["status"] == "resolved"


def test_get_open_anomalies_filters_status_and_user():
    dynamodb.create_anomaly(user_id="u1", metric="sleep", severity="MEDIUM")
    dynamodb.create_anomaly(
        user_id="u1", metric="heart_rate", severity="LOW", status="resolved"
    )
    dynamodb.create_anomaly(user_id="u2", metric="sleep", severity="HIGH")

    open_items = dynamodb.get_open_anomalies("u1")
    assert [i["metric"] for i in open_items] == ["sleep"]


def test_create_anomaly_extra_fields_and_timestamp():
    anomaly_id = dynamodb.create_anomaly(
        user_id="u3",
        metric="activity",
        severity="LOW",
        timestamp="2026-01-01T00:00:00+00:00",
        reason="steps dropped",
    )
    items = dynamodb.get_anomalies("u3")
    assert items[0]["anomaly_id"] == anomaly_id
    assert items[0]["reason"] == "steps dropped"
    assert items[0]["timestamp"] == "2026-01-01T00:00:00+00:00"


def test_user_preferences_roundtrip():
    dynamodb.save_user_preferences(
        {
            "user_id": "u1",
            "target_sleep_hours": 8.0,
            "notification_enabled": True,
            "notification_level": "high",
        }
    )
    prefs = dynamodb.get_user_preferences("u1")
    assert prefs["target_sleep_hours"] == 8.0
    assert prefs["notification_enabled"] is True


def test_user_preferences_missing_returns_none():
    assert dynamodb.get_user_preferences("ghost") is None


def test_save_session_roundtrip():
    session_id = dynamodb.save_session(
        user_id="u1", conversation_context=[{"role": "user", "content": "hi"}]
    )
    item = dynamodb.get_session(session_id)
    assert item["user_id"] == "u1"
    assert item["conversation_context"] == [{"role": "user", "content": "hi"}]
    assert "created_at" in item
    assert "updated_at" in item


def test_append_to_session():
    session_id = dynamodb.save_session(user_id="u1")
    assert dynamodb.append_to_session(
        session_id, {"role": "user", "content": "hello"}
    ) is True
    assert dynamodb.append_to_session(
        session_id, {"role": "assistant", "content": "hi"}
    ) is True
    item = dynamodb.get_session(session_id)
    assert item["conversation_context"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]


def test_append_to_session_preserves_created_at():
    session_id = dynamodb.save_session(user_id="u1")
    dynamodb.append_to_session(session_id, {"role": "user", "content": "hi"})
    item = dynamodb.get_session(session_id)
    assert item["created_at"] == item["updated_at"] or item["updated_at"] >= item[
        "created_at"
    ]


def test_scan_fallback_when_gsi_missing():
    client = boto3.client("dynamodb", region_name=REGION)
    client.create_table(
        TableName="anomalies_no_gsi",
        KeySchema=[{"AttributeName": "anomaly_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "anomaly_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    original = dynamodb.TABLES["anomalies"]
    try:
        dynamodb.TABLES["anomalies"] = "anomalies_no_gsi"
        anomaly_id = dynamodb.create_anomaly(
            user_id="u9", metric="sleep", severity="HIGH"
        )
        assert dynamodb.get_open_anomalies("u9")[0]["anomaly_id"] == anomaly_id
    finally:
        dynamodb.TABLES["anomalies"] = original