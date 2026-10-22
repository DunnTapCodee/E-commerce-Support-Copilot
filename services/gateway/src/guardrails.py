
"""Business safety guardrail checks for API Gateway."""

import math
from typing import List, Optional

from contracts.schemas import (
    GuardrailResult,
    IntentPredictionResponse,
    RetrievedDocument,
)
from services.gateway.src.config import (
    FINANCIAL_INTENTS,
    INTENT_CONFIDENCE_THRESHOLD,
)


def _escalate(reason: str) -> GuardrailResult:
    """Create a safe decision that prevents LLM generation."""
    return GuardrailResult(
        allow_llm=False,
        action_type="ESCALATE_HUMAN",
        reason=reason,
    )


def evaluate_intent_guard(
    intent_resp: IntentPredictionResponse,
) -> GuardrailResult:
    """Reject invalid, uncertain, or unsupported intent predictions."""

    confidence = intent_resp.confidence

    # Fail closed if confidence is invalid.
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        return _escalate(
            "Confidence không hợp lệ; cần nhân viên kiểm tra."
        )

    if not intent_resp.is_in_scope:
        return _escalate(
            "Yêu cầu nằm ngoài phạm vi hỗ trợ; cần nhân viên xử lý."
        )

    if confidence < INTENT_CONFIDENCE_THRESHOLD:
        return _escalate(
            f"Độ tin cậy thấp ({confidence:.0%}); "
            "cần nhân viên xác nhận ý định."
        )

    if not intent_resp.intent or not intent_resp.intent.strip():
        return _escalate(
            "Không xác định được ý định của khách hàng."
        )

    if intent_resp.intent == "human_agent":
        return _escalate(
            "Khách hàng yêu cầu hỗ trợ trực tiếp từ nhân viên."
        )

    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        reason="Ý định hợp lệ, nằm trong phạm vi và đạt ngưỡng tin cậy.",
    )


def evaluate_financial_guard(
    intent: str,
) -> Optional[GuardrailResult]:
    """Prevent financial intents from triggering automated decisions."""

    if intent in FINANCIAL_INTENTS:
        return GuardrailResult(
            allow_llm=False,
            action_type="DIRECT_REFUND_FORM",
            reason=(
                "Yêu cầu tài chính cần nhân viên đối soát và quyết định. "
                "Hệ thống không tự phê duyệt hoặc thực hiện giao dịch."
            ),
        )

    return None


def evaluate_policy_guard(
    citations: List[RetrievedDocument],
) -> GuardrailResult:
    """Require usable, active policy documents before LLM generation."""

    if not citations:
        return _escalate(
            "Không tìm thấy tài liệu chính sách làm căn cứ trả lời."
        )

    invalid_docs = [
        doc for doc in citations
        if not doc.doc_id
        or not doc.content
        or not doc.content.strip()
        or not doc.is_active
    ]

    if invalid_docs:
        invalid_ids = ", ".join(
            doc.doc_id or "<missing-doc-id>"
            for doc in invalid_docs
        )
        return _escalate(
            "Tài liệu không hợp lệ hoặc đã hết hiệu lực: "
            f"{invalid_ids}. Không được dùng làm căn cứ trả lời."
        )

    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        reason=(
            "Các tài liệu được cung cấp đều có nội dung "
            "và đang được đánh dấu có hiệu lực."
        ),
    )
