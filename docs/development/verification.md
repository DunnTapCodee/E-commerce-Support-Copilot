# Verification Engineering Baseline v1

> **Purpose:** Authoritative verification matrix, test safety classification, AI/ML evaluation separation, privacy/security checks, and deterministic CI baseline for `E-commerce-Support-Copilot`.
> **Linked Knowledge:** [Requirements Baseline v1](../product/requirements.md), [Architecture Overview v1](../architecture/overview.md), [Intent Classification Spec](../specs/intent-classification.md), [Copilot Workflow Spec](../specs/copilot-workflow.md), [Assumptions Register](../assumptions.md), [REPO_GUIDE.md](../agent/REPO_GUIDE.md)
>
> **Verification Status Legend (evidence-based only):**
> - **`Verified`** — Passing automated test evidence exists in the current code state for the full scope of the requirement.
> - **`Partially Verified`** — Deterministic unit/mock or isolated tests pass, but live integration, trained ML artifacts, or online verification is still pending.
> - **`Not Verified`** — Implemented or documented without adequate executable test coverage.
> - **`Blocked`** — Cannot be verified due to missing ML artifacts, offline/credential constraints, or unresolved product decisions (`OD-*`).

---

## 1. Requirement Verification Matrix

| Req ID | Requirement Summary | Modules | Spec | Automated Tests / Checks | Status | Notes / Gaps |
| --- | --- | --- | --- | --- | --- | --- |
| `FR-UI-001`, `FR-UI-004` | React/Vite primary UI & accurate model labels | `frontend/src/`, `conversation_service/src/main.py` | [SPEC-WF-001](../specs/copilot-workflow.md) | `frontend` `tsc --noEmit`; `test_contracts_and_integration.py::test_frontend_required_interface_fields_exist_in_pydantic_contracts` | `Partially Verified` | Typecheck + schema contract verified; no automated React component/E2E browser tests yet. |
| `FR-INT-001`, `FR-INT-002`, `FR-INT-003`, `FR-INT-004` | Intent `LLM primary -> ML fallback -> safe human escalation`; CKEY.VN config; no silent Gemini fallback; honest `model_name` & `/health` | `services/intent_service/src/predictor.py`, `llm_classifier.py`, `main.py`; `conversation_service/src/main.py`; `gateway/src/main.py` | [SPEC-INT-001](../specs/intent-classification.md) | `test_architecture_decisions_alignment.py`, `test_llm_failover_and_offline_isolation.py`, `test_contracts_and_integration.py` | `Partially Verified` | Routing/fail-closed logic `Verified` via mocks; real Module 1 ML artifacts (`OD-002`) and live CKEY.VN call (`OD-003`) are **Blocked**. |
| `FR-INT-005` | Bilingual & unaccented Vietnamese normalization (16 canonical `TARGET_INTENTS`) | `services/intent_service/src/normalizer.py`, `llm_classifier.py`, `pipeline/dataset.py` | [SPEC-INT-001](../specs/intent-classification.md) | `test_intent_llm.py`, `test_robustness.py`, `test_mlip_evaluation.py` (offline heuristic/legacy sklearn) | `Partially Verified` | 16 canonical intents + `out_of_scope` confirmed (`OD-004`) and aligned in `llm_classifier.py` & `tracker.py`; legacy sklearn `1.6.1` unpickle warnings under `1.9.1`. |
| `FR-DLG-001`, `FR-DLG-002` | Multi-turn dialogue persistence + Gateway standalone & SSE fallback + CircuitBreaker + concurrency | `conversation_service/src/`, `gateway/src/main.py`, `clients.py`, `circuit_breaker.py` | [SPEC-WF-001](../specs/copilot-workflow.md) | `test_gateway_rag_fallback.py`, `test_contracts_and_integration.py`, `test_rbac_step1.py`, `test_conversation_order_pipeline.py`, `test_conversation_service.py`, `test_e2e_customer_staff_sync.py`, `test_load_concurrency.py` | `Partially Verified` | Mocked Gateway primary/fallback/SSE/CircuitBreaker + handover + 30-worker WAL concurrency + draft-clear lifecycle + isolated SQLite verified; live multi-process E2E not run in offline baseline. |
| `FR-RAG-001`, `FR-RAG-002` | Policy retrieval JSON array (`bm25` default) & CKEY.VN grounded drafting without silent Gemini fallback | `services/rag_service/src/main.py`, `retriever.py`, `generator.py`; `copilot_draft_engine.py` | [SPEC-WF-001](../specs/copilot-workflow.md) | `test_gateway_rag_fallback.py`, `test_contracts_and_integration.py`, `test_architecture_decisions_alignment.py`, `test_data_and_pipeline_quality.py` | `Partially Verified` | `/retrieve` contract, `bm25`/`tfidf` Top-3 recall & trap filtering (`test_data_and_pipeline_quality.py`), and no-Gemini fallback verified; retrieval quality comparison (`bm25` vs `dense`) uses `scripts/benchmark_retrieval.py`. |
| `FR-ORD-001` | Order lookup & cancellation rules | `services/telemetry_service/src/repository.py`, `conversation_service/src/tools/order_tools.py` | [SPEC-WF-001](../specs/copilot-workflow.md) | `test_module3_orders.py`, `test_conversation_order_pipeline.py`, `test_rbac_step1.py`, `test_data_and_pipeline_quality.py` | `Verified` (isolated unit/repo) | `test_module3_orders.py` isolated via `tempfile.TemporaryDirectory()` and promoted to CI; covers migration, indexed lookup, LRU cache, and cancellation rules. |
| `FR-POL-001` | Policy CRUD, parsing/filtering, dynamic `is_active`, audit log, rollback, RAG sync | `services/document_service/src/policy_manager.py`, `policy_filter.py`, `routers/` | [Architecture Overview](../architecture/overview.md) | `test_policy_audit_rollback.py`, `test_policy_filter.py`, `test_data_and_pipeline_quality.py` (offline heuristic/mocked LLM, temp dir, `AsyncMock` on `trigger_rag_sync`, 0 HTTP calls) | `Partially Verified` | Schema/CRUD, parsing/heuristic fallback, dynamic `is_active`, audit log, delete, rollback, and sync trigger counts verified offline; live `rag_service /sync-kb` HTTP call remains unverified in CI. |
| `FR-TEL-001`, `FR-TEL-002` | Audit log, human action metrics, drift/shadow APIs (`/audit/drift`, `/audit/shadow/evaluate`), continual learning CSV PII safety | `services/telemetry_service/src/main.py`, `repository.py`, `metrics.py`; `scripts/export_continual_learning_dataset.py` | [SPEC-WF-001](../specs/copilot-workflow.md) | `test_architecture_decisions_alignment.py`, `test_contracts_and_integration.py`, `test_production_drift_and_shadow.py`, `test_mlip_evaluation.py` | `Verified` (unit/isolated) | PII redaction, opt-out toggle, `+07:00` chronological sorting, drift detection (`recent_records`), and shadow comparison verified on temp DBs/files. |
| `NFR-SEC-001`, `NFR-SEC-002` | Default `verify=True` + CA bundle; zero hardcoded keys; offline isolation | `contracts/llm_failover.py`, `llm_classifier.py`, `generator.py`, `copilot_draft_engine.py` | [SPEC-INT-001](../specs/intent-classification.md) | Static check (`zero verify=False`), `test_architecture_decisions_alignment.py`, `test_llm_failover_and_offline_isolation.py` | `Partially Verified` | Unit/static checks **Verified**; live TLS handshake to `https://api.xah.io/v1` is **Blocked** (`ASM-001`, `OD-003`). |
| `NFR-TIME-001` | Real `Asia/Ho_Chi_Minh` (`+07:00`), zero `+12h` offset, mixed UTC/VN sorting | `contracts/schemas.py`, `sqlite_state_store.py`, `state.py`, `policy_manager.py`, `repository.py`, `frontend/src/lib/time.ts` | [ADR-003](../decisions/ADR-003-vietnam-time-no-12h-offset.md) | Static check (`zero hours=12`), `test_architecture_decisions_alignment.py`, `frontend` `tsc --noEmit` | `Verified` (backend + TS typecheck) | Backend unit + midnight sorting verified; browser runtime test for `time.ts` not yet added (`Not Verified` in browser). |
| `SC-001`..`SC-007` | Financial, temporal/superseded, unified `0.60` confidence, shared faithfulness parity (`0.70`), prompt injection, review audit guardrails | `contracts/safety.py`, `services/gateway/src/guardrails.py`, `conversation_service/src/policies/` | [SPEC-WF-001](../specs/copilot-workflow.md) | `test_guardrails.py`, `test_conversation_service.py`, `test_robustness.py`, `test_mlip_evaluation.py`, `test_architecture_decisions_alignment.py` | `Verified` (current rules & parity, `OD-005` resolved) | Guardrail rules, decoupled scope/`0.60` confidence, and primary-path faithfulness/order-number grounding verified offline. |
| `NFR-PERF-001`, `NFR-QUAL-001`, `NFR-REL-002`, `NFR-COST-001` | Production latency, ML quality, availability, cost SLAs | Cross-cutting | [Requirements](../product/requirements.md) §4 | None (targets are `TBD`) | `Blocked` | Blocked on owner-defined SLAs (`OD-006`) and real Module 1 artifacts (`OD-002`). |

