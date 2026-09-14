"""Main agent entry point.

Creates a Strands Agent backed by Ollama and registers the tool layer.
Run with: python -m agent.agent
"""

import os
import sys

from dotenv import load_dotenv
from strands import Agent
from strands.models.ollama import OllamaModel

from agent.tools import (
    check_pipeline_status,
    check_user_risks,
    fetch_user_anomalies,
    load_session,
    notify_anomaly,
    notify_user,
    query_risk_flags,
    query_user_health,
    query_weekly_trends,
    record_anomaly,
    resolve_anomaly,
    save_to_session,
    start_session,
)

load_dotenv()

SYSTEM_PROMPT = """You are a health monitoring agent for the Health & Habit Guardian project.

Your role:
- Monitor user health data from the gold layer (daily_health, weekly_trends, risk_flags).
- Track anomalies and pipeline status from DynamoDB.
- Send notifications when intervention is needed.
- Maintain conversation memory across sessions.

Guidelines:
- Always check risk flags before making recommendations.
- Respect user notification preferences and quiet hours.
- Use specific data when giving advice — reference actual scores and metrics.
- When you detect an issue, record it as an anomaly.
- Keep conversations concise and actionable.
- Never provide medical advice — frame everything as project heuristics.

You have access to tools that query Databricks gold tables, DynamoDB, and send notifications.
Use them proactively rather than guessing at data.
"""


def create_agent() -> Agent:
    """Create and configure the Strands Agent."""
    model = OllamaModel(
        model_id=os.getenv("OLLAMA_MODEL", "llama3.1"),
        host=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    )

    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            check_pipeline_status,
            query_user_health,
            query_weekly_trends,
            query_risk_flags,
            check_user_risks,
            fetch_user_anomalies,
            record_anomaly,
            resolve_anomaly,
            notify_user,
            notify_anomaly,
            start_session,
            load_session,
            save_to_session,
        ],
    )


def main():
    """Interactive agent loop."""
    agent = create_agent()
    print("Health & Habit Guardian Agent")
    print("Type 'exit' to quit.\n")

    user_id = input("Enter user_id: ").strip()
    session_id = start_session(user_id)
    print(f"Session started: {session_id}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if user_input.lower() in ("exit", "quit", "q"):
            print("Goodbye.")
            break

        if not user_input:
            continue

        save_to_session(session_id, "user", user_input)
        response = agent(user_input)
        save_to_session(session_id, "assistant", str(response))
        print(f"Agent: {response}\n")


if __name__ == "__main__":
    main()
