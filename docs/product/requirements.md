# E-commerce Support Copilot — Requirements Baseline v1

> **Purpose:** Baseline product and system requirements for `E-commerce-Support-Copilot`, linked with [Architecture Overview v1](../architecture/overview.md), [Intent Classification Spec](../specs/intent-classification.md), [Copilot Workflow Spec](../specs/copilot-workflow.md), [Assumptions Register](../assumptions.md), [ADRs](../decisions/ADR-001-primary-ui-react-legacy-streamlit.md), and [REPO_GUIDE.md](../agent/REPO_GUIDE.md).
>
> **Status Classification (strictly enforced):**
> - **`Confirmed`** — Explicitly confirmed by the project owner/user.
> - **`Observed`** — Currently implemented in code, contracts, tests, or evaluation artifacts (**not** automatically treated as a confirmed product requirement).
> - **`Proposed`** — Candidate requirement inferred from existing capabilities/architecture; awaits owner confirmation.
> - **`Open Decision`** — Unresolved product or architectural question requiring owner direction.
>
> **Target Rule:** Quantitative targets (latency, accuracy, availability, cost) without an owner-confirmed product SLA are marked **`TBD`**. Any numeric thresholds cited from code/evaluation scripts are explicitly tagged `Observed` (implementation/eval defaults), not `Confirmed` product SLAs.

---

## 1. Product Goals & Scope

| ID | Statement | Status | Source / Evidence |
| --- | --- | --- | --- |
| `PG-001` | Provide an AI-assisted E-commerce Customer Support (CSKH) Copilot supporting bilingual (Vietnamese/English) customer inquiries, policy-grounded response drafting, order lookup, and human-in-the-loop review. | `Proposed` (aligned with `Observed`) | `README.md`, `services/conversation_service/src/main.py`, `services/gateway/src/main.py` |
| `PG-002` | Establish **React/Vite (`frontend/`)** as the official primary UI for ongoing product development, while retaining **Streamlit (`services/ui_service/`)** as a legacy UI for reference and existing Compose workflows without deleting it or restructuring Docker Compose UI deployment in this baseline. | `Confirmed` | Owner decision; `docs/architecture/overview.md` §1, §2 |
| `PG-003` | Prioritize safe, fail-closed customer support: when requests cannot be handled reliably (financial operations, out-of-scope queries, unavailable AI backends, expired policies, or prompt injection), escalate safely to human staff instead of generating ungrounded responses. | `Confirmed` | Owner decision; `services/gateway/src/guardrails.py`, `services/conversation_service/src/policies/response_dispatcher.py` |
| `PG-004` | **Non-Goal / Out of Scope:** The Copilot must not autonomously send unreviewed final replies to customers or autonomously execute financial refunds/compensations; staff review (`APPROVE`/`EDIT`/`REJECT`/`ESCALATE`) records audit decisions only. | `Observed` / `Proposed` | `README.md`, `services/telemetry_service/src/repository.py` |

---

## 2. Business Requirements

| ID | Business Requirement | Status | Source / Evidence |
| --- | --- | --- | --- |
| `BR-001` | **Human-in-the-Loop Control:** AI generates suggested replies and agent guidance for CS staff review rather than acting as an unchecked autonomous agent. | `Proposed` (`Observed`) | `README.md`, `services/conversation_service/src/main.py`, `services/telemetry_service/src/repository.py` |
| `BR-002` | **Safe Escalation on Unreliable Handling:** Any request that cannot be classified or grounded reliably (out-of-scope, low confidence, missing/expired policy, or backend outage) must fall back safely to human escalation. | `Confirmed` | Owner decision; `docs/architecture/overview.md` §1.2, §7 |
| `BR-003` | **Financial Risk Prevention:** Refund requests and payment issues must not be resolved autonomously by LLM generation; staff must review order/payment records manually (`DIRECT_REFUND_FORM`), and order cancellations must enforce status eligibility rules. | `Proposed` (`Observed`) | `services/gateway/src/guardrails.py`, `services/conversation_service/src/policies/response_dispatcher.py`, `services/telemetry_service/src/repository.py` |
| `BR-004` | **Policy Currency & Grounding:** Customer-facing guidance citing store policy must rely only on active, currently effective, non-superseded policies evaluated against Vietnam calendar time. | `Proposed` (`Observed`) | `services/gateway/src/guardrails.py`, `services/document_service/src/policy_manager.py` |
| `BR-005` | **Accurate Auditability & Vietnam Time Convention:** All new operational timestamps (sessions, turns, telemetry logs, policy audit trails, order cancellations) must reflect real Vietnam time (`Asia/Ho_Chi_Minh`, `UTC+07:00`) without the legacy `+12 hours` artificial shift, while preserving existing historical records untouched. | `Confirmed` | Owner decision; `contracts/schemas.py`, `docs/architecture/overview.md` §5.2 |
| `BR-006` | **Role-Based Portal & Workbench Separation:** Customers interact via a Customer Portal (`/customer`), while CS staff manage assigned customers, live/copilot chat, policies, audit notifications, and telemetry via a Staff Workspace (`/staff`). | `Proposed` (`Observed`) | `frontend/src/App.tsx`, `services/gateway/src/routers/rbac_router.py` |

