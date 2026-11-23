"""Project-agnostic evaluation aggregation, A/B pairing, and reporting engine.

Pure Python standard library only. Never calls live LLMs, never invents telemetry,
never lets speed/cost cancel safety violations, never treats unverified claims as
passed evidence, and strictly rejects incomparable or synthetic A/B pairs.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from statistics import median
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from evaluation.agent_harness.core.graders import DeterministicCheckOutcome, TrialEvaluationOutcome, evaluate_trial
from evaluation.agent_harness.core.schemas import (
    ALLOWED_CONDITIONS,
    extract_trials_list,
    validate_manifest,
    validate_trial_records,
)


def _extract_numeric_telemetry(trial: Dict[str, Any], field: str) -> Optional[float]:
    val = trial.get(field)
    if val is None or val == "not_available":
        return None
    if field == "tokens_used":
        if isinstance(val, int) and not isinstance(val, bool):
            return float(val)
        if isinstance(val, dict):
            parts = [
                v for k, v in val.items()
                if k in ("input_tokens", "output_tokens", "total_tokens")
                and isinstance(v, (int, float))
                and not isinstance(v, bool)
            ]
            if "total_tokens" in val and isinstance(val["total_tokens"], (int, float)):
                return float(val["total_tokens"])
            if parts:
                return float(sum(parts))
            return None
        return None
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    return None


def _summarize_numeric_series(values: Sequence[Optional[float]]) -> Dict[str, Any]:
    measured = [float(v) for v in values if v is not None]
    total_n = len(values)
    missing_n = total_n - len(measured)
    if not measured:
        return {
            "measured_count": 0,
            "missing_count": missing_n,
            "status": "not_available",
            "min": None,
            "median": None,
            "mean": None,
            "max": None,
            "total": None,
        }
    return {
        "measured_count": len(measured),
        "missing_count": missing_n,
        "status": "available" if missing_n == 0 else "partial",
        "min": round(min(measured), 4),
        "median": round(float(median(measured)), 4),
        "mean": round(sum(measured) / len(measured), 4),
        "max": round(max(measured), 4),
        "total": round(sum(measured), 4),
    }


def _aggregate_trial_group(
    trials: Sequence[Dict[str, Any]],
    outcomes_by_id: Dict[str, TrialEvaluationOutcome],
) -> Dict[str, Any]:
    total = len(trials)
    status_counts = {
        "PASSED": 0,
        "FAILED": 0,
        "UNVERIFIED": 0,
        "TIMEOUT": 0,
        "INFRA_ERROR": 0,
        "INCOMPLETE": 0,
        "SAFETY_DISQUALIFIED": 0,
    }
    reported_pass_count = 0
    unverified_pass_rejections = 0
    total_safety_violations = 0

    durations: List[Optional[float]] = []
    interventions: List[Optional[float]] = []
    tool_calls: List[Optional[float]] = []
    tokens: List[Optional[float]] = []
    costs: List[Optional[float]] = []

    for trial in trials:
        outcome = outcomes_by_id[str(trial["trial_id"])]
        status_counts[outcome.effective_status] = status_counts.get(outcome.effective_status, 0) + 1
        if trial.get("status") == "PASSED":
            reported_pass_count += 1
            if not outcome.verified_passed and not outcome.safety_disqualified:
                unverified_pass_rejections += 1
        total_safety_violations += len(outcome.safety_violations)

        durations.append(_extract_numeric_telemetry(trial, "duration_seconds"))
        interventions.append(_extract_numeric_telemetry(trial, "human_interventions"))
        tool_calls.append(_extract_numeric_telemetry(trial, "tool_calls"))
        tokens.append(_extract_numeric_telemetry(trial, "tokens_used"))
        costs.append(_extract_numeric_telemetry(trial, "estimated_cost"))

    verified_passed = status_counts["PASSED"]
    success_rate = round(verified_passed / total, 4) if total else None

    return {
        "total_trials": total,
        "verified_passed": verified_passed,
        "reported_passed": reported_pass_count,
        "unverified_pass_rejections": unverified_pass_rejections,
        "task_success_rate": success_rate,
        "status_counts": status_counts,
        "safety_disqualified_count": status_counts["SAFETY_DISQUALIFIED"],
        "total_safety_violations": total_safety_violations,
        "telemetry": {
            "duration_seconds": _summarize_numeric_series(durations),
            "human_interventions": _summarize_numeric_series(interventions),
            "tool_calls": _summarize_numeric_series(tool_calls),
            "tokens_used": _summarize_numeric_series(tokens),
            "estimated_cost": _summarize_numeric_series(costs),
        },
    }


def _budget_fingerprint(task: Optional[Dict[str, Any]], trial: Dict[str, Any]) -> Any:
    if "budget_fingerprint" in trial and trial["budget_fingerprint"] is not None:
        return trial["budget_fingerprint"]
    if task is not None:
        return task.get("timeout_or_budget")
    return None


def _build_ab_pairs(
    trials: Sequence[Dict[str, Any]],
    outcomes_by_id: Dict[str, TrialEvaluationOutcome],
    tasks_by_id: Dict[str, Dict[str, Any]],
    is_smoke_run: bool,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Strictly match comparable A_BASELINE vs B_FULL_HARNESS trials on identical conditions."""
    valid_pairs: List[Dict[str, Any]] = []
    rejected_pairs: List[Dict[str, Any]] = []

    by_task: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for trial in trials:
        by_task[str(trial["task_id"])][str(trial["configuration"])].append(trial)

    for task_id in sorted(by_task):
        configs = by_task[task_id]
        a_list = configs.get("A_BASELINE", [])
        b_list = configs.get("B_FULL_HARNESS", [])

        if not a_list or not b_list:
            rejected_pairs.append(
                {
                    "task_id": task_id,
                    "reason": "missing_partner_trial",
                    "available_configs": {k: len(v) for k, v in configs.items()},
                }
            )
            continue

        if len(a_list) != len(b_list):
            rejected_pairs.append(
                {
                    "task_id": task_id,
                    "reason": "unbalanced_pair_counts",
                    "a_count": len(a_list),
                    "b_count": len(b_list),
                }
            )
            continue

        task = tasks_by_id.get(task_id)
        for pair_idx, (a_trial, b_trial) in enumerate(zip(a_list, b_list)):
            a_id = str(a_trial["trial_id"])
            b_id = str(b_trial["trial_id"])
            a_out = outcomes_by_id[a_id]
            b_out = outcomes_by_id[b_id]

            incomparability: List[str] = []
            if is_smoke_run or a_trial.get("evidence_quality") == "SYNTHETIC_SMOKE" or b_trial.get("evidence_quality") == "SYNTHETIC_SMOKE":
                incomparability.append("synthetic_smoke_fixture_not_empirical")
            if task is not None and task.get("ab_readiness") == "NOT_AB_READY":
                incomparability.append("task_marked_not_ab_ready")
            if a_trial.get("base_commit") != b_trial.get("base_commit"):
                incomparability.append("mismatched_base_commit")
            if a_trial.get("model") != b_trial.get("model"):
                incomparability.append("mismatched_model")
            if a_trial.get("runtime") != b_trial.get("runtime"):
                incomparability.append("mismatched_runtime")
            if a_trial.get("config_fingerprint_mismatch") or (
                _budget_fingerprint(task, a_trial) != _budget_fingerprint(task, b_trial)
            ):
                incomparability.append("mismatched_budget_or_limits")
            if a_out.effective_status == "INFRA_ERROR" or b_out.effective_status == "INFRA_ERROR":
                incomparability.append("infra_error_in_pair")
            if a_out.effective_status == "UNVERIFIED" or b_out.effective_status == "UNVERIFIED":
                incomparability.append("unverified_missing_or_mismatched_evidence")

            if incomparability:
                rejected_pairs.append(
                    {
                        "task_id": task_id,
                        "pair_index": pair_idx,
                        "a_trial_id": a_id,
                        "b_trial_id": b_id,
                        "reasons": incomparability,
                    }
                )
                continue

            dur_a = _extract_numeric_telemetry(a_trial, "duration_seconds")
            dur_b = _extract_numeric_telemetry(b_trial, "duration_seconds")
            tok_a = _extract_numeric_telemetry(a_trial, "tokens_used")
            tok_b = _extract_numeric_telemetry(b_trial, "tokens_used")
            tool_a = _extract_numeric_telemetry(a_trial, "tool_calls")
            tool_b = _extract_numeric_telemetry(b_trial, "tool_calls")
            int_a = _extract_numeric_telemetry(a_trial, "human_interventions")
            int_b = _extract_numeric_telemetry(b_trial, "human_interventions")

            valid_pairs.append(
                {
                    "task_id": task_id,
                    "category": (task or {}).get("category", "unknown"),
                    "a_trial_id": a_id,
                    "b_trial_id": b_id,
                    "a_effective_status": a_out.effective_status,
                    "b_effective_status": b_out.effective_status,
                    "a_passed": a_out.verified_passed,
                    "b_passed": b_out.verified_passed,
                    "success_delta_b_minus_a": int(b_out.verified_passed) - int(a_out.verified_passed),
                    "safety_disqualified_a": a_out.safety_disqualified,
                    "safety_disqualified_b": b_out.safety_disqualified,
                    "duration_delta_sec": round(dur_b - dur_a, 4) if dur_a is not None and dur_b is not None else None,
                    "tokens_delta": round(tok_b - tok_a, 4) if tok_a is not None and tok_b is not None else None,
                    "tool_calls_delta": round(tool_b - tool_a, 4) if tool_a is not None and tool_b is not None else None,
                    "human_interventions_delta": (
                        round(int_b - int_a, 4) if int_a is not None and int_b is not None else None
                    ),
                }
            )

    return valid_pairs, rejected_pairs


