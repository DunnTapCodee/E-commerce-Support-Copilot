# E-commerce-Support-Copilot — Repository Guide (v0.2 — Baseline v1)

> **Status:** Active Project-Specific Adapter for Agent Harness v0.2, aligned with Project Knowledge System v1 and Verification Baseline v1. Always check live Git (`git status --short`, current branch, `HEAD`) and current code/config before acting. This document routes navigation and risk awareness; canonical requirements, decisions, and verification rules live in the linked documents below.

## Repository snapshot and navigation

- `services/gateway/` — HTTP entrypoint (`:8000`), routing, guardrails, RBAC.
- `services/conversation_service/` — multi-turn conversation state and orchestration (`:8006`).
- `services/intent_service/` — intent classification (`:8005`: LLM primary -> ML fallback -> fail-closed abstention).
- `services/rag_service/` — policy retrieval (`:8002`, JSON array `/retrieve`) and grounded drafting (`/generate`).
- `services/document_service/` — policy lifecycle (`:8004`) and RAG KB synchronization.
- `services/telemetry_service/` — orders, audit logs, RBAC data (`:8003`).
- `services/ui_service/` — Legacy Streamlit UI (`:8501`, retained in Docker Compose per `ADR-001`).
- `frontend/` — **Confirmed Primary UI** (`:5173`, React/Vite/TypeScript SPA per `ADR-001`).
- `contracts/` — shared Pydantic DTOs, Vietnam timezone helpers (`ADR-003`), and TLS-verified LLM failover client (`ADR-004`).
- `tests/`, `evaluation/` — unit, contract, mocked integration, and MLIP evaluation suites.
- `reports/`, `data/`, `artifacts/` — runtime/eval outputs and artifacts; do not treat them as disposable.
- `docs/architecture/overview.md` — Architecture Overview v1 (boundaries, storage, LLM config audit, and known code/doc mismatches).
- `docs/product/requirements.md` — Requirements Baseline v1 (goals, requirements, safety constraints, acceptance criteria, and open decisions `OD-001`..`OD-008`).
- `docs/specs/intent-classification.md` & `docs/specs/copilot-workflow.md` — Implementable specifications.
- `docs/assumptions.md` — Canonical Assumptions Register (`ASM-001`..`ASM-007`).
- `docs/decisions/` — Architecture Decision Records (`ADR-001` UI, `ADR-002` Intent LLM/ML fallback, `ADR-003` Vietnam timezone, `ADR-004` TLS verification).
- `docs/development/verification.md` — **Canonical Verification Matrix, test side-effect classification, safe offline/CI commands, and AI/ML eval blockers.**
- `docs/agent/CONTEXT_AND_MEMORY.md` & `docs/agent/templates/` (`EXECUTION_PLAN.md`, `SESSION_HANDOFF.md`) — Reusable Core protocol and templates for progressive context loading, task memory, and cross-session recovery.
- `.agents/skills/`, `scripts/validate_skills.py`, `docs/agent/SKILLS_AND_AUTOMATION.md` — Repository-scoped Agent Skills (`repo-onboarding`, `task-resume`, `change-impact-analysis`), stdlib skill validator, activation evals, and hooks/subagents assessment.
- `docs/agent/AGENT_EVALUATION.md`, `evaluation/agent_harness/` — Coding Agent Harness evaluation protocol, task manifest, deterministic graders, and offline smoke runner (distinct from product AI/ML evaluations in `evaluation/*.py`).

## Sensitive paths — assess consumers and side effects first

| Area | Why sensitive |
| --- | --- |
| `contracts/schemas.py` | Shared DTOs; divergence remains with `frontend/src/types/index.ts` and `conversation_service` extra kwargs (`OD-007`). *Historical note:* legacy `+12 hours` shift in `get_system_now()` was removed per `ADR-003` (`Asia/Ho_Chi_Minh`, `+07:00`). |
| `services/gateway/src/guardrails.py` | Financial, temporal, and faithfulness invariants (`SC-001`..`SC-006`); changes alter safety behavior. |
| `services/document_service/src/policy_manager.py` | Mutates policy JSON/audit files and triggers RAG KB synchronization. |
| `services/conversation_service/src/main.py` | Stateful SQLite orchestration and background continual-learning CSV writes (`scripts/export_continual_learning_dataset.py`, PII-redacted + disableable via `DISABLE_CONTINUAL_LEARNING_CSV_EXPORT`). |
| `services/gateway/src/clients.py` | Inter-service HTTP client wrapper. *Historical note:* `/retrieve` JSON array parsing mismatch was fixed and covered by `tests/test_gateway_rag_fallback.py`. |

### Security status & historical credential warning (never reproduce secrets)

