# Execution Plan Template (Reusable Core)

> **Usage:** Use this template for **Extended** or multi-session **Standard** tasks (`docs/agent/TASK_PROTOCOL.md`, `docs/agent/CONTEXT_AND_MEMORY.md`). Skip for small Fast-path tasks.
> **Rule:** A checked milestone box indicates step completion only; it is **not** proof of verification unless backed by observed command output in Section 8. Never store secrets, API keys, PII, or full raw logs here.

---

## 1. Task Identity & Status

- **Task ID:** `<TASK-YYYYMMDD-short-slug>`
- **Task Title:** `<Concise action-oriented title>`
- **Created / Updated At:** `<YYYY-MM-DDTHH:MM:SS±HH:MM>`
- **Task Status:** `NOT_STARTED | IN_PROGRESS | BLOCKED | COMPLETED | ARCHIVED`
- **Implementation Status:** `PLANNED | IN_PROGRESS | PARTIAL | IMPLEMENTED`
- **Verification Status:** `NOT_VERIFIED | LOCALLY_VERIFIED | INTEGRATION_VERIFIED | BLOCKED`
- **Approval Status:** `NOT_REQUIRED (R0/R1 or authorized R2 in scope) | PENDING_APPROVAL (R3 / approval gate or scope change) | APPROVED | ACCEPTED`

---

## 2. Goal & Expected Outcome

- **Objective:** `<1–3 sentences describing the observable problem to solve or capability to deliver>`
- **Expected Outcome:** `<Concrete deliverables: files, behavior changes, tests, or docs>`

---

## 3. Scope & Non-Goals

- **In Scope:**
  - `<Module / component / document 1>`
  - `<Module / component / document 2>`
- **Out of Scope (Non-Goals):**
  - `<Unrelated refactors, unapproved migrations, live external calls, etc.>`

---

## 4. Relevant Requirements, Specifications & ADRs

- **Requirements:** `<e.g., BR-xxx, FR-xxx, NFR-xxx, SC-xxx>`
- **Specifications:** `<Path(s) to relevant spec files>`
- **ADRs / Architecture:** `<Path(s) to relevant ADRs and architecture section>`

---

## 5. Constraints & Risk Classification

- **Highest Risk Level (`R0`–`R3`):** `<R1 / R2 / R3 — see docs/agent/RISK_AND_APPROVAL.md>`
- **Hard Constraints:**
  - Preserve all pre-existing working tree edits and untracked files.
  - `<Additional constraints: offline-only, no DB mutation, no schema break, etc.>`
- **Approval Gates Required:** `<None (within authorized scope) | Specify R3 / approval-gate action requiring explicit user approval before execution>`

---

## 6. Proposed Approach

`<Brief technical design: key root cause or architectural approach, affected consumers, backward compatibility, and rollback strategy>`

---

## 7. Implementation Steps / Milestones

> Tag each step with `[PLANNED]`, `[IN_PROGRESS]`, `[IMPLEMENTED]`, `[VERIFIED]`, or `[BLOCKED]`.

- [ ] **M1 (`[PLANNED]`):** `<Step 1 description — target files>`
- [ ] **M2 (`[PLANNED]`):** `<Step 2 description — target files>`
- [ ] **M3 (`[PLANNED]`):** `<Add/update targeted regression tests — target test files>`
- [ ] **M4 (`[PLANNED]`):** `<Run safe verification suite & reconcile docs>`

---

## 8. Verification Strategy & Observed Evidence

- **Planned Safe Commands:**
  - `<Command 1 — why safe / isolated>`
  - `<Command 2 — why safe / isolated>`
- **Observed Verification Results (fill only after actual execution):**
  - `Command:` `<exact command run>`
  - `Result:` `<pass/fail counts, exit code, timestamp — or NOT_YET_RUN>`
  - `Limitations:` `<what was mocked vs. unverified in live integration>`

---

## 9. Dependencies & Blockers

- **Active Blockers:** `<None | Describe missing artifact, credential, external service, or pending owner decision>`
- **Assumptions Relied Upon:** `<e.g., ASM-xxx>`

---

## 10. Acceptance Criteria / Definition of Done

- [ ] `<Criterion 1 — mapped to requirement/spec>`
- [ ] `<Criterion 2 — regression test added and passing>`
- [ ] `<Criterion 3 — no unintended side effects in git status / diff>`

---

## 11. Decisions & Plan Changes Log

| Timestamp | Change / Decision | Rationale / Evidence | Status (`Confirmed` / `Observed`) |
| --- | --- | --- | --- |
| `<ISO timestamp>` | `<Initial plan baseline>` | `<Preflight inspection>` | `Observed` |

---

## 12. Current Progress & References

- **Completed So Far:** `<Summary of finished milestones>`
- **Next Action:** `<Immediate next step for current or receiving agent>`
- **References:**
  - `<Link to REPO_GUIDE.md, verification doc, or active SESSION_HANDOFF.md>`
