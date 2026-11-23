"""Runtime Safety Guardrails & Prompt Injection Detection for Conversation Service.
Complies with CMU MLIP Chapter 18: System Quality (Fail-closed Safety Envelopes).
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from contracts.schemas import GuardrailResult, RetrievedDocument

PROMPT_INJECTION_PATTERNS = [
    re.compile(r"(ignore|disregard|forget)\s+(?:all\s+)?(?:previous\s+)?(instructions|prompts|rules)", re.IGNORECASE),
    re.compile(r"(bỏ qua|quên đi|hủy bỏ)\s+(mọi|tất cả)?\s*(hướng dẫn|chỉ thị|quy tắc|quy định)", re.IGNORECASE),
    re.compile(r"(in ra|tiết lộ|show me|reveal)\s+(system prompt|prompts hệ thống|chỉ dẫn hệ thống)", re.IGNORECASE),
    re.compile(r"\b(jailbreak|dan mode|bẻ khóa ai|developer mode)\b", re.IGNORECASE),
    re.compile(r"\b(đóng vai là|act as a|pretend you are)\s+(unrestricted|không bị giới hạn)", re.IGNORECASE),
]


def evaluate_prompt_injection(query: str) -> Tuple[bool, Optional[str]]:
    """Detect prompt injection and adversarial jailbreak attempts."""
    for pattern in PROMPT_INJECTION_PATTERNS:
        match = pattern.search(query)
        if match:
            return True, f"Phát hiện mẫu Prompt Injection / Jailbreak: '{match.group(0)}'"
    return False, None


def evaluate_runtime_safety_envelope(
    customer_query: str,
    draft_text: str,
    order_data: Optional[Dict[str, Any]] = None,
    citations: Optional[List[RetrievedDocument]] = None,
) -> GuardrailResult:
    """Rigorous runtime safety envelope:
    1. Prompt Injection Attack check on query.
    2. Unauthorized Financial Action check on draft.
    3. Fail-closed defense.
    """
    violations: List[str] = []

    # 1. Prompt Injection Check
    is_injection, injection_msg = evaluate_prompt_injection(customer_query)
    if is_injection:
        violations.append(injection_msg)

    # 2. Financial Hard Gate on Draft
    refund_promise_match = re.search(
        r"(sẽ hoàn lại|đã hoàn|hoàn trả lại số tiền|chuyển khoản lại cho anh/chị|bồi thường)\s+(\d+[\d.,]*\s*(?:đ|vnd|đồng)?)",
        draft_text,
        re.IGNORECASE,
    )
    if refund_promise_match:
        authorized = False
        if order_data:
            order_status = str(order_data.get("status", "")).upper()
            if order_status in {"REFUND_PENDING", "CANCELLED", "RETURN_APPROVED"}:
                authorized = True
        if not authorized:
            violations.append(
                f"LLM tự ý phát ngôn cam kết bồi thường / hoàn tiền trái thẩm quyền: '{refund_promise_match.group(0)}'"
            )

    # 3. Decision
    if violations:
        return GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason=" | ".join(violations),
            is_hard_fail=True,
            violations=violations,
        )

    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        reason="Đạt chuẩn kiểm định an toàn (Safety Envelope passed).",
        is_hard_fail=False,
    )

