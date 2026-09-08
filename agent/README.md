# Agent

Autonomous background agent that monitors the pipeline and personal metrics, diagnoses issues, and only surfaces when a real decision or intervention is needed.

- `tools/` — custom tool implementations (pipeline status, query gold tables, quality checks, flag/quarantine, notify, memory).
- `prompts/` — system/user prompt templates.

Runs via Ollama/LiteLLM with local/open models.
