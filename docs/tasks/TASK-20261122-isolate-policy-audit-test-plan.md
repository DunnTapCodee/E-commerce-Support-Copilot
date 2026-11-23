# Execution Plan: Isolate `tests/test_policy_audit_rollback.py` for Safe Offline Testing

> **Rule:** A checked milestone box indicates step completion only; it is **not** proof of verification unless backed by observed command output in Section 8. Never store secrets, API keys, PII, or full raw logs here.

---

## 1. Task Identity & Status

- **Task ID:** `TASK-20261122-isolate-policy-audit-test`
- **Task Title:** `Isolate tests/test_policy_audit_rollback.py for safe offline testing`
- **Created / Updated At:** `2026-11-22T21:48:00+07:00`
- **Task Status:** `COMPLETED`
- **Implementation Status:** `IMPLEMENTED`
- **Verification Status:** `LOCALLY_VERIFIED`
- **Approval Status:** `NOT_REQUIRED (R1 — scoped test isolation, verification doc, and reversible offline CI alignment without altering production behavior)`

---

## 2. Goal & Expected Outcome

- **Objective:** Eliminate external/local HTTP side effects (`POST {RAG_SERVICE_URL}/api/v1/rag/sync-kb`) and verify clean disk/env isolation in `tests/test_policy_audit_rollback.py` without changing `document_service` production behavior, so the test suite can run safely in deterministic offline CI.
- **Expected Outcome:**
  - `tests/test_policy_audit_rollback.py` mocks `PolicyManager.trigger_rag_sync` (via `AsyncMock`) and asserts zero outbound HTTP traffic (`httpx.AsyncClient` not called) while verifying sync invocation count/behavior on mutations, rollback, and batch expiry recomputation.
  - Observed passing local pytest run recorded in Section 8 and Handoff.
  - `docs/development/verification.md` (`FR-POL-001`, §2.1 / §2.2) reconciled with observed verification results (and `.github/workflows/ci-offline.yml` evaluated for inclusion if requested/appropriate).

---

## 3. Scope & Non-Goals

- **In Scope:**
  - `tests/test_policy_audit_rollback.py`
  - `docs/development/verification.md` (§1 `FR-POL-001`, §2.1 / §2.2)
  - Optional alignment in `.github/workflows/ci-offline.yml` (add `tests/test_policy_audit_rollback.py` to `backend-offline-tests` once offline safety is verified)
  - Task tracking docs: this Execution Plan and `docs/tasks/TASK-20261122-isolate-policy-audit-test-handoff.md`
- **Out of Scope (Non-Goals):**
  - Modifying production behavior in `services/document_service/src/policy_manager.py`, `document_router.py`, `main.py`, `policy_filter.py`, or `services/rag_service/`
  - Refactoring other unsafe/conditional tests (`test_module3_orders.py`, `test_conversation_service.py`)
  - Starting live services (`rag_service`, `document_service`) or making real LLM/network calls
  - Running `git commit`, `git push`, `git reset`, `git clean`, or deleting `docs.zip`

---

## 4. Relevant Requirements, Specifications & ADRs

- **Requirements:** `FR-POL-001` (Policy CRUD, dynamic `is_active`, audit log, rollback, RAG sync), `NFR-TIME-001` (Vietnam time `+07:00`, no `+12h` offset) — see [Requirements Baseline v1](../product/requirements.md) and [Verification Baseline v1](../development/verification.md)
- **Specifications:** None dedicated beyond [Architecture Overview v1](../architecture/overview.md) (`document_service` & `rag_service` boundaries)
- **ADRs / Architecture:** [ADR-003](../decisions/ADR-003-vietnam-time-no-12h-offset.md), [Architecture Overview v1](../architecture/overview.md)

---

## 5. Constraints & Risk Classification

- **Highest Risk Level (`R0`–`R3`):** `R1` (test-only isolation & verification doc update; updating `.github/workflows/ci-offline.yml` if included is scoped `R1`/`R2` reversible CI config — see `docs/agent/RISK_AND_APPROVAL.md`)
- **Hard Constraints:**
  - Preserve all pre-existing working tree edits and untracked files (including `AGENTS.md`, `docs/agent/*`, `docs.zip`).
  - Do **not** alter `document_service` production runtime behavior.
  - Run offline only (`DISABLE_EXTERNAL_LLM=true`, `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true`); never trigger real `rag_service` sync or touch `data/knowledge_base/policies.json` or `policy_audit_logs.json`.
