# Skills & Automation Baseline v1

> **Status:** Active Baseline v1 (Phase V). Complements [AGENTS.md](../../AGENTS.md), [TASK_PROTOCOL.md](TASK_PROTOCOL.md), [RISK_AND_APPROVAL.md](RISK_AND_APPROVAL.md), [CONTEXT_AND_MEMORY.md](CONTEXT_AND_MEMORY.md), and [REPO_GUIDE.md](REPO_GUIDE.md) without duplicating their rules.

---

## 1. Runtime Discovery & Cross-Tool Compatibility

- **Primary Runtime (`Observed`):** Google Antigravity discovers repository-scoped skills under `.agents/skills/<skill-name>/SKILL.md` (with progressive disclosure: `name` + `description` indexed upfront; full `SKILL.md` loaded on demand or via `/<skill-name>`).
- **Codex Compatibility (`Observed` via docs):** OpenAI Codex and the open Agent Skills specification share `.agents/skills/<skill-name>/SKILL.md` with lowercase hyphenated `name` (`<= 64` chars, matching directory name) and `description` (`<= 1024` chars).
- **Important Limit:** Skills added mid-session are not indexed in an already-running session's startup metadata; implicit activation must be verified in a **fresh independent session**.

---

## 2. Repository-Scoped Core Skills (`.agents/skills/`)

All committed skills are **Reusable Core** workflows (no hardcoded `E-commerce-Support-Copilot` service or DB names); project-specific routing remains in [REPO_GUIDE.md](REPO_GUIDE.md) and [verification.md](../development/verification.md).

| Skill | Path | When to Invoke | When NOT to Invoke |
| --- | --- | --- | --- |
| `repo-onboarding` | [.agents/skills/repo-onboarding/SKILL.md](../../.agents/skills/repo-onboarding/SKILL.md) | Orienting in an unfamiliar repo, mapping entrypoints/tests, separating `Confirmed`/`Observed`/`Assumed` | Resuming a task handoff (`task-resume`), analyzing a specific code edit (`change-impact-analysis`), or trivial Fast-path edits |
| `task-resume` | [.agents/skills/task-resume/SKILL.md](../../.agents/skills/task-resume/SKILL.md) | Resuming a paused or handed-off task (`docs/tasks/*-handoff.md`), reconciling Git snapshot vs. live state | Initial repository onboarding (`repo-onboarding`) or standalone pre-edit impact analysis (`change-impact-analysis`) |
| `change-impact-analysis` | [.agents/skills/change-impact-analysis/SKILL.md](../../.agents/skills/change-impact-analysis/SKILL.md) | Mapping callers, consumers, shared contracts, `R0`–`R3` risks, and minimal tests before changing sensitive/shared code | Whole-repo onboarding (`repo-onboarding`), handoff recovery (`task-resume`), or simple Fast-path bug/typo fixes |

---

## 3. Deterministic Skill Automation & CI

- **Validator:** [scripts/validate_skills.py](../../scripts/validate_skills.py) (Python stdlib only; zero execution of skill scripts). Checks directory layout, YAML frontmatter syntax, unique lowercase hyphenated `name == <dir>`, `description` length (`20..1024` chars), progressive-disclosure caps (`<= 500` lines / `24,000` bytes), non-empty Markdown sections, and relative link resolution inside repo root.
- **Test Suite:** [tests/test_agent_skills.py](../../tests/test_agent_skills.py) verifies live skills, negative validator cases, reusable-core leak checks, frontmatter routing separability, constraint compliance, and simulated read-only `task-resume` pilot checks.
- **CI Integration:** Integrated directly into `backend-offline-tests` inside [.github/workflows/ci-offline.yml](../../.github/workflows/ci-offline.yml) with `permissions: contents: read`.

---

## 4. Hooks & Subagents Assessment (Deferred in Baseline v1)

| Mechanism | Expected Benefit | Runtime Support | Decision & Rationale |
| --- | --- | --- | --- |
| `PreToolUse` safety hook (`.agents/hooks.json`) | Block destructive shell commands or sensitive reads pre-tool | Antigravity supported (`cmd /c` Win, `sh -c` Unix); different config in Codex | **Deferred:** Synchronous execution blocks every matching call, introduces Windows/Unix script portability risk, and duplicates existing tool permissions + `RISK_AND_APPROVAL.md` + CI static guards. |
| `PostToolUse` auto-validation hook | Auto-run `validate_skills.py` or `pytest` after edits | Antigravity supported (`write_file`/`edit_file`) | **Deferred:** Fires mid-edit during multi-file changes, slowing edits and causing transient false failures; deterministic CI + explicit verification after coherent edits are cleaner. |
| Custom static subagent definitions | Dedicated read-only reviewer or impact scanner | Antigravity provides built-in `research` subagent & `define_subagent` | **Deferred:** Built-in read-only `research` subagent plus `change-impact-analysis` already cover isolated inspection without maintaining runtime-specific agent manifests. |

---

## 5. Activation Quality Evaluation & Fresh-Session Pilot

Executable unit checks in [tests/test_agent_skills.py](../../tests/test_agent_skills.py) verify **structural validity**, **metadata routing separability**, **constraint compliance**, **context efficiency** (`<= 90` lines per skill), and **simulated read-only reconciliation** (`TASK-20261122-isolate-policy-audit-test-handoff.md`). They do **not** prove live LLM implicit activation.

### Recommended Fresh-Session Pilot Prompt (Independent Session)

1. **Implicit activation test (`task-resume`):**
   > *"Kiểm tra task bàn giao tại `docs/tasks/TASK-20261122-isolate-policy-audit-test-handoff.md` ở chế độ read-only, đối chiếu với trạng thái Git hiện tại và cho biết còn việc gì chưa hoàn thành."*
   - **Expected:** Agent discovers and reads `.agents/skills/task-resume/SKILL.md`, reconciles live Git without editing files, recognizes `COMPLETED` / `LOCALLY_VERIFIED`, reports any doc drift (`REPO_GUIDE.md:45`), and proposes zero redundant code changes.
2. **Negative activation test (Fast-path control):**
   > *"Giải thích ngắn gọn hàm `get_vn_today()` trong `contracts/schemas.py` trả về kiểu gì."*
   - **Expected:** Agent reads only `contracts/schemas.py` directly without loading `.agents/skills/*/SKILL.md`.
