"""Repository-scoped entrypoint and minimal pilot prep wrapper for Agent Harness evaluation."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evaluation.agent_harness.adapter import (
    prepare_isolated_ab_workspaces,
    run_project_check,
    validate_ab_workspaces,
)
from evaluation.agent_harness.core.cli import main as core_main

ADAPTER_DIR = Path(__file__).resolve().parent


def _is_inside(candidate: Path, parent: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _handle_prepare_pilot(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_eval prepare-pilot", description="Create scrubbed A/B pilot workspaces outside REPO_ROOT")
    parser.add_argument("--task-id", default="TASK-EVAL-001")
    parser.add_argument("--dest-dir", type=Path, required=True, help="Sandbox parent directory (must be outside REPO_ROOT)")
    parser.add_argument("--trial-prefix", default="PILOT-001")
    args = parser.parse_args(list(argv))

    if _is_inside(args.dest_dir, REPO_ROOT):
        print(f"ERROR: --dest-dir must reside outside REPO_ROOT ({REPO_ROOT}).", file=sys.stderr)
        return 1

    manifest = json.loads((ADAPTER_DIR / "tasks_manifest.json").read_text(encoding="utf-8"))
    tasks = {str(t["task_id"]): t for t in manifest.get("tasks", [])}
    task = tasks.get(args.task_id)
    if task is None:
        print(f"ERROR: Unknown task_id {args.task_id!r}.", file=sys.stderr)
        return 1

    shared_overlays = ["docs/development/verification.md"]
    prov = prepare_isolated_ab_workspaces(
        REPO_ROOT,
        args.dest_dir,
        shared_overlay_paths=shared_overlays,
        task=task,
        strict_readiness=True,
    )

    trial_a = f"{args.trial_prefix}-A"
    trial_b = f"{args.trial_prefix}-B"
    wmap = {
        trial_a: {
            "workspace_path": prov["workspaces"]["A_BASELINE"],
            "expected_base_commit": prov["source_base_commit"],
            "sandbox_head_commit": prov["sandbox_heads"]["A_BASELINE"],
        },
        trial_b: {
            "workspace_path": prov["workspaces"]["B_FULL_HARNESS"],
            "expected_base_commit": prov["source_base_commit"],
            "sandbox_head_commit": prov["sandbox_heads"]["B_FULL_HARNESS"],
        },
    }
    wmap_path = args.dest_dir / "workspaces.json"
    wmap_path.write_text(json.dumps(wmap, indent=2) + "\n", encoding="utf-8")

    instructions = (
        f"# Pilot Runbook: {args.task_id}\n"
        f"base_commit={prov['source_base_commit']}\n"
        f"isolation_scope={prov['isolation_scope']}\n"
        f"runtime_permission_status={prov['runtime_permission_status']}\n"
        f"trial_a={trial_a} -> {prov['workspaces']['A_BASELINE']}\n"
        f"trial_b={trial_b} -> {prov['workspaces']['B_FULL_HARNESS']}\n"
        f"workspaces_map={wmap_path.resolve()}\n\n"
        "Prompt (identical for A and B):\n"
        f"{task['description']}\n"
        f"Allowed scope: {task['allowed_scope']}\n"
        f"Forbidden actions: {task['forbidden_actions']}\n"
        f"Acceptance criteria: {task['acceptance_criteria']}\n"
    )
    (args.dest_dir / "PILOT_INSTRUCTIONS.txt").write_text(instructions, encoding="utf-8")

    print(
        f"PILOT PREPARED: {args.task_id} | dest={args.dest_dir.resolve()} | "
        f"commits={prov['sandbox_heads']} | excluded_sensitive={len(prov['excluded_sensitive_paths'])}"
    )
    return 0


def _handle_validate_workspaces(argv: Sequence[str]) -> int:
    parser = argparse.ArgumentParser(prog="run_eval validate-workspaces", description="Validate prepared A/B pilot sandboxes")
    parser.add_argument("--pilot-dir", type=Path, required=True)
    parser.add_argument("--task-id", default="TASK-EVAL-001")
    args = parser.parse_args(list(argv))

    prov_path = args.pilot_dir / "provenance.json"
    if not prov_path.exists():
        print(f"ERROR: Missing provenance.json in {args.pilot_dir}", file=sys.stderr)
        return 1
    prov = json.loads(prov_path.read_text(encoding="utf-8"))
    manifest = json.loads((ADAPTER_DIR / "tasks_manifest.json").read_text(encoding="utf-8"))
    task = next((t for t in manifest.get("tasks", []) if t.get("task_id") == args.task_id), None)

    res = validate_ab_workspaces(
        Path(prov["workspaces"]["A_BASELINE"]),
        Path(prov["workspaces"]["B_FULL_HARNESS"]),
        task=task,
        provenance=prov,
    )
    if not res["ready"]:
        print("WORKSPACES INVALID:\n" + "\n".join(res["errors"]), file=sys.stderr)
        return 1
    print(f"WORKSPACES READY: {args.task_id} | {args.pilot_dir.resolve()}")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] == "prepare-pilot":
        return _handle_prepare_pilot(raw_argv[1:])
    if raw_argv and raw_argv[0] == "validate-workspaces":
        return _handle_validate_workspaces(raw_argv[1:])

    return core_main(
        argv=raw_argv,
        default_manifest=ADAPTER_DIR / "tasks_manifest.json",
        default_smoke_manifest=ADAPTER_DIR / "smoke_fixtures" / "smoke_manifest.json",
        default_smoke_trials=ADAPTER_DIR / "smoke_fixtures" / "smoke_trials.json",
        adapter_check_runner=run_project_check,
    )


if __name__ == "__main__":
    raise SystemExit(main())
