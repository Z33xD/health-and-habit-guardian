"""Strands Agent tool definitions.

Each tool wraps a helper function from dynamodb.py or databricks.py.
The agent calls these — it never touches boto3 or SQL directly.
"""

from strands import tool

from agent.databricks import get_quality_metrics as _get_quality_metrics
from agent.databricks import get_risk_flags as _get_risk_flags
from agent.dynamodb import (
    get_latest_pipeline_run,
    get_user_preferences as _get_user_preferences,
    update_anomaly_status as _update_anomaly_status,
)
from agent.notifications import send_notification as _send_notification


@tool
def get_pipeline_status() -> dict | None:
    """Check the status of the most recent Databricks pipeline run.

    Call this when asked about pipeline health, whether the nightly data
    job succeeded, data freshness, or if a quality check has run.

    Returns:
        The latest pipeline run with status, tables_affected, rows_processed,
        and error_message if present. Returns None if no runs exist.
    """
    return get_latest_pipeline_run()


@tool
def get_risk_flags(user_id: str, date: str | None = None) -> list[dict]:
    """Get health risk flags for a user.

    Call this when asked about a user's current risks, alerts, or anything
    the user should be aware of about their health.

    Args:
        user_id: The user identifier.
        date: Optional date (YYYY-MM-DD) to filter flags for a specific day.

    Returns:
        List of risk flags, each with risk_type, severity, reason, and
        recommended_action. Empty list if no risks.
    """
    return _get_risk_flags(user_id, date)


@tool
def get_quality_metrics(table_name: str | None = None) -> list[dict]:
    """Check data-quality metrics from the pipeline.

    Call this when asked about data quality, failed quality checks, or
    whether the ingested data is trustworthy.

    Args:
        table_name: Optional filter for a specific table
            ('activity', 'heart_rate', 'sleep').

    Returns:
        Most recent quality summary rows with tables, valid/invalid row
        counts, and quality_status (PASS / WARNING / FAIL / EMPTY).
    """
    return _get_quality_metrics(table_name)


@tool
def update_anomaly_status(anomaly_id: str, status: str) -> bool:
    """Change the status of an anomaly record.

    Call this when an anomaly has been investigated or resolved.

    Args:
        anomaly_id: The anomaly's identifier.
        status: The new status — 'open' or 'resolved'.

    Returns:
        True if the update succeeded.
    """
    return _update_anomaly_status(anomaly_id, status)


@tool
def get_user_preferences(user_id: str) -> dict | None:
    """Get a user's notification and health preferences.

    Call this before deciding to send notifications, or when a user asks
    about their goals, targets, or quiet hours.

    Args:
        user_id: The user identifier.

    Returns:
        User preferences (sleep target, activity goal, notification
        channel, quiet hours). None if the user has no preferences.
    """
    return _get_user_preferences(user_id)


@tool
def send_notification(user_id: str, message: str) -> bool:
    """Send a notification to a user.

    Call this when the agent decides a user should be alerted about a risk
    flag, anomaly, or pipeline issue. Respects the user's quiet hours and
    notification preferences.

    Args:
        user_id: The user to notify.
        message: Short, actionable notification text.

    Returns:
        True if the notification was sent, False if suppressed.
    """
    return _send_notification(user_id, message)