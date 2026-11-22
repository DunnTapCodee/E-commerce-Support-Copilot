# E-commerce-Support-Copilot — Repository Guide (v0.2 candidate)

> **Evidence status:** Based on a read-only coding-agent survey and subsequent review of the repository on branch `refine` at `0e471a1` (2026-11-21). These are **reported observations**, not independently verified here. Re-check current code, working tree, and environments before acting. This document is navigation guidance, not a product/architecture decision record.

## Repository snapshot and navigation

- `services/gateway/` — HTTP entrypoint, routing, guardrails, RBAC.
- `services/conversation_service/` — conversation state and orchestration (reported configured port `8006`).
- `services/intent_service/` — intent classification and model backends.
- `services/rag_service/` — retrieval and answer drafting.
- `services/document_service/` — policy lifecycle and KB synchronization.
- `services/telemetry_service/` — orders, audit, RBAC-related data.
- `services/ui_service/` — Streamlit UI in Docker Compose.
- `frontend/` — separate React/Vite UI.
- `contracts/` — shared Pydantic DTOs and LLM access utilities.
- `tests/`, `evaluation/` — unit/behavioral/evaluation checks.
- `reports/`, `data/`, `artifacts/` — some are generated or modified at runtime. Do not treat them as disposable.
- `docs/architecture/overview.md` — Project Architecture Knowledge v1 (component boundaries, contracts, storage, LLM provider audit, verified invariants, and code/doc discrepancies).
- `docs/product/requirements.md` — Requirements Baseline v1 (product goals, business/functional/non-functional requirements, safety constraints, acceptance criteria, and open decisions).
- `docs/specs/intent-classification.md` & `docs/specs/copilot-workflow.md` — Implementable specifications (inputs/outputs, states, failure scenarios, edge cases, invariants, and verification mapping).
- `docs/assumptions.md` — Canonical Assumptions Register (`ASM-001`..`ASM-007` with impact and verification plans).
- `docs/decisions/` — Architecture Decision Records (`ADR-001` UI, `ADR-002` Intent LLM/ML fallback, `ADR-003` Vietnam timezone, `ADR-004` TLS verification).
- `docs/development/verification.md` — Verification Engineering Baseline v1 (requirement-to-test matrix, safe/unsafe test classification, AI/ML eval blockers, privacy safeguards, and offline CI baseline).

There were **seven Compose containers** (six backend services plus Streamlit UI), not seven backend microservices. Do not assume React or Streamlit is the official primary UI: this remains an owner decision. `refine` was the checked-out branch during review, not a confirmed permanent branching policy.

## Reported sensitive paths — assess consumers and side effects first

| Area | Why sensitive |
| --- | --- |
| `contracts/schemas.py` | Shared DTOs; possible divergence from `frontend/src/types/index.ts`; reported `get_system_now()` offset `+12 hours` requires owner clarification |
| `services/gateway/src/guardrails.py` | Financial and temporal policy invariants; changes may alter safety behavior |
| `services/document_service/src/policy_manager.py` | Mutates policy files / audit data and triggers RAG KB synchronization |
| `services/conversation_service/src/main.py` | Stateful orchestration, CSV/SQLite writes and a direct import from `scripts/export_continual_learning_dataset.py` |
| `services/gateway/src/clients.py` | Reported mismatch between `rag_service /retrieve` array response and `data.get("documents", [])` in fallback; investigate with contract tests |

### Security leads: handle urgently, without reading or reproducing secret values in reports

- `contracts/llm_failover.py`: reported hardcoded default credentials and TLS verification bypass.
- `services/intent_service/src/llm_classifier.py` and `services/rag_service/src/generator.py`: additional reported `verify=False` uses.
- If keys are real, notify owner to rotate/revoke them, review Git/history exposure, and remove hardcoding in an authorized remediation task. Do not wait for harness completion to address active exposure. Do not copy secrets into chat, issues, tests, or artifacts.

## Verification candidates: STATICALLY REVIEWED, NOT EXECUTED

**No test pass/fail baseline has been demonstrated by the supplied reports.** The classifications below come from a static inspection. Before execution, re-read fixtures/imports/config and verify the target database, network, and output paths. An "offline candidate" is **not a blanket preauthorization**.