---

## 2. Test Suite Inventory & Side-Effect Classification

### 2.1 Verified Safe Deterministic Offline Suite (CI-Eligible)

Run with:
```powershell
$env:DISABLE_EXTERNAL_LLM="true"
$env:DISABLE_CONTINUAL_LEARNING_CSV_EXPORT="true"
$env:CONVERSATIONS_DB_PATH="$env:TEMP\ci_copilot_conversations.sqlite3"
python -m pytest tests/test_contracts_and_integration.py tests/test_architecture_decisions_alignment.py tests/test_llm_failover_and_offline_isolation.py tests/test_gateway_rag_fallback.py tests/test_guardrails.py tests/test_rbac_step1.py tests/test_conversation_order_pipeline.py tests/test_conversation_service.py tests/test_module3_orders.py tests/test_policy_filter.py tests/test_policy_audit_rollback.py tests/test_data_and_pipeline_quality.py tests/test_e2e_customer_staff_sync.py tests/test_load_concurrency.py tests/test_production_drift_and_shadow.py tests/test_order_actions_and_proactive_delay.py tests/test_replay_and_rollback.py tests/test_agent_skills.py tests/test_agent_harness_eval.py -v
```

| Test File | Test Type | Network / LLM | Disk / DB Side Effects | CI Safe? |
| --- | --- | --- | --- | --- |
| `tests/test_contracts_and_integration.py` | Contract, Integration, Privacy | Mocked (`httpx.MockTransport` / `ASGITransport`) | Temp dir only | **Yes** |
| `tests/test_architecture_decisions_alignment.py` | Unit, Integration, TLS, Time | Mocked (`httpx`/`requests`) | Temp SQLite/files only | **Yes** |
| `tests/test_llm_failover_and_offline_isolation.py` | Unit, Security/Isolation | Mocked; asserts 0 calls | Temp dir only | **Yes** |
| `tests/test_gateway_rag_fallback.py` | Integration, Contract | Mocked (`httpx.MockTransport`) | None | **Yes** |
| `tests/test_guardrails.py` | Unit (Safety Invariants) | None | None | **Yes** |
| `tests/test_rbac_step1.py` | Unit, Integration | Mocked `_get_json` | Temp SQLite only | **Yes** |
| `tests/test_conversation_order_pipeline.py` | Unit | None | Read-only `data/mock_orders.json` | **Yes** |
| `tests/test_conversation_service.py` | Conversation Unit (`ADR-002` fail-closed + memory/state) | None | Temp dir SQLite (`CONVERSATIONS_DB_PATH`) | **Yes** |
| `tests/test_module3_orders.py` | Order DB Integration | None | Temp dir SQLite only | **Yes** |
| `tests/test_policy_filter.py` | Policy Extraction & Parser Unit | `DISABLE_EXTERNAL_LLM=true` / `AsyncMock` | None | **Yes** |
| `tests/test_policy_audit_rollback.py` | Unit, Integration | Mocked (`trigger_rag_sync` & `httpx.AsyncClient`) | Temp dir only | **Yes** |
| `tests/test_data_and_pipeline_quality.py` | Data Schema & RAG Index Regression (`bm25` + `tfidf`) | None | Temp dir index only | **Yes** |
| `tests/test_e2e_customer_staff_sync.py` | SQLite E2E Lifecycle & Draft Clear | None | Temp dir SQLite only | **Yes** |
| `tests/test_load_concurrency.py` | Concurrency / SQLite WAL Load (30 workers) | None | Temp dir SQLite only | **Yes** |
| `tests/test_production_drift_and_shadow.py` | Telemetry Drift & Shadow API Unit/Integration | None (`TestClient` patched to temp repo) | Temp dir SQLite only | **Yes** |
| `tests/test_order_actions_and_proactive_delay.py` | Order Action HITL, Delay 30k Agent & Incident Clustering | None | Temp dir SQLite only | **Yes** |
| `tests/test_replay_and_rollback.py` | Read-Only PII-Redacted Replay & Config Rollback Registry | `DISABLE_EXTERNAL_LLM=true` | Read-only SQLite URI & Temp dir only | **Yes** |
| `tests/test_agent_skills.py` | Unit, Governance | None | Read-only `.agents/skills` & temp dir | **Yes** |
| `tests/test_agent_harness_eval.py` | Unit, Eval Harness | None (synthetic fixtures only) | Read-only manifest/fixtures & temp dir | **Yes** |