---

## 3. Functional Requirements

### 3.1 User Interfaces (`FR-UI-*`)

| ID | Requirement | Status | Source / Evidence |
| --- | --- | --- | --- |
| `FR-UI-001` | **Primary React/Vite UI:** Provide role selection (`/`), Customer Portal (`/customer`), and Staff Workspace (`/staff`) with tabs for Copilot Chat, Customer Management, Policy Management, Audit Notifications, Telemetry Dashboard, and Evaluation Dashboard, communicating with API Gateway via `/api/v1/copilot/*`. | `Confirmed` (`frontend/` primary); features `Observed` | Owner decision; `frontend/src/App.tsx`, `frontend/src/lib/api-client.ts` |
| `FR-UI-002` | **Legacy Streamlit UI Retention:** Keep `services/ui_service/` functional for existing Docker Compose and `run_dev.py` workflows (Chat, Policy Management, Audit Notifications, Telemetry) without deleting or forcing container migration in this phase. | `Confirmed` | Owner decision; `services/ui_service/src/app.py`, `docker-compose.yml` |
| `FR-UI-003` | **Streaming & Immediate Acknowledgement UX:** Support an immediate customer buffer acknowledgement (`/api/v1/copilot/fast_ack`) and SSE token streaming (`/api/v1/copilot/query_stream`) with graceful fallback to non-streaming `/api/v1/copilot/query`. | `Proposed` (`Observed`) | `services/gateway/src/main.py`, `services/conversation_service/src/main.py` |
| `FR-UI-004` | **Accurate Model & Component Attribution in UI:** Display active component/model labels derived from backend telemetry (`components_used`) without hardcoding stale model names (e.g. removed `openai-gpt-oss-20b`). | `Confirmed` (`Observed` in `ChatView.tsx` & `conversation_service`) | `frontend/src/features/chat/ChatView.tsx`, `services/conversation_service/src/main.py` |

### 3.2 Intent Classification (`FR-INT-*`)

