"""Telemetry metrics calculation for human-in-the-loop interactions.
Includes:
1. Normalized Levenshtein Edit Distance (measuring draft reuse).
2. Rubber-stamping detection (Automation bias: agent approving long draft in < 1.5s).
3. Continual Learning data candidate selector.
Aligns with CMU MLIP Chapter 19: Testing and Experimenting in Production.
"""
from typing import Tuple


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

