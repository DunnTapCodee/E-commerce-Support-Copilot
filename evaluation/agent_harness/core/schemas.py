"""Project-agnostic schema definitions and validators for Agent Harness evaluation.

Pure Python standard library only. Contains zero repository-specific assumptions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

ALLOWED_CONDITIONS = ("A_BASELINE", "B_FULL_HARNESS")
ALLOWED_DATASET_SPLITS = ("development", "pilot", "held_out")
ALLOWED_READINESS_STATUSES = ("EXECUTABLE", "PARTIAL", "NOT_READY")
ALLOWED_AB_READINESS_STATUSES = ("AB_READY", "PARTIAL", "NOT_AB_READY")
ALLOWED_GRADER_TYPES = ("deterministic", "hybrid", "manual_rubric")
ALLOWED_TRIAL_STATUSES = (
    "PASSED",
    "FAILED",
    "TIMEOUT",
    "INFRA_ERROR",
    "INCOMPLETE",
    "SAFETY_DISQUALIFIED",
)
ALLOWED_EFFECTIVE_STATUSES = (
    "PASSED",
    "FAILED",
    "UNVERIFIED",
    "TIMEOUT",
    "INFRA_ERROR",
    "INCOMPLETE",
    "SAFETY_DISQUALIFIED",
)
ALLOWED_EVIDENCE_QUALITY = (
    "INDEPENDENT_VERIFIED",
    "SELF_REPORT_ONLY",
    "SYNTHETIC_SMOKE",
    "LIMITED_ISOLATION",
    "MISSING",
)
ALLOWED_RUN_TYPES = ("INFRASTRUCTURE_SMOKE_TEST", "AGENT_AB_PILOT", "AGENT_AB_BENCHMARK")

REQUIRED_TASK_FIELDS = (
    "task_id",
    "category",
    "description",
    "initial_state",
    "allowed_scope",
    "forbidden_actions",
    "acceptance_criteria",
    "grader_definition",
    "timeout_or_budget",
    "dataset_split",
    "readiness_status",
)

REQUIRED_TRIAL_FIELDS = (
    "trial_id",
    "task_id",
    "configuration",
    "model",
    "runtime",
    "base_commit",
    "start_time",
    "end_time",
    "duration_seconds",
    "status",
    "grader_results",
    "verification_evidence",
    "human_interventions",
    "tool_calls",
    "tokens_used",
    "estimated_cost",
    "safety_violations",
    "trace_reference",
    "evidence_quality",
)


@dataclass
class ManifestValidationResult:
    """Validation outcome for a task manifest JSON payload."""

    ok: bool
    task_count: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


@dataclass
class TrialValidationResult:
    """Validation outcome for a list of trial record JSON dicts."""

    ok: bool
    trial_count: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_empty_str_list(value: Any, min_items: int = 1) -> bool:
    return (
        isinstance(value, list)
        and len(value) >= min_items
        and all(_is_non_empty_str(item) for item in value)
    )


def _is_missing_telemetry(value: Any) -> bool:
    return value is None or value == "not_available"


def _validate_iso_timestamp(value: Any, field_name: str, ctx: str) -> Optional[str]:
    if _is_missing_telemetry(value):
        return None
    if not isinstance(value, str) or not value.strip():
        return f"{ctx}: '{field_name}' must be an ISO-8601 string or null/'not_available'."
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return f"{ctx}: '{field_name}' is not a valid ISO-8601 timestamp ({value!r})."
    return None


def _validate_non_negative_number(
    value: Any,
    field_name: str,
    ctx: str,
    *,
    integer_only: bool = False,
) -> Optional[str]:
    if _is_missing_telemetry(value):
        return None
    if isinstance(value, bool):
        return f"{ctx}: '{field_name}' cannot be boolean."
    if integer_only:
        if not isinstance(value, int):
            return f"{ctx}: '{field_name}' must be an integer or null/'not_available'."
    else:
        if not isinstance(value, (int, float)):
            return f"{ctx}: '{field_name}' must be numeric or null/'not_available'."
    if value < 0:
        return f"{ctx}: '{field_name}' cannot be negative ({value})."
    return None


def validate_manifest(payload: Any) -> ManifestValidationResult:
    """Validate structure and readiness invariants of an evaluation task manifest."""
    errors: List[str] = []
    warnings: List[str] = []

    if not isinstance(payload, dict):
        return ManifestValidationResult(ok=False, errors=["Manifest root must be a JSON object."])

    if not _is_non_empty_str(payload.get("schema_version")):
        errors.append("Manifest missing non-empty 'schema_version'.")

    tasks = payload.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        errors.append("Manifest 'tasks' must be a non-empty list.")
        return ManifestValidationResult(ok=False, errors=errors, warnings=warnings)

    seen_ids: set[str] = set()
    for idx, task in enumerate(tasks):
        ctx = f"tasks[{idx}]"
        if not isinstance(task, dict):
            errors.append(f"{ctx}: task entry must be a JSON object.")
            continue

        for req in REQUIRED_TASK_FIELDS:
            if req not in task:
                errors.append(f"{ctx}: missing required field '{req}'.")

        task_id = task.get("task_id")
        if not _is_non_empty_str(task_id):
            errors.append(f"{ctx}: 'task_id' must be a non-empty string.")
        else:
            ctx = f"task {task_id}"
            if task_id in seen_ids:
                errors.append(f"{ctx}: duplicate task_id '{task_id}'.")
            seen_ids.add(task_id)

        if not _is_non_empty_str(task.get("category")):
            errors.append(f"{ctx}: 'category' must be a non-empty string.")
        if not _is_non_empty_str(task.get("description")):
            errors.append(f"{ctx}: 'description' must be a non-empty string.")

        initial_state = task.get("initial_state")
        if not isinstance(initial_state, dict) or not _is_non_empty_str(initial_state.get("base_commit")):
            errors.append(f"{ctx}: 'initial_state' must be an object with non-empty 'base_commit'.")
        elif "required_files" in initial_state:
            req_files = initial_state.get("required_files")
            if not isinstance(req_files, list) or not all(_is_non_empty_str(f) for f in req_files):
                errors.append(f"{ctx}: initial_state.required_files must be a list of non-empty strings.")

        if not _is_non_empty_str_list(task.get("allowed_scope"), min_items=1):
            errors.append(f"{ctx}: 'allowed_scope' must be a non-empty list of path strings.")
        if not _is_non_empty_str_list(task.get("forbidden_actions"), min_items=1):
            errors.append(f"{ctx}: 'forbidden_actions' must be a non-empty list of strings.")
        if not _is_non_empty_str_list(task.get("acceptance_criteria"), min_items=1):
            errors.append(f"{ctx}: 'acceptance_criteria' must be a non-empty list of strings.")

        split = task.get("dataset_split")
        if split not in ALLOWED_DATASET_SPLITS:
            errors.append(f"{ctx}: invalid 'dataset_split' {split!r}; expected one of {ALLOWED_DATASET_SPLITS}.")

        readiness = task.get("readiness_status")
        if readiness not in ALLOWED_READINESS_STATUSES:
            errors.append(
                f"{ctx}: invalid 'readiness_status' {readiness!r}; expected one of {ALLOWED_READINESS_STATUSES}."
            )

        ab_readiness = task.get("ab_readiness")
        if ab_readiness is not None:
            if ab_readiness not in ALLOWED_AB_READINESS_STATUSES:
                errors.append(
                    f"{ctx}: invalid 'ab_readiness' {ab_readiness!r}; expected one of {ALLOWED_AB_READINESS_STATUSES}."
                )
            elif ab_readiness == "AB_READY" and readiness != "EXECUTABLE":
                errors.append(
                    f"{ctx}: ab_readiness='AB_READY' requires readiness_status='EXECUTABLE' (got {readiness!r})."
                )

        grader = task.get("grader_definition")
        if not isinstance(grader, dict):
            errors.append(f"{ctx}: 'grader_definition' must be a JSON object.")
        else:
            g_type = grader.get("grader_type")
            if g_type not in ALLOWED_GRADER_TYPES:
                errors.append(
                    f"{ctx}: invalid grader_definition.grader_type {g_type!r}; expected {ALLOWED_GRADER_TYPES}."
                )
            det_checks = grader.get("deterministic_checks", [])
            if not isinstance(det_checks, list):
                errors.append(f"{ctx}: grader_definition.deterministic_checks must be a list.")
                det_checks = []

            if readiness == "EXECUTABLE":
                if not det_checks and not grader.get("independent_commands"):
                    errors.append(
                        f"{ctx}: readiness_status='EXECUTABLE' requires at least one deterministic check or independent command."
                    )
                if split == "held_out" and not grader.get("held_out_protected", False):
                    errors.append(
                        f"{ctx}: held_out executable task must set grader_definition.held_out_protected=true."
                    )
            if ab_readiness == "AB_READY" and grader.get("manual_rubric_required"):
                errors.append(
                    f"{ctx}: ab_readiness='AB_READY' cannot rely on unautomated manual_rubric_required=true without PARTIAL status."
                )

        budget = task.get("timeout_or_budget")
        if not isinstance(budget, dict):
            errors.append(f"{ctx}: 'timeout_or_budget' must be a JSON object.")
        else:
            max_wall = budget.get("max_wall_minutes")
            if isinstance(max_wall, bool) or not isinstance(max_wall, (int, float)) or max_wall <= 0:
                errors.append(f"{ctx}: timeout_or_budget.max_wall_minutes must be a positive number.")

    return ManifestValidationResult(
        ok=not errors,
        task_count=len(tasks),
        errors=errors,
        warnings=warnings,
    )


def extract_trials_list(payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any], List[str]]:
    """Normalize either a raw list of trials or an envelope object into (trials, metadata, errors)."""
    if isinstance(payload, list):
        return payload, {}, []
    if isinstance(payload, dict):
        trials = payload.get("trials")
        if not isinstance(trials, list):
            return [], payload, ["Trial bundle object must contain a 'trials' list."]
        meta = {k: v for k, v in payload.items() if k != "trials"}
        return trials, meta, []
    return [], {}, ["Trials payload must be a JSON list or an object with a 'trials' list."]


def validate_trial_records(
    payload: Any,
    manifest_tasks_by_id: Optional[Dict[str, Dict[str, Any]]] = None,
    allowed_conditions: Tuple[str, ...] = ALLOWED_CONDITIONS,
) -> TrialValidationResult:
    """Validate trial record structure, types, telemetry bounds, and manifest alignment."""
    errors: List[str] = []
    warnings: List[str] = []

    trials, meta, extract_errors = extract_trials_list(payload)
    if extract_errors:
        return TrialValidationResult(ok=False, errors=extract_errors)

    run_type = meta.get("run_type")
    if run_type is not None and run_type not in ALLOWED_RUN_TYPES:
        errors.append(f"Invalid envelope run_type {run_type!r}; expected one of {ALLOWED_RUN_TYPES}.")

    seen_trial_ids: set[str] = set()
    for idx, trial in enumerate(trials):
        ctx = f"trials[{idx}]"
        if not isinstance(trial, dict):
            errors.append(f"{ctx}: trial record must be a JSON object.")
            continue

        for req in REQUIRED_TRIAL_FIELDS:
            if req not in trial:
                errors.append(f"{ctx}: missing required field '{req}'.")

        trial_id = trial.get("trial_id")
        if not _is_non_empty_str(trial_id):
            errors.append(f"{ctx}: 'trial_id' must be a non-empty string.")
        else:
            ctx = f"trial {trial_id}"
            if trial_id in seen_trial_ids:
                errors.append(f"{ctx}: duplicate trial_id '{trial_id}'.")
            seen_trial_ids.add(trial_id)

        task_id = trial.get("task_id")
        if not _is_non_empty_str(task_id):
            errors.append(f"{ctx}: 'task_id' must be a non-empty string.")
        elif manifest_tasks_by_id is not None and task_id not in manifest_tasks_by_id:
            errors.append(f"{ctx}: task_id '{task_id}' not found in task manifest.")

        config = trial.get("configuration")
        if config not in allowed_conditions:
            errors.append(f"{ctx}: invalid 'configuration' {config!r}; expected one of {allowed_conditions}.")

        for str_field in ("model", "runtime", "base_commit"):
            if not _is_non_empty_str(trial.get(str_field)):
                errors.append(f"{ctx}: '{str_field}' must be a non-empty string.")

        status = trial.get("status")
        if status not in ALLOWED_TRIAL_STATUSES:
            errors.append(f"{ctx}: invalid 'status' {status!r}; expected one of {ALLOWED_TRIAL_STATUSES}.")

        ev_quality = trial.get("evidence_quality")
        if ev_quality not in ALLOWED_EVIDENCE_QUALITY:
            errors.append(
                f"{ctx}: invalid 'evidence_quality' {ev_quality!r}; expected one of {ALLOWED_EVIDENCE_QUALITY}."
            )

        for ts_field in ("start_time", "end_time"):
            err = _validate_iso_timestamp(trial.get(ts_field), ts_field, ctx)
            if err:
                errors.append(err)

        for num_field, int_only in (
            ("duration_seconds", False),
            ("human_interventions", True),
            ("tool_calls", True),
            ("estimated_cost", False),
        ):
            err = _validate_non_negative_number(trial.get(num_field), num_field, ctx, integer_only=int_only)
            if err:
                errors.append(err)

        tokens = trial.get("tokens_used")
        if not _is_missing_telemetry(tokens):
            if isinstance(tokens, int) and not isinstance(tokens, bool):
                if tokens < 0:
                    errors.append(f"{ctx}: 'tokens_used' cannot be negative.")
            elif isinstance(tokens, dict):
                for t_key, t_val in tokens.items():
                    err = _validate_non_negative_number(t_val, f"tokens_used.{t_key}", ctx, integer_only=True)
                    if err:
                        errors.append(err)
            else:
                errors.append(f"{ctx}: 'tokens_used' must be int, dict, or null/'not_available'.")

        if not isinstance(trial.get("grader_results"), list):
            errors.append(f"{ctx}: 'grader_results' must be a list.")

        ver_ev = trial.get("verification_evidence")
        if not isinstance(ver_ev, dict):
            errors.append(f"{ctx}: 'verification_evidence' must be a JSON object.")

        safety_violations = trial.get("safety_violations")
        if not isinstance(safety_violations, list):
            errors.append(f"{ctx}: 'safety_violations' must be a list.")

        trace_ref = trial.get("trace_reference")
        if not _is_missing_telemetry(trace_ref) and not isinstance(trace_ref, str):
            errors.append(f"{ctx}: 'trace_reference' must be a string or null/'not_available'.")

        if status == "PASSED" and ev_quality == "MISSING":
            errors.append(f"{ctx}: status='PASSED' cannot have evidence_quality='MISSING'.")
        if status == "PASSED" and not trial.get("grader_results"):
            errors.append(f"{ctx}: status='PASSED' requires at least one entry in 'grader_results'.")

    return TrialValidationResult(
        ok=not errors,
        trial_count=len(trials),
        errors=errors,
        warnings=warnings,
    )
