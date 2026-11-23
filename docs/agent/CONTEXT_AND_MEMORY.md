# Context & Memory Engineering Protocol — v0.2 Extension (Baseline v1)

> **Purpose:** Operational protocol for Coding Agents to load context progressively, manage multi-session execution plans and handoffs, reconcile live repository state, and track progress without duplicating project knowledge.
> **Scope:** Part of the **Reusable Core** of the Agent Harness v0.2. Project-specific paths and commands are resolved via `docs/agent/REPO_GUIDE.md`.

---

## 1. Memory Layers & Lifecycles

Context is what is loaded into the current turn; memory is what persists across turns or sessions. Never treat stale memory as proof of live repository state.

| Layer | Purpose | Canonical Location | Lifecycle | Authority Level |
| --- | --- | --- | --- | --- |
| **Working Context** | Short-term information loaded for the active turn/session (prompt, recent tool outputs, active file slices). | In-memory conversation window | Ephemeral; discarded or compacted when session ends. | Current turn only; must be refreshed if files change. |
| **Task Memory** | Persistent state for complex/multi-session tasks: Execution Plan and Session Handoff. | Task-scoped files when triggered (e.g., `docs/tasks/<task-id>-plan.md`, `docs/tasks/<task-id>-handoff.md`) using `docs/agent/templates/`. | Created on Standard/Extended trigger; updated at checkpoints; closed/archived upon task completion. | Historical snapshot of task intent & progress at timestamp; subordinate to live Git and approved Specs. |
| **Project Knowledge** | Durable system documentation: Architecture, Requirements, Specifications, ADRs, Assumptions, Verification Matrix. | `docs/architecture/`, `docs/product/`, `docs/specs/`, `docs/decisions/`, `docs/development/`, `docs/assumptions.md` | Long-lived; updated only when architecture, requirements, or verification baselines change. | Authoritative for *desired behavior* (`Confirmed`) and *documented design* (`Observed`). |
| **External State** | Live ground truth of code, history, tests, and tasks. | Git (`HEAD`, working tree, diff, branches), filesystem, issue/PR tracker, fresh test runs. | Continuous real-time state. | Highest technical authority for *what currently exists* and *what currently passes*. |

---

## 2. Progressive Context Loading Strategy

Do **not** read the entire `docs/` tree or scan the whole codebase on every task. Load context in four progressive tiers and stop expanding as soon as evidence is sufficient:

1. **Tier 1 — Mission & Live Preflight (Always):**
   - Read user task request and `AGENTS.md`.
   - Run read-only Git preflight (`git status --short`, current branch, `HEAD` commit) to identify existing edits to protect.
2. **Tier 2 — Navigation & Active Task Memory (Always route, load memory if resuming):**
   - Read `docs/agent/REPO_GUIDE.md` as the repository navigation map to locate relevant modules, sensitive hotspots, and documentation entry points.
   - Read `docs/development/verification.md` as the Single Source of Truth for test inventory, safe verification commands, and side-effect classifications.
   - If continuing an in-progress task, load its active Session Handoff and/or Execution Plan.
3. **Tier 3 — Targeted Project Knowledge (On Demand by Task Scope):**
   - Load only the specific Requirement IDs (`docs/product/requirements.md`), Specification (`docs/specs/*.md`), ADR (`docs/decisions/ADR-*.md`), Assumption (`docs/assumptions.md`), or Verification matrix entry (`docs/development/verification.md`) directly touched by the task.
   - Load `docs/agent/RISK_AND_APPROVAL.md` when actions approach R2/R3 boundaries or side effects are uncertain.
4. **Tier 4 — Implementation & Verification Artifacts (Targeted Slices):**
   - Read only the source files, contracts, configs, and test files required to implement and verify the change.
   - Do not re-read unchanged static files already loaded in the current session; always re-check mutable files after edits or external operations.

---

## 3. Plan & Handoff Triggers (Adaptive Overhead)

Separate **planning overhead** (driven by task complexity and multi-session duration) from **approval/verification rigor** (driven by `R0`–`R3` risk in `docs/agent/RISK_AND_APPROVAL.md`):

| Scenario | Persistent Execution Plan? | Persistent Session Handoff? | Action |
| --- | --- | --- | --- |
| **Fast Path** (small, single-session task) | **No** | **No** | State brief inline intention, execute, verify, and report concisely. |
| **Standard Path — Single Session** (multi-file change completed in one session, including authorized `R2`) | **No** (use inline chat plan) | **No** | Outline short plan in conversation; create handoff only if session pauses early or hits a blocker. |
| **Extended Path / Multi-Session / Sensitive Migration** (multi-session work, major cross-boundary design, or `R3` staged work) | **Yes** (`docs/agent/templates/EXECUTION_PLAN.md`) | **Yes, when pausing/transferring** (`docs/agent/templates/SESSION_HANDOFF.md`) | Maintain task-scoped plan and update handoff before ending session or waiting on an R3/approval gate. |
| **Task Completed & Accepted** | Close / Archive | Close / Archive | Mark status `COMPLETED` (or remove temporary task scratch files if requested) so stale active plans do not accumulate. |

Note: Authorized `R2` work within agreed scope proceeds without step-by-step approval (with proportionate impact & verification checks); only `R3` actions, scope/behavior changes, and explicit approval gates require stopping for authorization.

---

## 4. Source Authority & Conflict Resolution

When information conflicts across files or sessions, resolve using this strict order of authority:

