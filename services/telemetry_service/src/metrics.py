"""Telemetry metrics calculation for human-in-the-loop interactions.
Includes:
1. Normalized Levenshtein Edit Distance (measuring draft reuse).
2. Rubber-stamping detection (Automation bias: agent approving long draft in < 1.5s).
3. Continual Learning data candidate selector.
4. Data / Concept Drift Detector (monitoring OOS spike, Low Confidence, NED degradation, Rubber-stamping).
5. Shadow Mode Comparison Evaluator (comparing primary model vs shadow candidate on live traffic).
Aligns with CMU MLIP Chapters 16 & 19: Data Quality & Testing and Experimenting in Production.
"""
import re
from typing import Any, Dict, List, Optional, Tuple


def levenshtein_distance(s1: str, s2: str) -> int:
    """Compute standard Levenshtein edit distance between two strings."""
    if s1 == s2:
        return 0
    if not s1:
        return len(s2)
    if not s2:
        return len(s1)

    len_s1, len_s2 = len(s1), len(s2)
    dp = [[0] * (len_s2 + 1) for _ in range(len_s1 + 1)]

    for i in range(len_s1 + 1):
        dp[i][0] = i
    for j in range(len_s2 + 1):
        dp[0][j] = j

    for i in range(1, len_s1 + 1):
        for j in range(1, len_s2 + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,      # deletion
                dp[i][j - 1] + 1,      # insertion
                dp[i - 1][j - 1] + cost # substitution
            )

    return dp[len_s1][len_s2]


def compute_normalized_levenshtein(raw_draft: str, final_text: str) -> float:
    """Compute normalized Levenshtein distance between 0.0 (identical) and 1.0 (completely rewritten)."""
    raw = (raw_draft or "").strip()
    final = (final_text or "").strip()

    if not raw and not final:
        return 0.0
    max_len = max(len(raw), len(final))
    if max_len == 0:
        return 0.0

    raw_dist = levenshtein_distance(raw, final)
    return round(float(raw_dist / max_len), 4)


def detect_rubber_stamping(
    handling_time_ms: int,
    raw_draft: str,
    action: str,
) -> bool:
    """Detect suspected automation bias (rubber-stamping).
    Occurs when human agent approves a non-trivial draft (> 80 chars) within less than 1.5 seconds.
    """
    if action != "APPROVE":
        return False
    draft_len = len((raw_draft or "").strip())
    # Reading speed of humans is ~200-250 words/min (~20 chars/sec).
    # A draft of 100 chars takes >= 4-5 seconds to read and verify.
    if draft_len > 80 and handling_time_ms < 1500:
        return True
    return False


def is_continual_learning_candidate(
    raw_draft: str,
    final_text: str,
    action: str,
    edit_dist: float,
) -> bool:
    """Select high-value feedback samples for continual learning few-shot buffers."""
    if action not in {"APPROVE", "EDIT"}:
        return False
    if not final_text or len(final_text.strip()) < 30:
        return False
    # If agent made thoughtful corrections (edit distance between 0.10 and 0.85)
    # or approved a high quality draft
    if action == "APPROVE" or (action == "EDIT" and 0.10 <= edit_dist <= 0.85):
        return True
    return False