| Candidate command/test | Reported classification / concern |
| --- | --- |
| `tests/test_guardrails.py`, `test_robustness.py`, `test_mlip_evaluation.py`, `test_conversation_order_pipeline.py` | Reported offline/local-only based on inspected logic; inspect transitive imports before running |
| `tests/test_policy_audit_rollback.py`, `test_rbac_step1.py` | Reported to use temporary directories for data; confirm isolation still holds |
| `tests/test_module3_orders.py` | **Do not run against the current root DB**: reported to use `copilot_telemetry.sqlite3` and forced migration/reset |
| `tests/test_intent_llm.py`, `test_conversation_service.py` | Possible live LLM/API calls; use mocks or controlled isolated evaluation |
| `tests/benchmark_latency.py`, `evaluation/behavioral_tests.py`, `evaluation/end_to_end_evaluator.py` | HTTP to running services; check backing data and services first |
| `evaluation/run_release_gates.py` | Reported overwrite of tracked `reports/mlip_release_gates_results.json` |
| `frontend` TypeScript check | Inspect `frontend/package.json`; prefer an installed local TypeScript compiler in no-emit mode. Avoid `npx` auto-install or unreviewed build side effects |
| `npm run build` | Produces build outputs; inspect script and dirty tree, and isolate if needed |

**Suggested offline baseline candidate after side-effect review** (not yet executed or auto-authorized):

```sh
pytest tests/test_guardrails.py tests/test_policy_audit_rollback.py tests/test_rbac_step1.py tests/test_robustness.py tests/test_mlip_evaluation.py tests/test_conversation_order_pipeline.py
```

Do not treat a complete `pytest` run, live service startup, or release-gate run as harmless by default. Starting conversation flows can modify `data/continual_learning_dataset.csv` and SQLite files; policy workflows can rewrite JSON/index data.

## Initial working tree reported in review (not a standing policy)

At snapshot `0e471a1`, existing changes included moved lecture/course documents, modifications to `artifacts/vector_store/policy_index.pkl` and `data/continual_learning_dataset.csv`, and untracked `docs/`/harness package. **Do not reset, clean, discard, move back, or delete any of these without checking the user's intent and obtaining appropriate permission.** Inspect `git status` again: the actual state may have changed.

## Documentation status

- `README.md` describes setup but reportedly omits or understates the React UI.
- `services/intent_service/README_MODULE1.md` contains specialized pipeline notes; reported legacy model loading wording may not match implementation.
- Historical `reports/*.md` may be stale about service count, UI and config defaults.

Use current runtime/config and code to determine actual behavior; use approved requirements for desired behavior. Raise unresolved contradictions to the owner when they affect a decision.

## Confirmed product & architecture decisions (see `docs/architecture/overview.md`)

1. **Primary UI:** React/Vite (`frontend/`) is the official primary UI; Streamlit (`services/ui_service/`) is retained as legacy/reference (do not remove Streamlit or modify Docker Compose solely for this).
2. **Intent Classification:** `LLM primary -> ML fallback when LLM is unavailable` using CKEY.VN (`https://api.xah.io/v1`, `mainnewnol/gpt-oss-120b`); safe observable `unavailable_fallback` when both are unavailable.
3. **Time Handling:** `+12 hours` shift removed; timestamps use real Vietnam time (`Asia/Ho_Chi_Minh`, `UTC+07:00`). Historical records are not batch-migrated.
4. **TLS Security:** `verify=True` enabled by default with optional CA bundle env vars (`LLM_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`).

## Open decisions (do not guess)

1. Branch integration workflow: `main` (stable), `refine` (integration), `feature/*`, `fix/*`, `docs/*` proposed — confirm CI/merge rules before acting.
2. Whether/when to containerize `frontend/` in `docker-compose.yml`, and when Module 1 artifacts will be populated into `artifacts/models/intent/`.
3. Whether `https://api.xah.io/v1` validates cleanly with default CA roots or requires `LLM_CA_BUNDLE` (online verification pending).
4. Whether leaving historical SQLite/JSON/CSV timestamps unmigrated (reconciled on read/display) is sufficient long-term.

## Reference checks for live repo adoption

Re-check `docker-compose.yml`, `run_dev.py`, `frontend/package.json`, `tests/` fixtures/imports, `evaluation/` output paths, relevant contracts, and current Git state. Record any differences in the adoption review; do not silently rewrite business or safety rules.
