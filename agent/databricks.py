"""Databricks SQL connector helper.

Provides controlled access to the gold tables via specific query functions.
No arbitrary SQL execution — the agent only calls named functions.
"""

import os

import databricks.sql as sql
from dotenv import load_dotenv

load_dotenv()

DATABRICKS_HOST = os.getenv("DATABRICKS_HOST", "")
DATABRICKS_TOKEN = os.getenv("DATABRICKS_TOKEN", "")
DATABRICKS_HTTP_PATH = os.getenv("DATABRICKS_HTTP_PATH", "")
CATALOG = "health_and_habit_guardian"


def _get_connection():
    return sql.connect(
        server_hostname=DATABRICKS_HOST,
        http_path=DATABRICKS_HTTP_PATH,
        access_token=DATABRICKS_TOKEN,
    )


def _query(sql_text: str, params: list | None = None) -> list[dict]:
    """Execute a parameterised query and return rows as dicts."""
    conn = _get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql_text, params or [])
        columns = [desc[0] for desc in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]
    finally:
        conn.close()


# ── Gold table queries ───────────────────────────────────────────────────────

def get_daily_health(user_id: str, date: str | None = None, limit: int = 30) -> list[dict]:
    """Fetch daily health scores for a user.

    Args:
        user_id: The user identifier.
        date: Optional date string (YYYY-MM-DD) for a specific day.
        limit: Max rows returned (most recent first).
    """
    base = (
        f"SELECT * FROM {CATALOG}.gold.daily_health "
        "WHERE user_id = ?"
    )
    params: list = [user_id]
    if date:
        base += " AND date = ?"
        params.append(date)
    base += " ORDER BY date DESC LIMIT ?"
    params.append(limit)
    return _query(base, params)


def get_weekly_trends(user_id: str, weeks: int = 4) -> list[dict]:
    """Fetch weekly trend summaries for a user.

    Args:
        user_id: The user identifier.
        weeks: Number of recent weeks to return.
    """
    return _query(
        f"SELECT * FROM {CATALOG}.gold.weekly_trends "
        "WHERE user_id = ? "
        "ORDER BY week_start DESC LIMIT ?",
        [user_id, weeks],
    )


def get_risk_flags(user_id: str, date: str | None = None) -> list[dict]:
    """Fetch active risk flags for a user.

    Args:
        user_id: The user identifier.
        date: Optional date string (YYYY-MM-DD) to filter by.
    """
    base = (
        f"SELECT * FROM {CATALOG}.gold.risk_flags "
        "WHERE user_id = ?"
    )
    params: list = [user_id]
    if date:
        base += " AND date = ?"
        params.append(date)
    base += " ORDER BY date DESC"
    return _query(base, params)
