---
name: repo-onboarding
description: >-
  Read-only repository orientation workflow for mapping structure, entrypoints,
  tests, agent instructions, and knowledge gaps while separating Confirmed facts
  from Observed and Assumed findings. Use when onboarding onto an unfamiliar
  repository or establishing baseline project context. Do not use to resume a
  paused task handoff (use task-resume) or analyze a proposed code edit (use
  change-impact-analysis).
---

# Repository Onboarding

Orient safely and economically in a repository without inventing requirements or
triggering unintended side effects.

## Constraints

- **Read-only by default:** Inspect files and run read-only Git checks only; do
  not modify code or overwrite documentation unless explicitly authorized.
- **No fabricated requirements:** Label every finding as `Confirmed`,
  `Observed`, `Assumed`, or `Unknown`.
- **Progressive loading:** Avoid scanning the whole repository when targeted
  manifest, doc, and entrypoint reads answer the question.

## Procedure

1. **Check Live Git State**
   - Run `git status --short`, current branch, and `HEAD` commit checks.
   - Record any pre-existing dirty or untracked files that must be preserved.

2. **Load Agent Harness & Project Adapter**
   - Read [AGENTS.md](../../../AGENTS.md) (and root `GEMINI.md` or `README.md` if
     present).
   - If the repository includes the Agent Harness docs, read
     [REPO_GUIDE.md](../../../docs/agent/REPO_GUIDE.md) for project-specific
     navigation and [verification.md](../../../docs/development/verification.md)
     (or the repository's test guide) before running any tests or builds.

3. **Map Structure, Stack & Entrypoints**
   - List top-level directories, build/dependency manifests, service or app
     entrypoints, configuration templates, and test directories.
   - Identify primary languages, frameworks, runtime ports/processes, and
     persistent storage boundaries.

4. **Reconcile Documentation vs. Code**
   - Locate architecture overviews, requirements, specs, and ADRs (`docs/` if
     present).
   - Note contradictions between documentation and current code/config without
     silently picking one side as confirmed.
   - Classify test/eval commands by side effects (offline vs. external LLM/API,
     disk/DB writes) per [RISK_AND_APPROVAL.md](../../../docs/agent/RISK_AND_APPROVAL.md).

5. **Deliver Onboarding Summary**
   - Report concisely: stack & entrypoints, confirmed vs. observed behaviors,
     safe verification commands, sensitive hotspots, open decisions/gaps, and
     recommended adapter updates if navigation docs are missing or stale.
