"""Business safety guardrail checks for API Gateway."""
from typing import List, Optional

from contracts.schemas import GuardrailResult, IntentPredictionResponse, RetrievedDocument
from services.gateway.src.config import (
    FINANCIAL_INTENTS,
    INTENT_CONFIDENCE_THRESHOLD,
)


def evaluate_intent_guard(intent_resp: IntentPredictionResponse) -> GuardrailResult:
    """Evaluate confidence threshold and operational scope."""
    if intent_resp.confidence < INTENT_CONFIDENCE_THRESHOLD or not intent_resp.is_in_scope:
        return GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason=f"Độ tin cậy thấp ({intent_resp.confidence:.0%}) hoặc ngoài phạm vi hỗ trợ",
        )
    if intent_resp.intent == "human_agent":
        return GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason="Khách hàng chủ động yêu cầu hỗ trợ trực tiếp từ nhân viên",
        )
    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        reason="Ý định nằm trong phạm vi nghiệp vụ và đạt ngưỡng tin cậy",
    )


def evaluate_financial_guard(intent: str) -> Optional[GuardrailResult]:
    """Intercept refund and payment intents to prevent unauthorized automated transactions."""
    if intent in FINANCIAL_INTENTS:
        return GuardrailResult(
            allow_llm=False,
            action_type="DIRECT_REFUND_FORM",
            reason="Yêu cầu tài chính (hoàn tiền/thanh toán) bắt buộc đối soát thủ công",
        )
    return None


def evaluate_policy_guard(citations: List[RetrievedDocument]) -> GuardrailResult:
    """Verify that cited policy documents exist and are currently active."""
    if not citations:
        return GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason="Không tìm thấy tài liệu chính sách làm căn cứ trả lời",
        )
    inactive_docs = [doc for doc in citations if not doc.is_active]
    if inactive_docs:
        inactive_ids = ", ".join(doc.doc_id for doc in inactive_docs)
        return GuardrailResult(
            allow_llm=False,
            action_type="ESCALATE_HUMAN",
            reason=f"Tài liệu căn cứ đã hết hiệu lực ({inactive_ids})",
        )
    return GuardrailResult(
        allow_llm=True,
        action_type="PROCEED_TO_LLM",
        reason="Tài liệu chính sách hợp lệ và còn hiệu lực",
    )