| ID | Requirement | Status | Source / Evidence |
| --- | --- | --- | --- |
| `FR-INT-001` | **Primary CKEY.VN LLM Classifier:** Classify customer queries using LLM as primary backend via CKEY.VN (`LLM_PROVIDER=openai_compatible`, `OPENAI_BASE_URL=https://api.xah.io/v1`, `OPENAI_MODEL=mainnewnol/gpt-oss-120b`, `INTENT_BACKEND=llm`). | `Confirmed` | Owner decision; `.env.example`, `services/intent_service/src/llm_classifier.py`, `predictor.py` |
| `FR-INT-002` | **LLM-Primary -> ML-Fallback -> Safe Abstention Hierarchy:** When primary LLM succeeds (including returning `out_of_scope`), return its prediction without ML override. When LLM is unavailable (missing keys, network/HTTP error, or parse failure), fall back to local ML (`_predict_ml`) **only if** valid ML artifacts are loaded (`has_ml_artifacts`). If both LLM and ML are unavailable, return `unknown_query` (`confidence=0.0`, `is_in_scope=False`, `model_name="unavailable_fallback"`) so downstream guardrails escalate to human support. | `Confirmed` | Owner decision; `services/intent_service/src/predictor.py`, `tests/test_architecture_decisions_alignment.py` |
| `FR-INT-003` | **No Unapproved Provider Switching:** Do not silently fall back to Gemini or other external providers when `LLM_PROVIDER=openai_compatible` and CKEY.VN is unavailable. | `Confirmed` | Owner decision; `services/intent_service/src/llm_classifier.py`, `services/rag_service/src/generator.py`, `copilot_draft_engine.py` |
| `FR-INT-004` | **Intent Backend Observability:** Record the actual backend/model used in `IntentPredictionResponse.model_name` (e.g., `mainnewnol/gpt-oss-120b`, `legacy_baseline`, `semantic_rule_fallback`, `unavailable_fallback`) and expose `model_loaded`, `ml_artifacts_loaded`, and `intent_backend` via `GET /health`. | `Confirmed` (`Observed`) | `services/intent_service/src/main.py`, `predictor.py` |
| `FR-INT-005` | **Bilingual & Unaccented Vietnamese Support:** Support Vietnamese (including unaccented/typo normalization via `normalizer.py`) and English queries across the confirmed **16** canonical `TARGET_INTENTS` (`pipeline/dataset.py`) + `out_of_scope` (`OD-004` resolved and aligned in `llm_classifier.py` and `tracker.py`). | `Confirmed` (`OD-004`) / `Observed` | `services/intent_service/src/normalizer.py`, `llm_classifier.py`, `pipeline/dataset.py`, `tests/test_intent_llm.py` |

### 3.3 Dialogue Orchestration, Retrieval & Drafting (`FR-DLG-*`, `FR-RAG-*`, `FR-ORD-*`)

| ID | Requirement | Status | Source / Evidence |
| --- | --- | --- | --- |
| `FR-DLG-001` | **Multi-Turn Dialogue State & Persistence:** Persist conversation sessions and turns in SQLite (`copilot_conversations.sqlite3`), maintain active intent/order/facts across turns, perform contextual query rewriting (`QueryRewriter`), and support live-chat handover mode. | `Proposed` (`Observed`) | `services/conversation_service/src/main.py`, `sqlite_state_store.py`, `tracker.py` |
| `FR-DLG-002` | **Gateway Standalone Fallback:** When `conversation_service` is unreachable, Gateway `/api/v1/copilot/query` executes a degraded single-turn pipeline calling `intent_service`, `telemetry_service`, and `rag_service` (`/retrieve` JSON array + `/generate`) protected by Gateway guardrails. | `Confirmed` (safe fallback) / `Observed` | `services/gateway/src/main.py`, `services/gateway/src/clients.py`, `tests/test_gateway_rag_fallback.py` |
| `FR-RAG-001` | **Policy Retrieval (`POST /retrieve`):** Retrieve top-k candidate `RetrievedDocument` records as a JSON array using `RETRIEVAL_METHOD=bm25` by default (supporting `tfidf`, `dense`, `hybrid`, `reranked`), while flagging/filtering expired or superseded policy traps. | `Proposed` (`Observed`) | `services/rag_service/src/main.py`, `retriever.py`, `README.md` |
| `FR-RAG-002` | **Citation-Grounded Draft Generation:** Draft Vietnamese CS responses citing `[doc_id]` using CKEY.VN LLM (`mainnewnol/gpt-oss-120b`), falling back to deterministic citation-grounded templates/macros if LLM is unavailable (`no_citations_available`, `llm_timeout`, `all_llm_providers_failed`). | `Confirmed` (provider/safe fallback) / `Observed` | `services/rag_service/src/generator.py`, `services/conversation_service/src/policies/copilot_draft_engine.py` |
| `FR-ORD-001` | **Order Lookup & Cancellation:** Look up order records by `order_id`, `phone`, `tracking_code`, or `customer_id` via `telemetry_service` (SQLite + LRU cache, with local `OrderTools` fallback in `conversation_service`), and allow cancellation via `POST /orders/{order_id}/cancel` only when order status permits (`can_cancel` / not `cancelled`/`delivered`/`shipping`). | `Proposed` (`Observed`) | `services/telemetry_service/src/repository.py`, `services/conversation_service/src/tools/order_tools.py` |

### 3.4 Policy Lifecycle, Telemetry & Audit (`FR-POL-*`, `FR-TEL-*`)

