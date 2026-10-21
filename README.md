# E-commerce Support Copilot

Five-service agent workbench: Streamlit UI, FastAPI gateway, bilingual intent
classification, policy retrieval/drafting, and SQLite audit telemetry.

Module 1 NLU implementation and commands: [README_MODULE1.md](services/intent_service/README_MODULE1.md).
New NLU artifacts must be trained and deployed before the intent API becomes healthy.
The source-only Module 1 update includes no measured model results.

For a complete local installation, install the intent training requirements plus
requirements from gateway, RAG, telemetry and UI, then run `python run_dev.py`.
For Docker, populate `artifacts/models/intent/`, configure `.env` from
`.env.example`, and follow the calibrated deployment commands in the Module 1 guide.

The UI produces drafts for human review. Approve/Edit actions record an audit
entry; they do not send a customer message or execute financial transactions.
Orders and policy data in this repository are demonstration data.