- **Approval Gates Required:** `None (within authorized R1/R2 scope; request user approval only if production code or scope changes become necessary)`

---

## 6. Proposed Approach

### Verified Side-Effect Analysis (`Observed` in Session A)
1. **Unmocked HTTP RAG Sync (`Primary Blocker`):**
   - `services/document_service/src/policy_manager.py` calls `await self.trigger_rag_sync()` (HTTP `POST {RAG_SERVICE_URL}/api/v1/rag/sync-kb`, default `http://127.0.0.1:8002`) inside `create_policy`, `update_policy`, `delete_policy`, `rollback_policy`, and `recompute_all_active_statuses(trigger_rag_sync=True)`.
   - Four tests in `tests/test_policy_audit_rollback.py` currently exercise those unmocked paths:
     - `test_create_policy_auto_computes_active_and_records_audit`
     - `test_update_policy_date_automatically_recalculates_is_active`
     - `test_rollback_policy_restores_state_and_recomputes_active`
     - `test_batch_sync_active_status_detects_expired_and_logs_auto_expire`
   - If a local `rag_service` is running on port `8002`, the test silently triggers live KB re-indexing against `policies.json`.
2. **Import-Time Singleton & Unused Import (`Secondary Check`):**
   - `services/document_service/src/config.py` calls `load_dotenv(PROJECT_ROOT / ".env")` on import.
   - `services/document_service/src/policy_manager.py` instantiates module-level `policy_manager = PolicyManager()` at import time using `POLICIES_PATH` (`data/knowledge_base/policies.json`) and `AUDIT_LOGS_PATH` (`data/knowledge_base/policy_audit_logs.json`), calling `_ensure_storage_exists()` (does not overwrite existing files, but would create empty files if missing on a sparse env unless paths exist or are env-overridden).
   - `tests/test_policy_audit_rollback.py` imports `filter_raw_policy` from `policy_filter.py` (currently unused; `AsyncOpenAI` inside `policy_filter.py` is lazy, so no import-time LLM call occurs).
   - `self.client = TestClient(doc_main.app)` is instantiated without a `with` block, so FastAPI `lifespan` does not execute during `setUp`.

### Planned Isolation Design
1. In `tests/test_policy_audit_rollback.py`, patch `PolicyManager.trigger_rag_sync` (or `self.manager.trigger_rag_sync`) using `unittest.mock.patch.object(..., new_callable=AsyncMock)` inside `setUp` and clean up via `addCleanup` / `tearDown`.
2. Also guard/verify that `httpx.AsyncClient.post` is never invoked during the suite, and verify `trigger_rag_sync` call counts on create/update/rollback/sync-active-status match expected counts (`FR-POL-001`).
3. Ensure `test_policy_audit_rollback.py` runs cleanly with isolated `POLICIES_PATH` / `AUDIT_LOGS_PATH` in `setUp` or documented env overrides if needed, without altering production `policy_manager.py`.
4. Run `pytest` on `tests/test_policy_audit_rollback.py` and re-check `git status --short` + `data/knowledge_base/` to confirm zero disk/DB mutation.

---

## 7. Implementation Steps / Milestones

> Tag each step with `[PLANNED]`, `[IN_PROGRESS]`, `[IMPLEMENTED]`, `[VERIFIED]`, or `[BLOCKED]`.

- [x] **M1 (`[VERIFIED]`):** Reconcile Git/filesystem state via Handoff (`TASK-20261122-isolate-policy-audit-test-handoff.md`), inspect `tests/test_policy_audit_rollback.py` & `services/document_service/src/policy_manager.py` around `trigger_rag_sync`.
- [x] **M2 (`[VERIFIED]`):** Patch `PolicyManager.trigger_rag_sync` with `AsyncMock` and guard `httpx.AsyncClient.post` / `httpx.AsyncClient.request` in `tests/test_policy_audit_rollback.py`; also patch `doc_main.policy_manager`, align date offsets to `get_vn_today()`, remove unused imports (`os`, unused schema imports, `filter_raw_policy`), and cover `delete_policy` + no-op batch sync (`0` sync calls).
- [x] **M3 (`[VERIFIED]`):** Run isolated `pytest tests/test_policy_audit_rollback.py -v` (`10 passed in 2.86s`) and the full 8-suite offline CI `pytest` run (`75 passed in 33.25s`) with offline env vars, confirming `data/knowledge_base/` and `services/document_service/` stay untouched.
- [x] **M4 (`[VERIFIED]`):** Update `docs/development/verification.md` (`FR-POL-001`, §2.1, §2.2, §5), add `tests/test_policy_audit_rollback.py` to `.github/workflows/ci-offline.yml`, and mark Plan/Handoff `COMPLETED` / `LOCALLY_VERIFIED`.