### 2.2 Conditional / Artifact-Dependent / Unsafe Tests (Excluded from Default CI)

| File | Category | Risk / Side Effect / Blocker | Safe Usage Condition |
| --- | --- | --- | --- |
| `tests/test_robustness.py` | Robustness / Legacy ML | Loads `ML-model/` (sklearn `1.6.1` pickle -> `InconsistentVersionWarning` on `1.9.1`) and `artifacts/vector_store/policy_index.pkl` (gitignored, may not exist on fresh CI checkout). | Local offline run when `DISABLE_EXTERNAL_LLM=true` and `policy_index.pkl` exists. |
| `tests/test_mlip_evaluation.py` | Behavioral / Safety Eval | Loads legacy ML + `evaluation/*`; emits 36 sklearn version warnings; tests offline heuristic fallback when `DISABLE_EXTERNAL_LLM=true`. | Local offline run with `DISABLE_EXTERNAL_LLM=true`. |
| `tests/test_intent_llm.py` | Intent Benchmark (130+ cases) | Calls `LLMIntentClassifier.predict()` — triggers live external LLM calls if API keys are set in env (falls back to regex heuristic if `DISABLE_EXTERNAL_LLM=true`). | Run only as explicit offline heuristic check (`DISABLE_EXTERNAL_LLM=true`) or authorized live eval. |
| `tests/benchmark_latency.py`, `tests/evaluate_safety_metrics.py`, `evaluation/end_to_end_evaluator.py` | System / Benchmark | Expects running services or local model/index artifacts. | Manual / staging evaluation only. |
| `evaluation/run_release_gates.py` | Release Gate Runner | **Overwrites tracked file** `reports/mlip_release_gates_results.json`. | Manual release review only; never in PR CI. |