| ID | Requirement | Status | Source / Evidence |
| --- | --- | --- | --- |
| `FR-POL-001` | **Policy Authoring, Parsing & Sync:** Support creating, updating, deleting, and bulk-filtering policies from raw text or uploaded files (`.docx`, `.txt`, `.json`, `.md`, `.csv`), automatically computing `is_active` against `get_vn_today()`, recording lifecycle audit snapshots (`CREATE`, `UPDATE`, `SUPERSEDE`, `AUTO_EXPIRE`, `AUTO_ACTIVATE`, `ROLLBACK`, `DELETE`), supporting rollback, and triggering `rag_service /api/v1/rag/sync-kb`. | `Proposed` (`Observed`) | `services/document_service/src/policy_manager.py`, `policy_filter.py`, `routers/document_router.py` |
| `FR-TEL-001` | **Interaction Audit & Review Metrics:** Persist interaction telemetry (`POST /audit/log`) and staff review actions (`POST /audit/action` requiring non-empty `final_text` for `APPROVE`/`EDIT`), computing normalized Levenshtein edit distance, rubber-stamping flags, and continual-learning candidacy; expose aggregate stats via `/audit/stats`. | `Proposed` (`Observed`) | `services/telemetry_service/src/main.py`, `repository.py`, `metrics.py` |
| `FR-TEL-002` | **Continual Learning Dataset Export:** Append interaction records in background to `data/continual_learning_dataset.csv` and provide extraction utilities for offline training review. | `Observed` (cross-boundary script import) | `services/conversation_service/src/main.py`, `scripts/export_continual_learning_dataset.py` |

---

## 4. Non-Functional Requirements

