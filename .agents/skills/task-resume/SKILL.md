---
name: task-resume
description: >-
  Cross-session task recovery workflow from an Execution Plan or Session
  Handoff. Use when continuing a paused or handed-off task, reconciling
  recorded progress with live Git state, or verifying whether a handed-off task
  is already completed or has stale notes. Do not use for general repository
  onboarding (use repo-onboarding) or standalone pre-edit impact analysis (use
  change-impact-analysis).
---

# Task Resume & Session Recovery

Resume an existing or handed-off task safely while treating live Git and fresh
verification outputs as higher authority than stale handoff text.

## Constraints

- **Live state wins:** Never treat a handoff snapshot as proof of current
  repository state or current test health.
- **Idempotency & protection:** Never re-apply edits already present on disk,
  and never reset, clean, or overwrite pre-existing dirty/untracked files.
- **Authority & tracking hygiene:** Respect
  [RISK_AND_APPROVAL.md](../../../docs/agent/RISK_AND_APPROVAL.md) gates and do
  not create duplicate global progress trackers.

## Procedure

1. **Identify Target Task**
   - Locate the target handoff and linked execution plan (commonly under
     `docs/tasks/`).
   - If multiple unfinished tasks exist and the user's target is ambiguous, ask
     a brief clarifying question before modifying files.

2. **Load Context Progressively**
   - Read [AGENTS.md](../../../AGENTS.md),
     [CONTEXT_AND_MEMORY.md](../../../docs/agent/CONTEXT_AND_MEMORY.md) (if
     present), and [REPO_GUIDE.md](../../../docs/agent/REPO_GUIDE.md) (if
     present).
   - Read the target Session Handoff and Execution Plan, plus only the specific
     specs, ADRs, or verification rules named in the handoff recovery section.

3. **Reconcile Snapshot vs. Live Repository**
   - Run `git status --short`, current branch, `HEAD` commit, and `git diff --stat`.
   - Inspect files listed under completed and remaining work on disk to verify
     what was actually committed, modified, reverted, or left untracked.
   - Flag any discrepancy between the snapshot and live state before acting.

4. **Check 4-Axis Status & Select Safe Action**
   - Inspect `Task`, `Implementation`, `Verification`, and `Approval` status.
   - If the task is already `COMPLETED` (or all acceptance criteria are satisfied
     on disk), switch to read-only verification/reconciliation, report current
     state plus any doc drift, and stop without re-running completed edits.
   - Otherwise execute the next uncompleted, unblocked step within authorized
     `R0`–`R2` scope; stop for explicit approval on `R3` or approval-gated work.

5. **Verify & Update Task Memory**
   - Run side-effect-assessed verification checks from the final file state.
   - Update the active Plan/Handoff with observed verification outputs only, and
     mark closed (`COMPLETED`) once all acceptance criteria pass.