---

## 3. AI/ML Evaluation Strategy (Separated from Unit Tests)

> **Rule:** Offline unit tests with mocks verify **control flow, contracts, and fail-closed safety** — they do **not** measure real model quality. Separately, **Coding Agent Harness evaluation** lives under `evaluation/agent_harness/` and [docs/agent/AGENT_EVALUATION.md](../agent/AGENT_EVALUATION.md) rather than product AI/ML release gates (`evaluation/run_release_gates.py`).

| Capability | Current Evaluation Assets (`Observed`) | Recommended Metrics (Targets: **`TBD`** per `OD-006`) | Current Blockers |
| --- | --- | --- | --- |
| **Intent Classification (LLM & ML)** | `evaluation/behavioral_tests.py` (MFT/INV/DIR), `evaluation/model_benchmarks.py`, `tests/test_intent_llm.py` (130 cases), `data/eval/real_vi_handwritten.csv` (**header-only template**). | Macro-F1, Per-Intent Recall (especially `request_refund`, `payment_issue`, `human_agent`), Unaccented/Typo Slice Accuracy, OOS False-Accept Rate, P50/P95 Latency. | 1) `artifacts/models/intent/` is empty (only `.gitkeep`); 2) Legacy `ML-model/` pickled on sklearn `1.6.1` vs runtime `1.9.1`; 3) `real_vi_handwritten.csv` has no labeled rows yet; 4) Live CKEY.VN eval requires authorized online run (`OD-003`). |
| **RAG Policy Retrieval** | `scripts/benchmark_retrieval.py`, `data/retrieval_eval.json` (Vietnamese labeled query set), `reports/module2_retrieval_benchmark.json`. | Recall@k (`k=1,3`), MRR@k, Expired/Superseded Trap Rejection Rate, P95 Retrieval Latency. | Dense/hybrid/reranked modes require optional `requirements-retrieval-experiments.txt` and HuggingFace model downloads. |
| **Grounded Draft Generation** | `evaluation/oracle_evaluator.py` (hard constraints + rubric), `evaluation/guardrail_evaluator.py`, `contracts/safety.py` (`evaluate_response_faithfulness`, `evaluate_runtime_safety_envelope`). | Citation Precision/Recall (`[doc_id]`), Hallucination Block Rate, Unauthorized Financial Promise Rate (`0%` goal). | Live generation quality with `vantoanbk57/deepseek-v4.1-flash` unmeasured due to offline constraint. |

