# Task Execution Protocol — v0.2 (Active Baseline v1)

> Task complexity and duration determine planning/handoff overhead; risk level (`RISK_AND_APPROVAL.md`) determines approval authority and verification depth. For repository-specific navigation use `REPO_GUIDE.md`, and for authoritative test/side-effect rules use `docs/development/verification.md`.

## Intake

Identify the observable goal, acceptance criteria, scope/non-goals, constraints, and any unknown that materially affects correctness or safety. For a small clear change, do this briefly; do not manufacture a large task contract.

## Preflight

- Inspect branch/working tree and preserve pre-existing edits, untracked files, and generated artifacts.
- Discover implementation, callers, relevant tests, and current configuration incrementally.
- Identify invariants, public contracts, data ownership, and relevant documentation; record conflicts rather than silently choosing a side.
- Classify each planned command and edit for risk and side effects before executing.

## Execution paths

| Path | When useful | Required planning overhead |
| --- | --- | --- |
| Fast | Small, clear, single-session, low blast radius | Inline intention; **no** persistent plan or handoff file and no lengthy report |
| Standard | Several steps, nontrivial bug or multiple modules finished in one session | Short inline plan with expected edits, risks, and tests; persistent handoff only if paused/blocked |
| Extended | Multi-session, major cross-boundary/architectural work or sensitive migration design | Durable task-specific plan (`docs/agent/templates/EXECUTION_PLAN.md`), milestones, acceptance criteria, and handoff (`SESSION_HANDOFF.md`) when pausing |

Risk rules apply independently of path: `R2` work within already-authorized scope does **not** require step-by-step approval (only proportionate consumer/verification checks), while `R3` and explicit approval gates (`RISK_AND_APPROVAL.md`) always require specific authorization. Replan if evidence changes assumptions or risk.

## Implementation loop

- **Bug:** observe/reproduce where feasible → find root cause → add meaningful regression evidence → implement smallest coherent fix → verify.
- **Feature:** establish behavior and negative cases → inspect established patterns → implement increments → verify each coherent slice.
- Avoid test-specific hardcoding, unrelated refactors, unapproved interface changes, or modifications to existing user work.
- If unable to reproduce, report confidence and alternative evidence; do not invent a successful reproduction.

## Verification

Select the smallest meaningful test set based on touched surfaces, then broaden for shared contracts, safety controls, or regressions. Prefer evidence from the final code state. Before invoking any test, inspect side effects and isolation. Do not assume a command is safe solely because a previous review categorized it as offline.

| Touched area | Typical evidence |
| --- | --- |
| UI | Typecheck and build; interactions, accessibility/responsiveness if relevant |
| Shared contracts/API | Schema tests; all important consumers; contract/integration checks |
| Backend | Focused unit and error-path tests; affected integrations |
| Security/financial/temporal policy | Positive/negative authorization and safety cases; audit behavior |
| RAG/ML | Reproducible evaluation dataset, grounding, behavioral regressions and latency |
| Storage | Isolated persistence tests, migration checks, recovery/data consistency |

Distinguish `IMPLEMENTED`, `LOCALLY_VERIFIED`, `INTEGRATION_VERIFIED`, `READY_FOR_REVIEW`, `ACCEPTED`, and `DEPLOYED`. These are different claims; test passes do not automatically imply approval or deployment.

## Reporting and handoff

- **Fast:** one or two concise sentences: changed behavior, checks run/results, and blockers if any.
- **Standard:** summarize change, verification evidence, remaining risk/unknowns, and follow-up.
- **Extended:** keep a task-scoped status document with goal, approved scope, branch/base, decisions, work done, actual test results, blockers, and next actions.

Do not create a handoff file for a finished trivial task. For progressive context loading, Execution Plan / Session Handoff triggers, the 5-step Session Recovery Protocol, and the 4-axis progress model (without a global `PROGRESS.md`), follow `docs/agent/CONTEXT_AND_MEMORY.md` and use the reusable templates in `docs/agent/templates/EXECUTION_PLAN.md` and `docs/agent/templates/SESSION_HANDOFF.md`. When resuming a task, always reconcile any handoff snapshot against current Git state and actual code; prior test results may be stale.

## Example (Historical — Resolved Illustrative Pattern)

When investigating an inter-service contract bug (such as the historical Gateway/RAG `/retrieve` JSON array vs. `{"documents": []}` mismatch), compare the provider endpoint's actual JSON response against the client parser, add a mock-HTTP regression test, and verify downstream consumers before marking the fix `LOCALLY_VERIFIED` (resolved in `services/gateway/src/clients.py` and `tests/test_gateway_rag_fallback.py`).