| ID | Category | Requirement | Target / Status | Source / Evidence |
| --- | --- | --- | --- | --- |
| `NFR-SEC-001` | Security (TLS) | Enforce TLS certificate verification (`verify=True`) by default for all HTTP/HTTPS LLM clients (`contracts/llm_failover.py`, `llm_classifier.py`, `generator.py`, `copilot_draft_engine.py`), with optional CA bundle via `LLM_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, or `SSL_CERT_FILE` (fail-closed if file missing). | `Confirmed` (Implemented locally; online CKEY.VN handshake unverified) | Owner decision; `tests/test_architecture_decisions_alignment.py` |
| `NFR-SEC-002` | Security (Secrets & Offline Isolation) | Keep API keys strictly in environment/ignored `.env` (no hardcoded keys or disclosure in logs/tests/docs). `DISABLE_EXTERNAL_LLM=true` must guarantee zero outbound LLM HTTP calls. | `Confirmed` / `Observed` | `contracts/llm_failover.py`, `tests/test_llm_failover_and_offline_isolation.py` |
| `NFR-TIME-001` | Time Consistency | Use `Asia/Ho_Chi_Minh` (`UTC+07:00`) real time with zero `+12 hours` offset; write timezone-aware ISO 8601 (`+07:00`) for new records; distinguish legacy UTC naive (`telemetry_logs`) vs. legacy wall-clock strings at read/sort/display time without batch-migrating history. | `Confirmed` | Owner decision; `contracts/schemas.py`, `frontend/src/lib/time.ts`, `repository.py`, `sqlite_state_store.py` |
| `NFR-REL-001` | Reliability & Fail-Closed | Downstream outages (LLM, Intent, RAG, Conversation Service) must degrade safely to human escalation or deterministic templates without crashing ingress endpoints. | `Confirmed` (safe fallback) / `Observed` | `services/gateway/src/main.py`, `services/conversation_service/src/main.py` |
| `NFR-REL-002` | Availability & Circuit Breaker | Production availability SLA: **`TBD`** (`OD-006`). `CircuitBreaker` (`services/gateway/src/circuit_breaker.py`, default fail max `3`, reset `30s`) is now wired into Gateway primary `conversation_service` delegation (`/api/v1/copilot/query`, `/query_stream`, `/health`) and populates `GatewayResponse.circuit_breaker_tripped` (`OD-007`). | `TBD` (SLA) / `Implemented` (`CircuitBreaker`) | `services/gateway/src/circuit_breaker.py`, `main.py`, `tests/test_contracts_and_integration.py` |
| `NFR-PERF-001` | Performance & Latency | Production end-to-end latency SLA: **`TBD`**. *Observed local/eval references only (not confirmed SLAs):* `README.md` cites CPU retrieval experiment target `p95 < 15 ms` (BM25 `< 1 ms`); `run_release_gates.py` sets P90 intent inference warning at `> 2500 ms`; `fast_ack` targets sub-50ms buffer response in docstring; Gateway HTTP timeouts are `10s` (general) / `35s` (RAG generate) / `60s` (Conversation proxy). | `TBD` (`Observed` code/eval values only) | `README.md`, `evaluation/run_release_gates.py`, `services/gateway/src/clients.py` |
| `NFR-QUAL-001` | ML / Behavioral Quality | Confirmed production accuracy/F1 targets: **`TBD`**. *Observed eval gates only (not confirmed product SLAs):* `run_release_gates.py` uses `typo_acc >= 75%`, `macro_f1 >= 60%`, `MFT >= 80%`, `INV >= 75%`, `DIR >= 85%`. Note: `artifacts/models/intent/` currently has no deployed Module 1 model (`ML-model/` contains legacy `1.6.1` pickle). | `TBD` (`Observed` eval gates only) | `evaluation/run_release_gates.py`, `docs/architecture/overview.md` §5.1 |
| `NFR-COST-001` | Cost & Token Budget | Monthly LLM API budget, token caps per request, and fallback rate thresholds: **`TBD`** (`max_tokens` observed in code: `2048` in `llm_classifier.py`, `4096` in `generator.py` and `copilot_draft_engine.py`, `150` in `tracker.py`). | `TBD` | `services/intent_service/src/llm_classifier.py`, `rag_service/src/generator.py` |
| `NFR-OBS-001` | Observability | Every microservice exposes `GET /health`; Gateway/Conversation responses populate `components_used`, `guardrail`, `retrieval_status`, and `interaction_id` for trace auditing. | `Observed` / `Proposed` | All `services/*/src/main.py`, `contracts/schemas.py` |

---

## 5. Safety & Business Constraints (`Observed` vs. `Confirmed`)

> **Important:** The safety rules below are **observed** in the current implementation (`services/gateway/src/guardrails.py`, `services/conversation_service/src/policies/`). While the overarching *fail-closed / safe-fallback principle* is **`Confirmed`**, the exact intent lists, numeric thresholds, and regex rules require formal business sign-off before being treated as immutable product specifications.

| ID | Constraint | Current Behavior (`Observed`) | Product Confirmation Status |
| --- | --- | --- | --- |
| `SC-001` | **Financial Intent Interception** | Intents in `FINANCIAL_INTENTS` (`{"request_refund", "payment_issue"}`) block LLM generation (`allow_llm=False`, `action_type="DIRECT_REFUND_FORM"`). | Principle `Confirmed`; exact intent set `Proposed` |
| `SC-002` | **Runtime Financial Promise Gate** | `evaluate_runtime_safety_envelope()` blocks LLM drafts containing monetary refund/compensation promises unless `order_data.status` is in `{"REFUND_PENDING", "CANCELLED", "RETURN_APPROVED"}` (`is_hard_fail=True`). | `Observed` / `Proposed` |
| `SC-003` | **Intent Scope, Unavailable & Confidence Gate** | `out_of_scope`, `human_agent`, `unknown_query`, `unavailable_fallback`, invalid/NaN confidence, `is_in_scope=False`, or in-scope confidence `< INTENT_CONFIDENCE_THRESHOLD` (`0.60` default unified across Gateway, Conversation Tracker, and Dispatcher; bypassable only for low-confidence in-scope queries if `DISABLE_CONFIDENCE_GUARD=true`) escalate to `ESCALATE_HUMAN`. `is_in_scope` is strictly decoupled from confidence and checks canonical 16-intent membership (`contracts/safety.py`). | `Confirmed` (unified `0.60` + scope separation, `OD-005`) |
| `SC-004` | **Temporal & Superseded Policy Guard** | `policy_type="superseded"` is always blocked; `is_active=False` is always blocked; `temporary` policies require valid `effective_date` and `expiration_date` and must include `get_vn_today()`; `permanent` policies ignore missing `expiration_date`. | `Observed` / `Proposed` |
| `SC-005` | **Response Faithfulness / Hallucination Gate** | Both Gateway fallback and Conversation Service primary path (`/chat` and `/chat_stream`) invoke shared `contracts/safety.py` faithfulness & numeric-grounding checks against `citations` + `order_data` (`FAITHFULNESS_THRESHOLD=0.70`), blocking ungrounded claims or fabricated numbers (`ESCALATE_HUMAN`, `is_hard_fail=True`). | `Confirmed` (`OD-005` parity implemented) |
| `SC-006` | **Prompt Injection Defense** | `evaluate_prompt_injection()` blocks jailbreak/system-prompt-disclosure regex patterns pre- and post-generation (`ESCALATE_HUMAN`, `is_hard_fail=True`). | `Observed` / `Proposed` |
| `SC-007` | **Human Review Audit Integrity** | `telemetry_service` rejects `APPROVE` or `EDIT` actions with blank `final_text` (`HTTP 422`), computes edit distance, and flags rubber-stamping (`detect_rubber_stamping`). | `Observed` / `Proposed` |

---

## 6. Acceptance Criteria for Key Requirements

| AC ID | Covers | Acceptance Criteria (Verifiable Condition) | Current Verification Evidence |
| --- | --- | --- | --- |
| `AC-INT-001` | `FR-INT-001`, `FR-INT-002` | **Given** an operational query and an available CKEY.VN LLM response (including `out_of_scope`), **when** `IntentPredictor.predict()` runs in `llm` or `hybrid` mode, **then** the LLM result is returned with its actual `model_name` and ML fallback is not invoked. | Verified with mocked HTTP (`test_architecture_decisions_alignment.py`); live CKEY.VN call pending |
| `AC-INT-002` | `FR-INT-002`, `FR-INT-004` | **Given** primary LLM is unavailable and valid ML artifacts are loaded (`has_ml_artifacts=True`), **when** `IntentPredictor.predict()` runs, **then** it falls back to `_predict_ml()`, sets an ML `model_name`, and makes zero calls to Gemini. | Verified with mocked ML/LLM (`test_architecture_decisions_alignment.py`); real Module 1 ML artifacts pending |
| `AC-INT-003` | `FR-INT-002`, `BR-002`, `SC-003` | **Given** both LLM and ML artifacts are unavailable, **when** a query enters `IntentPredictor`, `ConversationService` (even on turn 2 with prior `active_intent`), or `Gateway` fallback, **then** `intent="unknown_query"`, `confidence=0.0`, `is_in_scope=False`, `model_name="unavailable_fallback"`, and guardrail returns `allow_llm=False`, `action_type="ESCALATE_HUMAN"`. | Verified offline (`test_architecture_decisions_alignment.py`) |
| `AC-GW-001` | `FR-DLG-002`, `FR-RAG-001` | **Given** `conversation_service` is unreachable and `rag_service /retrieve` returns a JSON array `[...]`, **when** `POST /api/v1/copilot/query` executes, **then** Gateway parses citations into `List[RetrievedDocument]`, passes `evaluate_policy_guard`, and returns grounded `draft_text`; if `/retrieve` returns `[]`, Gateway escalates via `blocked_policy_guard`. | Verified with `httpx.MockTransport` (`test_gateway_rag_fallback.py`) |
| `AC-TIME-001` | `BR-005`, `NFR-TIME-001` | **Given** system clock time, **when** new sessions, turns, telemetry audit logs, order cancellations, or policy audit logs are created, **then** timestamps use real `Asia/Ho_Chi_Minh` (`+07:00`) with zero `+12h` shift, legacy UTC `telemetry_logs` and naive sessions sort chronologically across midnight, and historical stored rows remain unmodified. | Verified offline (`test_architecture_decisions_alignment.py`, `frontend` `tsc --noEmit`) |
| `AC-SEC-001` | `NFR-SEC-001`, `NFR-SEC-002` | **Given** default configuration without custom CA env vars, **when** OpenAI-compatible or Gemini HTTP clients execute, **then** `verify=True` is passed; if `LLM_CA_BUNDLE` is set to a valid file it is used, if missing on disk `FileNotFoundError` is raised; and `DISABLE_EXTERNAL_LLM=true` produces zero outbound LLM HTTP calls. | Verified offline with mocks (`test_architecture_decisions_alignment.py`, `test_llm_failover_and_offline_isolation.py`) |
| `AC-SAF-001` | `BR-003`, `SC-001`..`005` | **Given** financial intents (`request_refund`, `payment_issue`), expired/superseded policy citations, prompt injection payloads, or fabricated numerical claims in Gateway fallback, **when** guardrails evaluate the request/draft, **then** `allow_llm=False` and `DIRECT_REFUND_FORM` or `ESCALATE_HUMAN` is returned. | Verified offline (`test_guardrails.py`, `test_robustness.py`, `test_mlip_evaluation.py`) |

---

## 7. Assumptions & Open Decisions

### Assumptions (`ASM-*`)
Detailed unverified assumptions, evidence, impact, verification plans, and priorities are maintained canonically in [docs/assumptions.md](../assumptions.md) (`ASM-001`..`ASM-007`) to avoid duplication.

### Open Decisions (`OD-*` — Owner Input Required)
- `OD-001` (**UI Deployment Roadmap**): Should React (`frontend/`) eventually replace Streamlit (`ui_service`) inside `docker-compose.yml`, and what is the deprecation plan for Streamlit?
- `OD-002` (**Module 1 ML Fallback Artifacts**): When and with which dataset/model family (ONNX PhoBERT/MiniLM vs. sklearn) will real Module 1 artifacts be trained and deployed into `artifacts/models/intent/`? (Currently only legacy `1.6.1` sklearn pickle exists in `ML-model/` / `intent_model.pkl`.)
- `OD-003` (**Online TLS Verification**): Confirm in an authorized online environment whether `https://api.xah.io/v1` validates cleanly with standard CA roots or requires configuring `LLM_CA_BUNDLE`.
- `OD-004` (**Intent Taxonomy Size — RESOLVED: 16 Canonical Intents**): Owner confirmed all **16** `TARGET_INTENTS` in `services/intent_service/src/pipeline/dataset.py` (12 core operational intents + `warranty`, `get_discounts`, `create_account`, `recover_password`) plus `out_of_scope` as the canonical product taxonomy. `llm_classifier.py`, `tracker.py`, `test_intent_llm.py`, and specs are aligned; historical Module 1 Kaggle training notes (`README_MODULE1.md` mapping `warranty` -> `out_of_scope` until new artifacts are trained under `OD-002`) remain documented as a training-data limitation.
- `OD-005` (**Guardrail Rules & Threshold Sign-Off — RESOLVED IN CODE/DOCS**): Owner approved unified `INTENT_CONFIDENCE_THRESHOLD = 0.60` (removing `0.50` divergence in `conversation_service` / `tracker.py`), decoupling `is_in_scope` cleanly via `contracts/safety.py::is_intent_in_scope`, calibrating LLM prompt/clamping `[0.0, 1.0]`, and enforcing shared `FAITHFULNESS_THRESHOLD=0.70` / numeric-grounding parity inside `conversation_service` (`evaluate_runtime_safety_envelope`). Real Module 1 ML validation cutoff selection remains tied to `OD-002`.
- `OD-006` (**Quantitative SLAs (`TBD` Targets)**): Define confirmed product acceptance targets for end-to-end latency, availability, intent/retrieval quality gates, and LLM token/cost budgets (distinct from dev/eval metric collection).
- `OD-007` (**Runtime Circuit Breaker & Contract Cleanup — RESOLVED IN CODE**): Reconciled `frontend/src/types/index.ts` optional fields (`retrieval_status`, `circuit_breaker_tripped`, `is_hard_fail`, `violations`, `all_probabilities`), removed dropped `session_id`/`latency_ms` kwargs and `"FALLBACK"` string in `conversation_service/src/main.py` (`EMPTY_RETRIEVAL`/`INSUFFICIENT_EVIDENCE`), fixed `Port 8006` docstrings, aligned `handover_session` + `/api/v1/conversation/handover`, and wired `CircuitBreaker` into live Gateway `conversation_service` delegation (`/query`, `/query_stream`, `/health`), verified in `tests/test_contracts_and_integration.py`.
- `OD-008` (**Historical Timestamp & Continual Learning Governance**): Confirm whether leaving legacy SQLite/JSON/CSV timestamps unmigrated is sufficient long-term, and define governance/PII rules for `data/continual_learning_dataset.csv`.
