# E-commerce Support Copilot

Five-service agent workbench: Streamlit UI, FastAPI gateway, bilingual intent
classification, policy retrieval/drafting, and SQLite audit telemetry.

Module 1 NLU implementation and commands: [README_MODULE1.md](services/intent_service/README_MODULE1.md).
New NLU artifacts must be trained and deployed before the intent API becomes healthy.
The source-only Module 1 update includes no measured model results.

To install service dependencies and launch locally, run `./run.sh`. The script creates `.venv` if needed. Module 1 training is separate; until its artifacts are installed, the intent service reports `degraded`. See [its runbook](services/intent_service/README_MODULE1.md).
For Docker, populate `artifacts/models/intent/`, configure `.env` from
`.env.example`, and follow the calibrated deployment commands in the Module 1 guide.

The UI produces drafts for human review. Approve/Edit actions record an audit
entry; they do not send a customer message or execute financial transactions.
Orders and policy data in this repository are demonstration data.