---

## 8. Verification Strategy & Observed Evidence

- **Planned Safe Commands:**
  - `DISABLE_EXTERNAL_LLM=true DISABLE_CONTINUAL_LEARNING_CSV_EXPORT=true python -m pytest tests/test_policy_audit_rollback.py -v` (safe once `trigger_rag_sync` is mocked via `AsyncMock` and temp dir is verified)
  - `git status --short data/knowledge_base/` (confirm tracked policy/audit files remain untouched)
  - Existing deterministic CI suite listed in `docs/development/verification.md` §2.1 (run after test edits if CI workflow is updated)
- **Observed Verification Results (fill only after actual execution):**
  - `Command:` `$env:DISABLE_EXTERNAL_LLM="true"; $env:DISABLE_CONTINUAL_LEARNING_CSV_EXPORT="true"; python -m pytest tests/test_policy_audit_rollback.py -v` -> `10 passed in 2.86s` (`git status --short data/knowledge_base/` clean).
  - `Command:` `$env:DISABLE_EXTERNAL_LLM="true"; $env:DISABLE_CONTINUAL_LEARNING_CSV_EXPORT="true"; $env:CONVERSATIONS_DB_PATH="$env:TEMP\ci_copilot_conversations.sqlite3"; python -m pytest tests/test_contracts_and_integration.py tests/test_architecture_decisions_alignment.py tests/test_llm_failover_and_offline_isolation.py tests/test_gateway_rag_fallback.py tests/test_guardrails.py tests/test_rbac_step1.py tests/test_conversation_order_pipeline.py tests/test_policy_audit_rollback.py -v` -> `75 passed in 33.25s`.
  - `Command:` Static guard check (`verify=False|hours=12` across `services/`, `contracts/`, `scripts/`, `evaluation/`) -> `CLEAN: zero verify=False or hours=12` (exit code `0`).
  - `Command:` Docs internal link check (`docs/**/*.md`) -> `DOCS LINKS OK` (exit code `0`); `git diff services/document_service/` -> empty.
  - `Limitations:` `tests/test_policy_audit_rollback.py` verifies `PolicyManager` lifecycle/CRUD/audit/rollback and mocked `trigger_rag_sync` offline only; `policy_filter` LLM/heuristic parsing and live `document_service -> rag_service /api/v1/rag/sync-kb` HTTP integration remain outside offline CI scope.

---

## 9. Dependencies & Blockers

- **Active Blockers:** `None`
- **Assumptions Relied Upon:** `None (direct code inspection verified trigger_rag_sync behavior and TestClient setup)`

---

## 10. Acceptance Criteria / Definition of Done

- [x] `tests/test_policy_audit_rollback.py` executes zero outbound HTTP requests (`trigger_rag_sync` mocked and verified; `httpx.AsyncClient.post` and `httpx.AsyncClient.request` uncalled).
- [x] `python -m pytest tests/test_policy_audit_rollback.py -v` passes completely under `DISABLE_EXTERNAL_LLM=true` without modifying `data/knowledge_base/`.
- [x] `services/document_service/` production code remains unchanged.
- [x] `docs/development/verification.md` accurately reflects the updated verification status of `tests/test_policy_audit_rollback.py` (and `.github/workflows/ci-offline.yml` includes it in `backend-offline-tests`).
- [x] `git status --short` shows only intended task changes while preserving all prior edits and `docs.zip`.

---

## 11. Decisions & Plan Changes Log

- `2026-11-22T21:42:00+07:00` — Created Execution Plan in Session A as part of Cross-Session Pilot preparation. Deliberately deferred code/test edits to Session B to validate cross-session recovery via Session Handoff.
- `2026-11-22T21:48:00+07:00` — Completed Session B execution: isolated `tests/test_policy_audit_rollback.py` (`10 passed`), aligned `docs/development/verification.md` and `.github/workflows/ci-offline.yml`, verified all 8 offline CI suites (`75 passed`), and preserved all pre-existing edits (`AGENTS.md`, `docs/agent/*`, `docs.zip`). Note: `docs/agent/REPO_GUIDE.md:45` still mentions `test_policy_audit_rollback.py` in its historical parenthetical summary and was left untouched per pre-existing edit protection.