def detect_telemetry_drift(
    recent_logs: List[Dict[str, Any]],
    baseline_avg_ned: float = 0.25,
    max_oos_rate: float = 0.25,
    max_rubber_stamp_rate: float = 0.20,
    max_low_conf_rate: float = 0.30,
) -> Dict[str, Any]:
    """Detect Data Drift, Concept Drift, and Automation Bias Drift from recent telemetry logs.
    Aligns with CMU MLIP Chapters 16 (Data Quality) & 19 (Testing in Production).
    """
    if not recent_logs:
        return {
            "drift_detected": False,
            "sample_size": 0,
            "oos_rate": 0.0,
            "low_confidence_rate": 0.0,
            "avg_edit_distance": 0.0,
            "rubber_stamping_rate": 0.0,
            "alerts": [],
        }

    total = len(recent_logs)
    oos_count = sum(1 for r in recent_logs if r.get("predicted_intent") in {"out_of_scope", "unknown_query"})
    low_conf_count = sum(1 for r in recent_logs if float(r.get("intent_confidence") or 0.0) < 0.65)

    reviewed_logs = [r for r in recent_logs if r.get("human_action") in {"APPROVE", "EDIT", "REJECT"}]
    ned_values = [float(r["edit_distance"]) for r in reviewed_logs if r.get("edit_distance") is not None]
    rubber_count = sum(1 for r in reviewed_logs if int(r.get("is_rubber_stamping") or 0) == 1)

    oos_rate = round(oos_count / total, 4)
    low_conf_rate = round(low_conf_count / total, 4)
    avg_ned = round(sum(ned_values) / len(ned_values), 4) if ned_values else 0.0
    rubber_rate = round(rubber_count / len(reviewed_logs), 4) if reviewed_logs else 0.0

    alerts: List[str] = []
    if oos_rate > max_oos_rate:
        alerts.append(
            f"DATA_DRIFT: Out-of-scope rate ({oos_rate:.1%}) exceeds threshold ({max_oos_rate:.1%}). New customer topics detected."
        )
    if low_conf_rate > max_low_conf_rate:
        alerts.append(
            f"COVARIATE_SHIFT: Low-confidence intent rate ({low_conf_rate:.1%}) exceeds threshold ({max_low_conf_rate:.1%})."
        )
    if ned_values and avg_ned > (baseline_avg_ned + 0.15):
        alerts.append(
            f"CONCEPT_DRIFT: Average staff edit distance NED ({avg_ned:.2f}) degraded significantly above baseline ({baseline_avg_ned:.2f})."
        )
    if reviewed_logs and rubber_rate > max_rubber_stamp_rate:
        alerts.append(
            f"AUTOMATION_BIAS_DRIFT: Staff rubber-stamping rate ({rubber_rate:.1%}) exceeds safe threshold ({max_rubber_stamp_rate:.1%})."
        )

    return {
        "drift_detected": len(alerts) > 0,
        "sample_size": total,
        "reviewed_count": len(reviewed_logs),
        "oos_rate": oos_rate,
        "low_confidence_rate": low_conf_rate,
        "avg_edit_distance": avg_ned,
        "rubber_stamping_rate": rubber_rate,
        "alerts": alerts,
    }


def evaluate_shadow_comparison(
    primary_draft: str,
    shadow_draft: str,
    expected_entities: Optional[Dict[str, str]] = None,
    primary_latency_ms: float = 0.0,
    shadow_latency_ms: float = 0.0,
) -> Dict[str, Any]:
    """Compare Primary production model output against a Shadow candidate model output
    without exposing the shadow output to end-users (CMU MLIP Ch. 19 Shadow Deployment).
    """
    divergence_ned = compute_normalized_levenshtein(primary_draft, shadow_draft)
    primary_citations = sorted(set(re.findall(r"POL-[A-Z0-9_-]+", primary_draft, re.IGNORECASE)))
    shadow_citations = sorted(set(re.findall(r"POL-[A-Z0-9_-]+", shadow_draft, re.IGNORECASE)))

    shadow_missing_entities: List[str] = []
    if expected_entities:
        shadow_lower = (shadow_draft or "").lower()
        for k, v in expected_entities.items():
            if str(v).lower() not in shadow_lower:
                shadow_missing_entities.append(f"{k}:{v}")

    shadow_passed_safety = (
        len(shadow_missing_entities) == 0
        and len((shadow_draft or "").strip()) >= 30
        and "traceback" not in (shadow_draft or "").lower()
    )

    return {
        "divergence_ned": divergence_ned,
        "primary_citations": [c.upper() for c in primary_citations],
        "shadow_citations": [c.upper() for c in shadow_citations],
        "citation_match": [c.upper() for c in primary_citations] == [c.upper() for c in shadow_citations],
        "shadow_missing_entities": shadow_missing_entities,
        "shadow_passed_safety": shadow_passed_safety,
        "latency_delta_ms": round(shadow_latency_ms - primary_latency_ms, 2),
        "promotion_ready": shadow_passed_safety and (len(shadow_citations) >= len(primary_citations)),
    }


