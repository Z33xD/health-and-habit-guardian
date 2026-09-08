# Health & Habit Guardian

An autonomous background agent that ingests personal health/habit data (wearables, sleep, activity, nutrition), builds clean modelled datasets in a Databricks lakehouse, continuously monitors for anomalies and patterns, and only surfaces when a decision or intervention is needed.

## Repo Layout

```
health-guardian/
├── data/samples/          # public + synthetic CSVs
├── ingestion/             # upload handling, S3 landing logic
├── databricks/
│   ├── notebooks/         # bronze/silver/gold medallion notebooks
│   ├── jobs/              # job orchestration definitions
│   └── schemas/           # Delta table schemas & data model
├── agent/
│   ├── tools/             # agent tool implementations
│   ├── prompts/           # system/user prompt templates
│   └── README.md
├── backend/
│   ├── app/               # FastAPI application
│   └── tests/
├── frontend/              # React dashboard + chat
├── infra/                 # CDK/Terraform or deploy scripts
├── docs/
├── tests/                 # end-to-end tests
├── .gitignore
├── README.md
└── requirements.txt
```
