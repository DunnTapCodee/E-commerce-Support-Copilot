# Session Handoff Template (Reusable Core)

> **Usage:** Create or update when pausing an unfinished task across sessions, stopping at an approval/dependency blocker, or transferring work to another Coding Agent (`docs/agent/CONTEXT_AND_MEMORY.md`).
> **Critical Rules:**
> 1. Never include secrets, API keys, tokens, credentials, raw PII, or full terminal log dumps.
> 2. The Repository Snapshot below records state **at handoff time only**. A receiving agent **must** run live Git checks (`git status --short`, branch, `HEAD`) to reconcile state before acting.

---

## 1. Handoff Identity & Four-Axis Status

- **Task ID:** `<TASK-YYYYMMDD-short-slug>`
- **Task Title:** `<Concise title>`
- **Handoff Timestamp:** `<YYYY-MM-DDTHH:MM:SS±HH:MM>`
- **Linked Execution Plan:** `<Path to plan file, or "None (Standard path)">`
- **Task Status:** `IN_PROGRESS | BLOCKED | COMPLETED`
- **Implementation Status:** `PLANNED | IN_PROGRESS | PARTIAL | IMPLEMENTED`
- **Verification Status:** `NOT_VERIFIED | LOCALLY_VERIFIED | INTEGRATION_VERIFIED | BLOCKED`
- **Approval Status:** `NOT_REQUIRED (R0/R1 or authorized R2 in scope) | PENDING_APPROVAL (R3 / approval gate or scope change) | APPROVED | ACCEPTED`

---

## 2. Goal, Scope & Constraints to Preserve

- **Task Goal:** `<1–2 sentences stating what the task must achieve>`
- **Hard Constraints:**
  - Do not reset, clean, or overwrite pre-existing working tree changes.
  - `<Other active constraints: offline-only, no commit/push, no live DB mutation, etc.>`

---

## 3. Repository Snapshot at Handoff (Must Re-verify on Resume)

- **Branch at Handoff:** `<branch-name>`
- **HEAD Commit at Handoff:** `<short-sha>`
- **Files Created / Modified by This Task:**
  - `<path/to/file1>` — `<status: IMPLEMENTED | PARTIAL; Verification: NOT_VERIFIED | LOCALLY_VERIFIED>`
  - `<path/to/file2>` — `<status>`
- **Pre-existing / Unrelated Working Tree Changes to Protect:**
  - `<None | List modified/untracked files that existed before this task and must not be touched>`

---

## 4. Completed Work & Key Findings

- **Implemented Changes:**
  - `<Bullet summary of exact code/doc/test changes applied>`
- **Confirmed Decisions Applied:**
  - `<Decisions confirmed by user or ADRs>`
- **Important Technical Findings (`Observed`):**
  - `<Root causes, contract nuances, or side-effect traps discovered during work>`

---

## 5. Verification Evidence

- **Commands Executed & Observed Results:**
  - `<Command 1>` -> `<Observed result: e.g., X passed in Ys, exit code 0>`
- **Tests / Checks Not Run or Blocked:**
  - `<Test/check name>` -> `<Why skipped or blocked: e.g., requires live API, missing artifact, mutates root DB>`
- **Evidence Limitations:**
  - `<Explicitly state what is only mocked/locally verified vs. unverified in live integration>`

---

## 6. Remaining Work, Blockers & Next Action

- **Remaining Steps:**
  1. `<Step 1>`
  2. `<Step 2>`
- **Active Blockers:** `<None | Missing artifact, credential, external service, or R3 / approval-gate authorization needed>`
- **Open Decisions Needed from User:** `<None | Specific question(s) requiring owner decision>`
- **Next Recommended Action:** `<Exact first step the receiving agent should take after state reconciliation>`

---

## 7. Recovery Instructions for Receiving Agent

Follow the **Session Recovery Protocol** in `docs/agent/CONTEXT_AND_MEMORY.md` (§6):

1. **Minimal Files to Read First (Progressive Load):**
   - `AGENTS.md` and `docs/agent/REPO_GUIDE.md`
   - This Handoff file (and linked Execution Plan if present)
   - `<2–4 specific requirement/spec/source/test files directly needed for the next step>`
2. **State Reconciliation Checklist (Mandatory Before Editing):**
   - Run `git status --short`, `git rev-parse --abbrev-ref HEAD`, and `git rev-parse --short HEAD`.
   - Compare live output against Section 3 above; check whether files in Section 3 were committed, modified, or reverted since handoff.
3. **Prohibited Automatic Actions:**
   - Do not run `git reset`, `git clean`, `git checkout --`, or automatic data migrations.
   - Do not re-apply edits already present on disk.
   - Do not cross `R3` / approval-gate boundaries or alter agreed scope without explicit user authorization.