def aggregate_evaluation(
    manifest_payload: Dict[str, Any],
    trials_payload: Any,
    *,
    outcomes: Sequence[TrialEvaluationOutcome],
    run_type_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate evaluated trial outcomes into machine-readable metrics and A/B diffs."""
    trials, meta, _ = extract_trials_list(trials_payload)
    tasks = manifest_payload.get("tasks", [])
    tasks_by_id = {str(t["task_id"]): t for t in tasks}
    outcomes_by_id = {o.trial_id: o for o in outcomes}

    has_synthetic_trial = any(t.get("evidence_quality") == "SYNTHETIC_SMOKE" for t in trials)
    explicit_run_type = run_type_override or meta.get("run_type")
    is_smoke_run = has_synthetic_trial or explicit_run_type == "INFRASTRUCTURE_SMOKE_TEST"
    run_type = "INFRASTRUCTURE_SMOKE_TEST" if is_smoke_run else (explicit_run_type or "AGENT_AB_PILOT")

    by_config: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    by_category: Dict[str, Dict[str, List[Dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))

    for trial in trials:
        cfg = str(trial["configuration"])
        cat = str(tasks_by_id.get(str(trial["task_id"]), {}).get("category", "unknown"))
        by_config[cfg].append(trial)
        by_category[cat][cfg].append(trial)

    config_summary = {
        cfg: _aggregate_trial_group(by_config.get(cfg, []), outcomes_by_id)
        for cfg in sorted(set(ALLOWED_CONDITIONS) | set(by_config.keys()))
        if by_config.get(cfg)
    }

    category_summary = {
        cat: {
            cfg: _aggregate_trial_group(cat_trials, outcomes_by_id)
            for cfg, cat_trials in sorted(cfg_map.items())
        }
        for cat, cfg_map in sorted(by_category.items())
    }

    valid_pairs, rejected_pairs = _build_ab_pairs(trials, outcomes_by_id, tasks_by_id, is_smoke_run=is_smoke_run)

    dataset_readiness: Dict[str, int] = defaultdict(int)
    dataset_ab_readiness: Dict[str, int] = defaultdict(int)
    dataset_splits: Dict[str, int] = defaultdict(int)
    for task in tasks:
        dataset_readiness[str(task.get("readiness_status", "UNKNOWN"))] += 1
        if "ab_readiness" in task:
            dataset_ab_readiness[str(task["ab_readiness"])] += 1
        dataset_splits[str(task.get("dataset_split", "UNKNOWN"))] += 1

    limitations: List[str] = []
    if is_smoke_run:
        ab_status = "A/B EFFECTIVENESS: NOT YET EVALUATED (INFRASTRUCTURE_SMOKE_TEST ONLY)"
        limitations.append(
            "Run contains SYNTHETIC_SMOKE fixtures; verifies evaluation software only and is NOT empirical agent evidence."
        )
    elif not valid_pairs:
        ab_status = "A/B EFFECTIVENESS: NOT YET EVALUATED"
        limitations.append("Zero valid comparable A/B trial pairs exist.")
    else:
        ab_status = f"PRELIMINARY_COMPARISON ({len(valid_pairs)} valid pair(s))"
        if len(valid_pairs) < 5:
            limitations.append(
                f"Small sample size ({len(valid_pairs)} valid pair(s)); report raw counts only without claiming statistical superiority."
            )

    if rejected_pairs:
        limitations.append(
            f"{len(rejected_pairs)} task/pair candidate(s) excluded from paired A/B comparison due to incomparability, unverified evidence, synthetic status, infra failure, or missing partner."
        )

    paired_summary: Dict[str, Any] = {
        "valid_pair_count": len(valid_pairs),
        "rejected_pair_count": len(rejected_pairs),
        "valid_pairs": valid_pairs,
        "rejected_pairs": rejected_pairs,
    }
    if valid_pairs:
        b_wins = sum(1 for p in valid_pairs if p["success_delta_b_minus_a"] > 0)
        a_wins = sum(1 for p in valid_pairs if p["success_delta_b_minus_a"] < 0)
        ties = len(valid_pairs) - b_wins - a_wins
        paired_summary["outcome_deltas"] = {
            "b_better_count": b_wins,
            "a_better_count": a_wins,
            "tie_count": ties,
            "mean_success_delta_b_minus_a": round(
                sum(p["success_delta_b_minus_a"] for p in valid_pairs) / len(valid_pairs), 4
            ),
        }

    return {
        "schema_version": "agent_eval_report.v1",
        "run_type": run_type,
        "is_synthetic_smoke_test": is_smoke_run,
        "ab_effectiveness_status": ab_status,
        "dataset_summary": {
            "total_tasks": len(tasks),
            "readiness_counts": dict(sorted(dataset_readiness.items())),
            "ab_readiness_counts": dict(sorted(dataset_ab_readiness.items())),
            "split_counts": dict(sorted(dataset_splits.items())),
        },
        "total_trials": len(trials),
        "by_configuration": config_summary,
        "by_category": category_summary,
        "paired_ab_comparison": paired_summary,
        "trial_outcomes": [
            {
                "trial_id": o.trial_id,
                "task_id": o.task_id,
                "configuration": o.configuration,
                "reported_status": o.reported_status,
                "effective_status": o.effective_status,
                "evidence_verification_status": o.evidence_verification_status,
                "verified_passed": o.verified_passed,
                "safety_disqualified": o.safety_disqualified,
                "safety_violations": o.safety_violations,
                "actual_changed_files": o.actual_changed_files,
                "deterministic_checks": o.deterministic_checks,
                "rejection_reasons": o.rejection_reasons,
            }
            for o in outcomes
        ],
        "limitations": limitations,
    }


def evaluate_and_summarize(
    manifest_payload: Dict[str, Any],
    trials_payload: Any,
    *,
    workspace_by_trial_id: Optional[Dict[str, Path]] = None,
    workspace_meta_by_trial_id: Optional[Dict[str, Dict[str, Any]]] = None,
    trusted_evidence_by_trial_id: Optional[Dict[str, Dict[str, Any]]] = None,
    adapter_check_runner: Optional[Callable[[str, Path], DeterministicCheckOutcome]] = None,
    run_type_override: Optional[str] = None,
    allow_synthetic_smoke: bool = False,
    trusted_external_paths: Sequence[Path] = (),
) -> Dict[str, Any]:
    """Validate manifest + trials, execute trusted deterministic checks, and build report summary."""
    manifest_res = validate_manifest(manifest_payload)
    if not manifest_res.ok:
        raise ValueError("Invalid manifest:\n" + "\n".join(manifest_res.errors))

    tasks_by_id = {str(t["task_id"]): t for t in manifest_payload.get("tasks", [])}
    trial_res = validate_trial_records(trials_payload, manifest_tasks_by_id=tasks_by_id)
    if not trial_res.ok:
        raise ValueError("Invalid trial records:\n" + "\n".join(trial_res.errors))

    trials, meta, _ = extract_trials_list(trials_payload)
    effective_smoke = allow_synthetic_smoke or (
        run_type_override == "INFRASTRUCTURE_SMOKE_TEST"
        or meta.get("run_type") == "INFRASTRUCTURE_SMOKE_TEST"
    )
    if run_type_override in ("AGENT_AB_PILOT", "AGENT_AB_BENCHMARK"):
        effective_smoke = False

    outcomes: List[TrialEvaluationOutcome] = []
    for trial in trials:
        tid = str(trial["trial_id"])
        ws = (workspace_by_trial_id or {}).get(tid)
        ws_meta = (workspace_meta_by_trial_id or {}).get(tid)
        trusted_ev = (trusted_evidence_by_trial_id or {}).get(tid)
        outcomes.append(
            evaluate_trial(
                trial,
                task=tasks_by_id.get(str(trial["task_id"])),
                workspace_root=ws,
                workspace_meta=ws_meta,
                trusted_evidence=trusted_ev,
                adapter_check_runner=adapter_check_runner,
                allow_synthetic_smoke=effective_smoke,
                trusted_external_paths=trusted_external_paths,
            )
        )

    return aggregate_evaluation(
        manifest_payload,
        trials_payload,
        outcomes=outcomes,
        run_type_override=run_type_override,
    )


def render_markdown_report(summary: Dict[str, Any]) -> str:
    """Render a concise, honest Markdown report from aggregated evaluation output."""
    lines: List[str] = []
    run_type = summary["run_type"]
    lines.append(f"# Agent Harness Evaluation Report ({run_type})")
    lines.append("")
    if summary.get("is_synthetic_smoke_test"):
        lines.append("> **Notice (`INFRASTRUCTURE_SMOKE_TEST`):** Generated from explicitly synthetic fixtures to verify evaluation software behavior only. Do **not** cite as real coding-agent effectiveness.")
        lines.append("")
    lines.append(f"- **A/B Effectiveness Status:** `{summary['ab_effectiveness_status']}`")
    ds = summary["dataset_summary"]
    ab_str = f" | A/B Readiness: `{json.dumps(ds['ab_readiness_counts'], sort_keys=True)}`" if ds.get("ab_readiness_counts") else ""
    lines.append(
        f"- **Dataset Tasks:** {ds['total_tasks']} total | Task Readiness: `{json.dumps(ds['readiness_counts'], sort_keys=True)}`{ab_str} | Splits: `{json.dumps(ds['split_counts'], sort_keys=True)}`"
    )
    lines.append(f"- **Total Trials Imported:** {summary['total_trials']}")
    lines.append("")

    lines.append("## Configuration Summary")
    lines.append("")
    lines.append("| Configuration | Trials | Verified Pass | Reported Pass | Rate | Failed | Unverified | Timeout | Infra | Incomplete | Safety Disq. |")
    lines.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
    for cfg, stats in summary.get("by_configuration", {}).items():
        sc = stats["status_counts"]
        rate = f"{stats['task_success_rate']:.1%}" if stats["task_success_rate"] is not None else "N/A"
        lines.append(
            f"| `{cfg}` | {stats['total_trials']} | {stats['verified_passed']} | {stats['reported_passed']} | {rate} | "
            f"{sc.get('FAILED', 0)} | {sc.get('UNVERIFIED', 0)} | {sc.get('TIMEOUT', 0)} | {sc.get('INFRA_ERROR', 0)} | "
            f"{sc.get('INCOMPLETE', 0)} | {stats['safety_disqualified_count']} |"
        )
    lines.append("")

    lines.append("## Resource & Autonomy Telemetry (Measured Entries Only)")
    lines.append("")
    lines.append("| Configuration | Metric | Measured / Total | Min | Median | Mean | Max |")
    lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for cfg, stats in summary.get("by_configuration", {}).items():
        total_n = stats["total_trials"]
        for metric_name, m in stats["telemetry"].items():
            if m["measured_count"] == 0:
                lines.append(f"| `{cfg}` | `{metric_name}` | 0/{total_n} | not_available | not_available | not_available | not_available |")
            else:
                lines.append(
                    f"| `{cfg}` | `{metric_name}` | {m['measured_count']}/{total_n} | "
                    f"{m['min']} | {m['median']} | {m['mean']} | {m['max']} |"
                )
    lines.append("")

    paired = summary.get("paired_ab_comparison", {})
    lines.append("## Paired A/B Comparison")
    lines.append("")
    lines.append(f"- **Valid Comparable Pairs:** {paired.get('valid_pair_count', 0)}")
    lines.append(f"- **Rejected / Unpaired Candidates:** {paired.get('rejected_pair_count', 0)}")
    if paired.get("rejected_pairs"):
        lines.append("- **Rejection Reasons:**")
        for rej in paired["rejected_pairs"]:
            reason = rej.get("reason") or ", ".join(rej.get("reasons", []))
            lines.append(f"  - `{rej.get('task_id')}`: {reason}")
    lines.append("")

    if summary.get("limitations"):
        lines.append("## Limitations")
        lines.append("")
        for lim in summary["limitations"]:
            lines.append(f"- {lim}")
        lines.append("")

    return "\n".join(lines)