1. **Safety, Permissions & Explicit User Directions (`AGENTS.md`, `RISK_AND_APPROVAL.md`, active prompt):** Overrides all other instructions on what actions are permitted.
2. **Live Git & Filesystem (`git status`, `git diff`, `HEAD`, actual files on disk):** Sole authority on *current workspace state*. If a Handoff says a file was edited or a branch was checked out, but live Git disagrees, **live Git wins** — report the discrepancy.
3. **Approved Requirements, Specifications & ADRs (`Confirmed` items):** Authority on *intended product/architectural behavior*. If code diverges from a `Confirmed` requirement, treat it as an implementation gap or bug (do not silently downgrade the requirement).
4. **Fresh Verification Output:** Authority on *current test/build health*. Past test pass claims in a Handoff apply only to the commit/diff snapshot recorded at handoff time.
5. **Historical Reports & Unconfirmed Observations (`Observed` / `reports/*`):** Treat as historical context, never as binding product requirements.

---

## 5. Memory Lifecycle & Hygiene Rules

1. **Capture:** Record only high-signal decisions, file paths, requirement IDs, exact verification commands/results, and remaining blockers. Never paste full source files, long terminal logs, secrets, API keys, tokens, or raw PII.
2. **Validate:** Tag every statement with its epistemic/execution status:
   - `Confirmed` (user-approved) | `Observed` (verified in repo/runtime) | `Planned` (not yet coded) | `Implemented` (coded, unverified) | `Verified` (backed by fresh test evidence) | `Blocked` (halted on dependency/approval) | `Unknown` (unverified).
3. **Update:** Refresh progress and verification evidence when milestones complete or scope shifts.
4. **Close & Archive:** When a task reaches `COMPLETED`, mark its Plan/Handoff closed so future agents do not mistake finished work for an active open task.

---

## 6. Session Recovery Protocol (Cross-Session Continuity)

When starting a new session to continue prior work, execute these five steps in order without asking the user to re-explain information already recoverable from the repo:

### Step 1 — Identify Target Task
- Identify the task from the user's request or locate the active Execution Plan / Session Handoff.
- If multiple unfinished tasks exist and the user's target is ambiguous, ask a brief clarifying question before modifying files.

### Step 2 — Load Relevant Context (Progressive)
- Read `AGENTS.md` and `docs/agent/REPO_GUIDE.md`.
- Read the task's Session Handoff and/or Execution Plan.
- Load only the linked Requirements, Specifications, ADRs, and Verification rules listed in the Handoff's recovery instructions.

### Step 3 — Reconcile Current State Against Snapshot
- Run read-only Git checks: `git status --short`, current branch (`git rev-parse --abbrev-ref HEAD`), and `HEAD` commit (`git rev-parse --short HEAD`).
- Compare live state against the Handoff's **Repository Snapshot**:
  - Were handoff changes committed, modified, or reverted?
  - Are there new untracked or modified user files that must be protected?
- Inspect the specific files listed under Completed / Remaining Work to confirm what is actually implemented on disk. Flag any conflict before proceeding.

### Step 4 — Resume Execution
- Select the next uncompleted, unblocked step from the reconciled state.
- Do not re-apply changes already present; do not run destructive git commands; proceed with `R0`/`R1` and already-authorized `R2` steps within scope, and stop for explicit approval before any `R3` action, scope/behavior change, or approval gate (`docs/agent/RISK_AND_APPROVAL.md`).

### Step 5 — Verify & Update Memory
- Run the safe, isolated verification commands mapped in `docs/development/verification.md`.
- Update the Execution Plan / Session Handoff with new evidence, or mark the task `COMPLETED` if all acceptance criteria are met.

---

## 7. Progress Tracking Strategy (No Competing Trackers)

To preserve a Single Source of Truth, **do not create a global `PROGRESS.md`** or duplicate backlog file:

- **Code & Change State:** Tracked natively by Git (`branch`, `HEAD`, `git status`, `git diff`, Pull Requests).
- **Durable Product / Verification State:** Tracked in `docs/product/requirements.md` and `docs/development/verification.md`.
- **Active Multi-Session Task State:** Tracked in the task-scoped Execution Plan and Session Handoff (`docs/agent/templates/`).

Always separate the **Four Status Axes** in plans, handoffs, and reports:
1. **Task Status:** `NOT_STARTED | IN_PROGRESS | BLOCKED | COMPLETED | ARCHIVED`
2. **Implementation Status:** `PLANNED | IN_PROGRESS | PARTIAL | IMPLEMENTED` (verification readiness is tracked independently via Axis 3)
3. **Verification Status:** `NOT_VERIFIED | LOCALLY_VERIFIED | INTEGRATION_VERIFIED | BLOCKED`
4. **Approval Status:** `NOT_REQUIRED (R0/R1 or authorized R2 in scope) | PENDING_APPROVAL (R3 / approval gate or scope change — use only when an actual unapproved gate exists) | APPROVED | ACCEPTED`

---

## 8. Reusable Core vs. Project-Specific Adapter

| Layer | Components | Portability |
| --- | --- | --- |
| **Reusable Core (80–90% Starter Kit)** | `AGENTS.md` (core working agreement), `docs/agent/TASK_PROTOCOL.md`, `docs/agent/RISK_AND_APPROVAL.md`, `docs/agent/CONTEXT_AND_MEMORY.md`, `docs/agent/templates/EXECUTION_PLAN.md`, `docs/agent/templates/SESSION_HANDOFF.md` | Project-agnostic; reusable across repositories without modification. |
| **Project-Specific Adapter (10–20%)** | `docs/agent/REPO_GUIDE.md`, `docs/architecture/overview.md`, `docs/product/requirements.md`, `docs/specs/*`, `docs/decisions/ADR-*`, `docs/development/verification.md`, `docs/assumptions.md` | Tailored to the specific repository's services, paths, contracts, and test commands. |
