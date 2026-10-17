"""Notification service.

Single channel (console/log) for the hackathon.
Checks user preferences for quiet hours and notification toggle.
"""

import logging
from datetime import datetime, timezone

from agent.dynamodb import get_user_preferences

logger = logging.getLogger("health_agent.notifications")


def is_quiet_hours(user_id: str) -> bool:
    """Check if the current time falls within the user's quiet hours."""
    prefs = get_user_preferences(user_id)
    if not prefs:
        return False

    now = datetime.now(timezone.utc)
    current_minutes = now.hour * 60 + now.minute

    try:
        start_parts = prefs["quiet_hours_start"].split(":")
        end_parts = prefs["quiet_hours_end"].split(":")
        start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
        end_minutes = int(end_parts[0]) * 60 + int(end_parts[1])
    except (KeyError, ValueError):
        return False

    if start_minutes <= end_minutes:
        return start_minutes <= current_minutes < end_minutes
    # Overnight quiet hours (e.g. 22:00–07:00)
    return current_minutes >= start_minutes or current_minutes < end_minutes


def send_notification(user_id: str, message: str, channel: str | None = None) -> bool:
    """Send a notification to the user.

    Looks up preferences to check notification_enabled and quiet_hours.
    If channel is None, reads it from user preferences.
    """
    prefs = get_user_preferences(user_id)
    if prefs and not prefs.get("notification_enabled", True):
        return False

    if is_quiet_hours(user_id):
        logger.info("Quiet hours active for %s — suppressing notification", user_id)
        return False

    if channel is None:
        channel = prefs.get("notification_channel", "console") if prefs else "console"

    if channel == "console":
        logger.info("[NOTIFICATION] %s: %s", user_id, message)
        print(f"[NOTIFICATION] {user_id}: {message}")
        return True

    logger.warning("Unknown notification channel '%s' for user %s", channel, user_id)
    return False


def send_anomaly_alert(anomaly: dict) -> bool:
    """Convenience wrapper for anomaly-specific notifications."""
    user_id = anomaly.get("user_id", "unknown")
    metric = anomaly.get("metric", "unknown")
    severity = anomaly.get("severity", "unknown")
    reason = anomaly.get("reason", "")
    message = f"[{severity}] {metric}: {reason}"
    return send_notification(user_id, message)
