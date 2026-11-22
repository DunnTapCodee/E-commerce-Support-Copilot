# Task Execution Protocol — v0.2 candidate

> The level of process should be proportional to complexity and impact. Risk classification is defined in `RISK_AND_APPROVAL.md`, and repo-specific verification candidates in `REPO_GUIDE.md`.

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
| Fast | Small, clear, reversible, low blast radius | Inline intention; no task file and no multi-section report |
| Standard | Several steps, nontrivial bug or multiple modules | Short plan with expected edits, risks, and tests, typically in the conversation |
| Extended | Multi-session, major cross-boundary/architectural work or sensitive migration design | Durable task-specific plan, milestones, acceptance criteria, checkpoints, rollback assumptions, and handoff |

R3 actions require approval regardless of path. Replan if evidence changes assumptions or risk.

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

Do not create a handoff file for a finished trivial task. When resuming a task, reconcile handoff against current Git state and actual code; prior test results may be stale.

## Example (illustrative only)

A reported Gateway/RAG response mismatch can be investigated by comparing the endpoint's actual JSON response with its client parser, then adding a regression test and checking downstream consumers. The repository review identified this as a concrete **investigation lead**; it still needs executable evidence before calling the fix verified.
