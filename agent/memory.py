"""Agent session memory.

Manages conversation sessions stored in the DynamoDB agent_sessions table.
"""

from datetime import datetime, timezone
from uuid import uuid4

from agent.dynamodb import get_agent_session, save_agent_session


def create_session(user_id: str) -> str:
    """Create a new session and return its ID."""
    session_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    save_agent_session({
        "session_id": session_id,
        "user_id": user_id,
        "created_at": now,
        "last_updated": now,
        "conversation_history": [],
        "conversation_summary": "",
        "last_action": "",
    })
    return session_id


def get_session(session_id: str) -> dict | None:
    """Retrieve a session by ID."""
    return get_agent_session(session_id)


def append_to_session(session_id: str, role: str, content: str) -> bool:
    """Append a message to the session's conversation history."""
    session = get_agent_session(session_id)
    if not session:
        return False

    history = session.get("conversation_history", [])
    history.append({
        "role": role,
        "content": content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    session["conversation_history"] = history
    session["last_updated"] = datetime.now(timezone.utc).isoformat()
    session["last_action"] = f"{role}: {content[:100]}"
    return save_agent_session(session)
