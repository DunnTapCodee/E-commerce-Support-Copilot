# Coding Agent Harness Evaluation Adapter (`E-commerce-Support-Copilot`)

This directory implements Phase VI Agent Evaluation Engineering while preserving strict separation between the **Reusable Core** (`core/`) and the **Project-Specific Adapter**.

> **Distinct from Product ML Evaluation:** Modules in `evaluation/*.py` (`evaluation_runner.py`, `run_release_gates.py`, etc.) evaluate the E-commerce Support Copilot's intent classifier, RAG retrieval, and runtime guardrails. This `evaluation/agent_harness/` package evaluates **coding agents working inside the repository** under a fail-closed trust boundary.

## Layout

- **Reusable Core (stdlib-only, repo-agnostic):**
  - `core/schemas.py` — Task manifest (`readiness_status` + `ab_readiness`) and trial record validation.
  - `core/graders.py` — Trust boundary enforcement (separating untrusted trial JSON from trusted workspace execution / external `--trusted-evidence`), Git-recomputed scope checks, safety disqualification gates, and anonymized blinded review packets.
  - `core/runner.py` — Aggregation distinguishing `PASSED`, `FAILED`, `UNVERIFIED`, `TIMEOUT`, `INFRA_ERROR`, `INCOMPLETE`, and `SAFETY_DISQUALIFIED`; strict A/B pairing; JSON/Markdown reports.
  - `core/cli.py` — Generic CLI commands (`validate-manifest`, `validate-trials`, `evaluate --workspace-map / --trusted-evidence`, `prepare-blind-review`, `smoke-test`).
- **Project-Specific Adapter:**
  - `tasks_manifest.json` — 8 candidate tasks (`2` `AB_READY`: `TASK-EVAL-001`, `TASK-EVAL-006`; `3` `PARTIAL`; `3` `NOT_AB_READY`), explicitly separating `TASK_READY`, `GRADER_READY`, `WORKSPACE_READY`, and `OPERATIONALLY_READY`.
  - `trusted_acceptance/` — Evaluator-owned independent acceptance checks (`accept_module3_orders.py`, `accept_conversation_service.py`) executed inside disposable staging copies with runtime SQLite path tracing and fault-injection probes (never editable inside trial sandboxes).
  - `adapter.py` — Scrubbed single-snapshot Git workspace builder (`prepare_isolated_ab_workspaces()` & `validate_ab_workspaces()`), pilot checks, and Antigravity `transcript.jsonl` parser.
  - `run_eval.py` — CLI wrapper preconfigured with repository paths and checks.
  - `smoke_fixtures/` — Explicitly synthetic fixtures for offline `INFRASTRUCTURE_SMOKE_TEST` verification.

## Quick Offline Commands

```powershell
# 1. Validate real task manifest
python -m evaluation.agent_harness.run_eval validate-manifest

# 2. Run offline synthetic infrastructure smoke test (0 LLM calls, does not overwrite tracked reports)
python -m evaluation.agent_harness.run_eval smoke-test
```

## Running a User-Authorized Paired A/B Pilot (Recommended First Task: `TASK-EVAL-001`)

1. Do **not** run trials on the live working tree or reset/clean existing edits.
2. Prepare scrubbed isolated sandboxes outside `REPO_ROOT`:
   ```powershell
   python -m evaluation.agent_harness.run_eval prepare-pilot --task-id TASK-EVAL-001 --dest-dir "<OUTSIDE_DIR>\pilot_001"
   python -m evaluation.agent_harness.run_eval validate-workspaces --pilot-dir "<OUTSIDE_DIR>\pilot_001" --task-id TASK-EVAL-001
   ```
3. Run `TASK-EVAL-001` in two cold independent sessions (same model, runtime, tool permissions, 15m budget; see `<OUTSIDE_DIR>\pilot_001\PILOT_INSTRUCTIONS.txt`). Note: `OPERATIONALLY_READY` is `false` on unconfined host IDE sessions.
4. Grade independently from outside both sandboxes using `--workspace-map` and `--require-trusted-evidence`:
   ```powershell
   python -m evaluation.agent_harness.run_eval evaluate --trials "<OUTSIDE_DIR>\pilot_001\trials.json" --workspace-map "<OUTSIDE_DIR>\pilot_001\workspaces.json" --require-trusted-evidence --output-json "<OUTSIDE_DIR>\pilot_001\report.json" --output-md "<OUTSIDE_DIR>\pilot_001\report.md"
   ```