---

## 4. Privacy & Security Verification

### Continual Learning CSV Audit (`data/continual_learning_dataset.csv`)
- **Pattern Scan (`Observed`, zero content disclosed):** `83` total rows; `0` phone number matches, `0` email matches, `12` order ID matches (`ORD-...`, demo orders).
- **Identified Write Paths:**
  - `services/conversation_service/src/main.py` (`/chat` line 550 & `/chat_stream` line 750) calls `scripts/export_continual_learning_dataset.py::append_single_interaction_to_csv()` on every turn.
- **Git Exposure Risk:** `data/continual_learning_dataset.csv` is currently tracked in Git (not in `.gitignore`). If real customer queries containing phone numbers, emails, or ID numbers are entered in dev/pilot sessions, they could be committed accidentally.
- **Preventive Safeguards Implemented (reversible, zero modification to existing rows):**
  1. Added `redact_pii()` in `scripts/export_continual_learning_dataset.py` to mask emails (`[REDACTED_EMAIL]`), Vietnamese/standard phone numbers (`[REDACTED_PHONE]`), and 9–16 digit IDs (`[REDACTED_NUMBER]`) before writing new rows, while preserving `ORD-...` IDs.
  2. Added `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=1|true|yes` toggle so tests, CI, and privacy-strict environments can disable runtime CSV writes completely.
  3. Verified in `tests/test_contracts_and_integration.py::TestPrivacyContinualLearningCsvExport`.
- **Remaining Owner Action (`OD-008`):** Decide whether to untrack `data/continual_learning_dataset.csv` from Git and move runtime exports to an ignored path.

---

## 5. CI Baseline (`.github/workflows/ci-offline.yml`)

A minimal, deterministic, offline-only GitHub Actions workflow has been created at `.github/workflows/ci-offline.yml` with 3 jobs:
1. **`backend-offline-tests`**: Installs lightweight service deps (`gateway`, `document_service`, `rag_service`, `pytest`), enforces static guard (`zero verify=False` and `zero hours=12`), validates `.agents/skills/` via `python scripts/validate_skills.py`, validates the Agent Evaluation manifest and offline smoke runner (`python -m evaluation.agent_harness.run_eval validate-manifest` and `smoke-test --quiet`), and runs the 19 verified deterministic offline pytest suites with `DISABLE_EXTERNAL_LLM=true`, `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`, and isolated `CONVERSATIONS_DB_PATH=/tmp/ci_copilot_conversations.sqlite3`.
2. **`frontend-typecheck`**: Runs `npm ci`, `npx tsc --noEmit`, and `npm run test:unit` inside `frontend/`.
3. **`docs-link-check`**: Verifies zero broken internal Markdown links across `docs/**/*.md`.