- **Resolved in current code (`Observed`, `ADR-004`):** `DEFAULT_KEYS` was removed from `contracts/llm_failover.py`, and all `verify=False` TLS bypasses were replaced with `verify=True` (plus optional `LLM_CA_BUNDLE` / `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE`) across `contracts/llm_failover.py`, `services/intent_service/src/llm_classifier.py`, and `services/rag_service/src/generator.py`.
- **Historical exposure warning (remains active):** Any real credentials that previously appeared in Git history must still be treated as potentially compromised until rotated/revoked by the owner and Git history exposure is reviewed. Never copy secrets into chat, issues, tests, handoffs, or artifacts, and never use `verify=False` as a workaround.

## Verification routing (Single Source of Truth)

**Do not maintain a separate test list here.** Consult [docs/development/verification.md](../development/verification.md) as the authoritative source for:
- Confirmed safe deterministic offline & CI test commands (with `DISABLE_EXTERNAL_LLM=true` and temp DB isolation).
- Tests excluded from default CI due to side effects (`test_module3_orders.py` mutates root `copilot_telemetry.sqlite3`; `test_policy_audit_rollback.py` calls unmocked `/sync-kb`; `test_conversation_service.py` initializes root DB on import; `evaluation/run_release_gates.py` overwrites `reports/mlip_release_gates_results.json`).
- Frontend TypeScript check (`tsc --noEmit`), docs link checks, and AI/ML evaluation blockers.

Always check side effects and isolation before running any command; never treat a full `pytest` run or live service startup as harmless by default.

## Historical baseline context (0e471a1 survey — Historical Only)

> **Historical note:** An earlier read-only survey at `0e471a1` (`refine`, 2026-11-21) documented pre-existing working tree edits (moved lecture docs, `policy_index.pkl`, `continual_learning_dataset.csv`). Subsequent work progressed on branch `harness` (`d3b2e8b`). **Do not rely on historical snapshots:** run `git status --short`, `git rev-parse --abbrev-ref HEAD`, and `git rev-parse --short HEAD` on every session and preserve any existing working tree edits unless explicitly authorized.

## Documentation status

- `README.md` still reflects the Streamlit-centric Compose quick start and older policy counts (`47` vs `51` total / `48` active in `policies.json`).
- `services/intent_service/README_MODULE1.md` assumes trained artifacts in `artifacts/models/intent/` (currently only `.gitkeep` is present; legacy sklearn `1.6.1` pickle exists in `ML-model/`).
- Historical `reports/*.md` may be stale on service count, UI, and config defaults.

Use current code/config to verify runtime behavior and `docs/product/requirements.md` / `docs/specs/*` for intended behavior.

## Confirmed decisions & remaining open decisions

### Confirmed decisions (implemented/documented in Baseline v1)
1. **Primary UI (`ADR-001`):** React/Vite (`frontend/`) is the official primary UI; Streamlit (`services/ui_service/`) is retained as legacy/reference without deleting it or changing Compose UI deployment yet.
2. **Intent Classification (`ADR-002`):** `LLM primary -> ML fallback (only when valid artifacts loaded) -> fail-closed human escalation` using CKEY.VN (`https://api.xah.io/v1`, `mainnewnol/gpt-oss-120b`), with no silent Gemini fallback.
3. **Time Handling (`ADR-003`):** `+12 hours` shift removed; real Vietnam time (`Asia/Ho_Chi_Minh`, `+07:00`) used for new records without batch-migrating history.
4. **TLS Security (`ADR-004`):** `verify=True` enabled by default with optional CA bundle support (`LLM_CA_BUNDLE`, `REQUESTS_CA_BUNDLE`, `SSL_CERT_FILE`).

### Open decisions (do not guess — see `docs/product/requirements.md` §7)
1. Branch integration workflow: `main` (stable), `refine` (integration), `feature/*`, `fix/*`, `docs/*` proposed — confirm CI/merge rules before acting.
2. Whether/when to containerize `frontend/` in `docker-compose.yml` (`OD-001`) and deploy trained Module 1 artifacts into `artifacts/models/intent/` (`OD-002`).
3. Online TLS handshake verification for `https://api.xah.io/v1` (`OD-003`, `ASM-001`).
4. Canonical intent taxonomy (`12` vs `16`, `OD-004`), guardrail threshold/parity sign-off (`OD-005`), quantitative SLAs (`OD-006`), contract/CircuitBreaker cleanup (`OD-007`), and historical timestamp / CSV Git-tracking policy (`OD-008`).

## Reference checks for cross-repo or adoption tasks

Re-check `docker-compose.yml`, `run_dev.py`, `frontend/package.json`, `docs/development/verification.md`, relevant `contracts/schemas.py` models, and current Git state before making cross-boundary changes.
