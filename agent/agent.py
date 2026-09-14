"""Main agent entry point.

Creates a Strands Agent backed by LM Studio (OpenAI-compatible) and
registers the Phase 1 tool layer.
Run with: python -m agent.agent
"""

import os

from dotenv import load_dotenv
from strands import Agent
from strands.models.openai import OpenAIModel

from agent.memory import append_to_session, create_session
from agent.tools import (
    get_pipeline_status,
    get_quality_metrics,
    get_risk_flags,
    get_user_preferences,
    update_anomaly_status,
)

load_dotenv()

SYSTEM_PROMPT = """You are a health monitoring agent for the Health & Habit Guardian project.

You have these tools:
- get_pipeline_status(): Check if the most recent Databricks pipeline run succeeded.
- get_risk_flags(user_id): Get health risk flags for a user.
- get_quality_metrics(): Check data-quality status of pipeline tables.
- update_anomaly_status(anomaly_id, status): Mark an anomaly open or resolved.
- get_user_preferences(user_id): Get a user's targets and notification settings.

Rules:
- Always call a tool to get data before answering. Never guess numbers.
- Reference actual metrics (sleep hours, steps, scores) in your answers.
- Keep responses under 4 sentences.
- These are project heuristics, not medical advice.
"""

# Phase 2: add send_notification to this list when ready.
TOOLS = [
    get_pipeline_status,
    get_risk_flags,
    get_quality_metrics,
    update_anomaly_status,
    get_user_preferences,
]


def create_agent() -> Agent:
    """Create and configure the Strands Agent backed by LM Studio."""
    model = OpenAIModel(
        client_args={
            "api_key": "lm-studio",
            "base_url": os.getenv("LM_STUDIO_URL", "http://localhost:1234/v1"),
        },
        model_id=os.getenv("LM_STUDIO_MODEL", "qwen2.5-coder-7b-instruct"),
        params={"temperature": 0.3, "max_tokens": 1024},
    )

    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=TOOLS,
    )


def main() -> None:
    """Interactive agent loop with persisted session memory."""
    agent = create_agent()
    print("Health & Habit Guardian Agent")
    print("Type 'exit' to quit.\n")

    user_id = input("Enter user_id: ").strip()
    session_id = create_session(user_id)
    print(f"Session started for user {user_id}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            return

        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye.")
            return

        if not user_input:
            continue

        append_to_session(session_id, "user", user_input)
        response = agent(user_input)
        append_to_session(session_id, "assistant", str(response))
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    main()