---

## 6. Selective Integration Audit of `origin/testing` (`5be8500`)

The following components from `origin/testing` were merged (preserving `5be8500` commit history and contributor attribution), reviewed, hardened, and integrated into `harness`:
- **Integrated & Hardened:**
  - `services/telemetry_service/src/metrics.py` (`detect_telemetry_drift`, `evaluate_shadow_comparison`) & `main.py` (`GET /audit/drift`, `POST /audit/shadow/evaluate`): Fixed the `stats.get("recent_logs")` -> `stats.get("recent_records")` key bug that caused `/audit/drift` to read empty data, and aligned low-confidence drift default to `0.60`.
  - `tests/test_production_drift_and_shadow.py`: Hardened `setUp`/`tearDown` to patch `repo_instance` & `DB_PATH` onto `tempfile.TemporaryDirectory()`, plus added an HTTP `/audit/drift` test against seeded temp records.
  - `tests/test_data_and_pipeline_quality.py`: Added runtime-default `bm25` coverage alongside `tfidf` (exercised automatically when `rank_bm25` is installed, e.g., in CI via `services/rag_service/requirements.txt`) for Top-3 recall and expired/superseded trap exclusion.
  - `tests/test_e2e_customer_staff_sync.py` & `tests/test_load_concurrency.py`: Integrated isolated SQLite WAL concurrency and draft-clear lifecycle tests into `.github/workflows/ci-offline.yml`.
  - `evaluation/behavioral_tests.py` (`run_multi_turn_context`), `evaluation/oracle_evaluator.py` (`verify_dynamic_order_grounding`), `evaluation/run_release_gates.py`, and `tests/test_mlip_evaluation.py`: Added multi-turn behavioral checks and Tier-4 order grounding oracle.
  - `tests/test_contracts_and_integration.py`: Merged round-trip Pydantic contract serialization checks (`StaffProfile`, `CustomerProfile`, `AuditLogCreate`, `HumanActionUpdate`, `GatewayResponse`) without dropped legacy kwargs.
  - `frontend/src/lib/chat-helpers.ts` & `frontend/src/lib/__tests__/chat-helpers.test.mjs`: Refactored `ChatView.tsx`, `CustomerPortalView.tsx`, and `StaffCustomerManagerView.tsx` to import the shared helpers (`findRepliedCustomerQuestion`, `formatRepliedCustomerQuestionGroup`, `sortCustomersByNewestActivity`, `extractPolicyCodes`) and updated `chat-helpers.test.mjs` (`npm run test:unit`) to compile and test the real TypeScript module rather than duplicated test functions. Kept `frontend/e2e/customer-staff-flow.spec.ts` as an explicit non-executed E2E scenario specification.
- **Intentionally Excluded / Superseded during Merge:**
  - `.github/workflows/ci.yml`: Excluded in favor of hardened `.github/workflows/ci-offline.yml` (`ci.yml` lacked `DISABLE_EXTERNAL_LLM=true`, `CONVERSATIONS_DB_PATH` isolation, `services/`/`scripts/` linting, Python type-checking, and labeled `node --test` as Vitest).
  - `tests/test_contracts_and_isolation.py`: Superseded by `tests/test_contracts_and_integration.py` (avoided dropped `session_id`/`latency_ms` kwargs and unmocked HTTP/breaker dependencies).

*Explicitly excluded from CI:* Live LLM API tests (`test_intent_llm.py`), root-DB-mutating tests (`test_module3_orders.py`), root-DB-initializing/stale-expectation tests (`test_conversation_service.py`), legacy-pickle/gitignored-index tests (`test_robustness.py`, `test_mlip_evaluation.py`), and `evaluation/run_release_gates.py`.
