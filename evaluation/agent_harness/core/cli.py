"""Project-agnostic CLI for Agent Harness evaluation validation, smoke checks, and trusted reporting."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from evaluation.agent_harness.core.graders import (
    DeterministicCheckOutcome,
    canonical_json_dumps,
    prepare_blind_review_packets,
)
from evaluation.agent_harness.core.runner import evaluate_and_summarize, render_markdown_report
from evaluation.agent_harness.core.schemas import (
    extract_trials_list,
    validate_manifest,
    validate_trial_records,
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _is_inside(candidate: Path, parent: Path) -> bool:
    try:
        candidate.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _parse_workspace_mappings(
    workspace_map_path: Optional[Path],
    workspace_flags: Sequence[str],
) -> Tuple[Dict[str, Path], Dict[str, Dict[str, Any]], List[str]]:
    ws_by_trial: Dict[str, Path] = {}
    meta_by_trial: Dict[str, Dict[str, Any]] = {}
    errors: List[str] = []

    if workspace_map_path is not None:
        raw = _load_json(workspace_map_path)
        entries = raw.get("workspaces") if isinstance(raw, dict) and "workspaces" in raw else raw
        if not isinstance(entries, dict):
            return {}, {}, ["workspace-map JSON must be an object mapping trial_id to path/metadata."]
        for tid, val in entries.items():
            if isinstance(val, str):
                ws_by_trial[str(tid)] = Path(val)
                meta_by_trial[str(tid)] = {"trial_id": str(tid)}
            elif isinstance(val, dict) and isinstance(val.get("workspace_path"), str):
                ws_by_trial[str(tid)] = Path(val["workspace_path"])
                meta_copy = dict(val)
                meta_copy.setdefault("trial_id", str(tid))
                meta_by_trial[str(tid)] = meta_copy
            else:
                errors.append(f"Invalid workspace-map entry for '{tid}'; expected string or object with 'workspace_path'.")

    for raw_arg in workspace_flags:
        if "=" not in raw_arg:
            errors.append(f"Invalid --workspace argument {raw_arg!r}; expected TRIAL_ID=PATH.")
            continue
        tid, path_str = raw_arg.split("=", 1)
        tid = tid.strip()
        path_str = path_str.strip()
        if not tid or not path_str:
            errors.append(f"Invalid --workspace argument {raw_arg!r}; expected non-empty TRIAL_ID=PATH.")
            continue
        ws_by_trial[tid] = Path(path_str)
        meta_by_trial.setdefault(tid, {"trial_id": tid})

    return ws_by_trial, meta_by_trial, errors


def _parse_trusted_evidence(path: Optional[Path]) -> Tuple[Dict[str, Dict[str, Any]], List[str]]:
    if path is None:
        return {}, []
    raw = _load_json(path)
    entries = raw.get("trials") if isinstance(raw, dict) and "trials" in raw else raw
    if not isinstance(entries, dict):
        return {}, ["trusted-evidence JSON must be an object mapping trial_id to trusted verdict object."]
    out: Dict[str, Dict[str, Any]] = {}
    for tid, val in entries.items():
        if not isinstance(val, dict):
            return {}, [f"trusted-evidence entry for '{tid}' must be a JSON object."]
        out[str(tid)] = val
    return out, []


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    default_manifest: Optional[Path] = None,
    default_smoke_manifest: Optional[Path] = None,
    default_smoke_trials: Optional[Path] = None,
    adapter_check_runner: Optional[Callable[[str, Path], DeterministicCheckOutcome]] = None,
) -> int:
    parser = argparse.ArgumentParser(description="Agent Harness Evaluation CLI (stdlib-only)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_man = sub.add_parser("validate-manifest", help="Validate task manifest JSON")
    p_man.add_argument("--manifest", type=Path, default=default_manifest, required=default_manifest is None)

    p_tr = sub.add_parser("validate-trials", help="Validate trial records JSON against manifest")
    p_tr.add_argument("--manifest", type=Path, default=default_manifest, required=default_manifest is None)
    p_tr.add_argument("--trials", type=Path, required=True)

    p_eval = sub.add_parser("evaluate", help="Evaluate imported trials against trusted workspaces/evidence")
    p_eval.add_argument("--manifest", type=Path, default=default_manifest, required=default_manifest is None)
    p_eval.add_argument("--trials", type=Path, required=True)
    p_eval.add_argument("--workspace-map", type=Path, default=None, help="JSON mapping trial_id -> workspace_path + provenance")
    p_eval.add_argument("--workspace", action="append", default=[], help="Explicit TRIAL_ID=PATH mapping (repeatable)")
    p_eval.add_argument("--trusted-evidence", type=Path, default=None, help="External trusted evaluator verdict JSON")
    p_eval.add_argument("--require-trusted-evidence", action="store_true", help="Exit non-zero if any trial is UNVERIFIED")
    p_eval.add_argument("--output-json", type=Path, default=None)
    p_eval.add_argument("--output-md", type=Path, default=None)

    p_blind = sub.add_parser("prepare-blind-review", help="Generate anonymized review packets without A/B labels")
    p_blind.add_argument("--manifest", type=Path, default=default_manifest, required=default_manifest is None)
    p_blind.add_argument("--trials", type=Path, required=True)
    p_blind.add_argument("--output-json", type=Path, default=None)

    p_smoke = sub.add_parser("smoke-test", help="Run deterministic offline INFRASTRUCTURE_SMOKE_TEST on synthetic fixtures")
    p_smoke.add_argument("--manifest", type=Path, default=default_smoke_manifest, required=default_smoke_manifest is None)
    p_smoke.add_argument("--trials", type=Path, default=default_smoke_trials, required=default_smoke_trials is None)
    p_smoke.add_argument("--output-json", type=Path, default=None)
    p_smoke.add_argument("--output-md", type=Path, default=None)
    p_smoke.add_argument("--quiet", action="store_true")

    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "validate-manifest":
        payload = _load_json(args.manifest)
        res = validate_manifest(payload)
        if not res.ok:
            print("\n".join(res.errors), file=sys.stderr)
            return 1
        print(f"MANIFEST OK: {res.task_count} task(s) validated in {args.manifest}")
        return 0

    if args.command == "validate-trials":
        manifest = _load_json(args.manifest)
        m_res = validate_manifest(manifest)
        if not m_res.ok:
            print("\n".join(m_res.errors), file=sys.stderr)
            return 1
        tasks_by_id = {str(t["task_id"]): t for t in manifest["tasks"]}
        trials = _load_json(args.trials)
        t_res = validate_trial_records(trials, manifest_tasks_by_id=tasks_by_id)
        if not t_res.ok:
            print("\n".join(t_res.errors), file=sys.stderr)
            return 1
        print(f"TRIALS OK: {t_res.trial_count} trial(s) validated in {args.trials}")
        return 0

    if args.command == "evaluate":
        manifest = _load_json(args.manifest)
        trials = _load_json(args.trials)

        ws_by_trial, meta_by_trial, ws_errs = _parse_workspace_mappings(args.workspace_map, args.workspace)
        trusted_ev_by_trial, tr_errs = _parse_trusted_evidence(args.trusted_evidence)
        if ws_errs or tr_errs:
            print("\n".join(ws_errs + tr_errs), file=sys.stderr)
            return 1

        # Trust boundary: grader code, manifest, trusted evidence, and output reports
        # must live outside evaluated trial workspaces.
        trusted_paths: List[Path] = [Path(args.manifest)]
        for opt in (args.workspace_map, args.trusted_evidence, args.output_json, args.output_md):
            if opt is not None:
                trusted_paths.append(Path(opt))
        for tid, ws in ws_by_trial.items():
            if ws.exists():
                for tp in trusted_paths:
                    if _is_inside(tp, ws):
                        print(
                            f"TRUST BOUNDARY ERROR: trusted path {tp} resides inside evaluated trial workspace {ws} ({tid}).",
                            file=sys.stderr,
                        )
                        return 1

        try:
            summary = evaluate_and_summarize(
                manifest,
                trials,
                workspace_by_trial_id=ws_by_trial,
                workspace_meta_by_trial_id=meta_by_trial,
                trusted_evidence_by_trial_id=trusted_ev_by_trial,
                adapter_check_runner=adapter_check_runner,
                run_type_override="AGENT_AB_PILOT",
                allow_synthetic_smoke=False,
                trusted_external_paths=trusted_paths,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1

        md = render_markdown_report(summary)
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(canonical_json_dumps(summary) + "\n", encoding="utf-8")
        if args.output_md:
            args.output_md.parent.mkdir(parents=True, exist_ok=True)
            args.output_md.write_text(md + "\n", encoding="utf-8")
        print(md)

        if args.require_trusted_evidence and any(
            o.get("effective_status") == "UNVERIFIED" for o in summary.get("trial_outcomes", [])
        ):
            print("ERROR: --require-trusted-evidence set and one or more trials are UNVERIFIED.", file=sys.stderr)
            return 1
        return 0

    if args.command == "smoke-test":
        manifest = _load_json(args.manifest)
        trials = _load_json(args.trials)
        summary = evaluate_and_summarize(
            manifest,
            trials,
            adapter_check_runner=adapter_check_runner,
            run_type_override="INFRASTRUCTURE_SMOKE_TEST",
            allow_synthetic_smoke=True,
        )
        md = render_markdown_report(summary)
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(canonical_json_dumps(summary) + "\n", encoding="utf-8")
        if args.output_md:
            args.output_md.parent.mkdir(parents=True, exist_ok=True)
            args.output_md.write_text(md + "\n", encoding="utf-8")
        if not getattr(args, "quiet", False):
            print(md)
        else:
            print(f"{summary['run_type']} OK: {summary['total_trials']} trial(s) | {summary['ab_effectiveness_status']}")
        return 0

    if args.command == "prepare-blind-review":
        manifest = _load_json(args.manifest)
        m_res = validate_manifest(manifest)
        if not m_res.ok:
            print("\n".join(m_res.errors), file=sys.stderr)
            return 1
        tasks_by_id = {str(t["task_id"]): t for t in manifest["tasks"]}
        trials_payload = _load_json(args.trials)
        trials, _, errs = extract_trials_list(trials_payload)
        if errs:
            print("\n".join(errs), file=sys.stderr)
            return 1
        packets = prepare_blind_review_packets(trials, tasks_by_id)
        rendered = canonical_json_dumps(packets)
        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(rendered + "\n", encoding="utf-8")
        else:
            print(rendered)
        return 0

    return 2
