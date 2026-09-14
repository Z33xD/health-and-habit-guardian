"""Strands Agent tool definitions.

Each tool wraps a helper function from dynamodb.py or databricks.py.
The agent calls these — it never touches boto3 or SQL directly.
"""

from strands import tool

from agent.databricks import get_daily_health, get_risk_flags, get_weekly_trends
from agent.dynamodb import (
    create_anomaly,
    get_anomalies,
    get_pipeline_status,
    get_user_preferences,
    save_agent_session,
    update_anomaly_status,
)
from agent.memory import append_to_session, create_session, get_session
from agent.notifications import send_anomaly_alert, send_notification


@tool
def check_pipeline_status(run_id: str) -> dict | None:
    """Check the status of a Databricks pipeline run.

    Args:
        run_id: The pipeline run identifier.

    Returns:
        Pipeline run details including status, tables affected, and any errors,
        or None if the run is not found.
    """
    return get_pipeline_status(run_id)


@tool
def query_user_health(user_id: str, date: str | None = None) -> dict:
    """Get a user's daily health summary from the gold layer.

    Args:
        user_id: The user identifier.
        date: Optional date (YYYY-MM-DD). Returns the most recent day if omitted.

    Returns:
        Daily health data including scores, sleep, activity, and heart-rate metrics.
    """
    rows = get_daily_health(user_id, date, limit=1)
    return rows[0] if rows else {}


@tool
def query_weekly_trends(user_id: str, weeks: int = 4) -> list[dict]:
    """Get a user's weekly health trends.

    Args:
        user_id: The user identifier.
        weeks: Number of recent weeks to return (default 4).

    Returns:
        List of weekly summaries with averages and week-over-week changes.
    """
    return get_weekly_trends(user_id, weeks)


@tool
def query_risk_flags(user_id: str, date: str | None = None) -> list[dict]:
    """Get active risk flags for a user.

    Args:
        user_id: The user identifier.
        date: Optional date (YYYY-MM-DD) to filter by.

    Returns:
        List of risk flags with severity, reason, and recommended action.
    """
    return get_risk_flags(user_id, date)


@tool
def check_user_risks(user_id: str) -> dict:
    """Get a user's current risk flags along with their preferences.

    Combines risk flags and user preferences in one call so the agent
    can make informed decisions about notifications.

    Args:
        user_id: The user identifier.

    Returns:
        Dict with 'risk_flags' and 'preferences' keys.
    """
    return {
        "risk_flags": get_risk_flags(user_id),
        "preferences": get_user_preferences(user_id),
    }


@tool
def fetch_user_anomalies(user_id: str, status: str | None = None) -> list[dict]:
    """Get anomalies recorded for a user.

    Args:
        user_id: The user identifier.
        status: Optional filter (e.g. 'open', 'resolved').

    Returns:
        List of anomaly records.
    """
    return get_anomalies(user_id, status)


@tool
def record_anomaly(
    user_id: str,
    metric: str,
    severity: str,
    reason: str,
    recommended_action: str,
    source: str = "agent",
) -> bool:
    """Create a new anomaly record.

    Args:
        user_id: The user the anomaly belongs to.
        metric: Which metric triggered it (e.g. 'sleep', 'heart_rate').
        severity: HIGH, MEDIUM, or LOW.
        reason: Human-readable explanation.
        recommended_action: What the agent suggests.
        source: Where this anomaly was detected.

    Returns:
        True if saved successfully.
    """
    from uuid import uuid4

    return create_anomaly({
        "anomaly_id": str(uuid4()),
        "user_id": user_id,
        "metric": metric,
        "severity": severity,
        "reason": reason,
        "recommended_action": recommended_action,
        "source": source,
        "status": "open",
    })


@tool
def resolve_anomaly(anomaly_id: str) -> bool:
    """Mark an anomaly as resolved.

    Args:
        anomaly_id: The anomaly to resolve.

    Returns:
        True if updated successfully.
    """
    return update_anomaly_status(anomaly_id, "resolved")


@tool
def notify_user(user_id: str, message: str) -> bool:
    """Send a notification to a user.

    Respects the user's notification preferences and quiet hours.

    Args:
        user_id: The user to notify.
        message: The notification message.

    Returns:
        True if the notification was sent.
    """
    return send_notification(user_id, message)


@tool
def notify_anomaly(anomaly: dict) -> bool:
    """Send an anomaly alert notification.

    Args:
        anomaly: Anomaly record with user_id, metric, severity, and reason.

    Returns:
        True if the notification was sent.
    """
    return send_anomaly_alert(anomaly)


@tool
def start_session(user_id: str) -> str:
    """Start a new agent conversation session.

    Args:
        user_id: The user starting the session.

    Returns:
        The new session ID.
    """
    return create_session(user_id)


@tool
def load_session(session_id: str) -> dict | None:
    """Load an existing agent session.

    Args:
        session_id: The session to load.

    Returns:
        Full session data including conversation history, or None.
    """
    return get_session(session_id)


@tool
def save_to_session(session_id: str, role: str, content: str) -> bool:
    """Append a message to a session's conversation history.

    Args:
        session_id: The session to update.
        role: Message role ('user' or 'assistant').
        content: Message content.

    Returns:
        True if saved successfully.
    """
    return append_to_session(session_id, role, content)
