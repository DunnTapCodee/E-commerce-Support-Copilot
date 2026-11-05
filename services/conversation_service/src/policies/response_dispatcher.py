"""Response policy dispatcher implementing the 5 guarded response rules."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from contracts.schemas import (
    GuardrailResult,
    IntentPredictionResponse,
    RetrievedDocument,
)
from services.conversation_service.src.config import (
    DISABLE_CONFIDENCE_GUARD,
    FINANCIAL_INTENTS,
    INTENT_CONFIDENCE_THRESHOLD,
)
from services.conversation_service.src.policies.templates import (
    AGENT_GUIDANCE,
    MACRO_TEMPLATES,
)


class ResponsePolicyDispatcher:
    """Evaluates multi-turn state and determines draft, guidance, and guardrail decision."""

    @staticmethod
    def dispatch(
        user_query: str,
        input_type: str,
        intent_resp: IntentPredictionResponse,
        order_data: Optional[Dict[str, Any]],
        citations: List[RetrievedDocument],
        has_expired_policy: bool,
        is_live_chat: bool,
    ) -> Tuple[GuardrailResult, str, Optional[str], Optional[str], str]:
        """Dispatch policy based on dialogue state.
        Returns:
            (guardrail_decision, draft_text, suggested_reply, agent_guidance, generation_mode)
        """
        intent_name = intent_resp.intent
        confidence = intent_resp.confidence

        # Case 0: Chitchat greeting or thanks
        if input_type == "chitchat":
            q_lower = user_query.lower()
            if any(k in q_lower for k in ["cam on", "cảm ơn", "thanks", "thank you"]):
                reply = MACRO_TEMPLATES["chitchat_thanks"]
            elif any(k in q_lower for k in ["ok", "vâng", "vang", "đúng", "dung"]):
                reply = MACRO_TEMPLATES["chitchat_confirm"]
            else:
                reply = MACRO_TEMPLATES["chitchat_greeting"]

            guard = GuardrailResult(
                allow_llm=False,
                action_type="CHITCHAT_RESPONSE",
                reason="Tin nhắn xã giao, lịch sự; trả lời tức thì mà không cần gọi ML/RAG.",
            )
            return guard, reply, reply, "🟢 XÃ GIAO: Khách hàng chào hỏi / cảm ơn.", "chitchat_instant"

        # Case 1: Khách đòi gặp người
        if intent_name == "human_agent" or is_live_chat:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason="Khách hàng yêu cầu hỗ trợ trực tiếp từ nhân viên.",
            )
            return (
                guard,
                MACRO_TEMPLATES["live_chat_activated"],
                None,
                AGENT_GUIDANCE["live_chat"],
                "live_chat_handover",
            )

        # Case 2: Rủi ro tài chính (Hoàn tiền / Lỗi thanh toán)
        if intent_name in FINANCIAL_INTENTS:
            order_id = (order_data.get("order_id") if order_data else None) or "của bạn"
            if order_id and order_id != "của bạn":
                suggested = MACRO_TEMPLATES["refund_pending"].format(order_id=order_id)
            else:
                suggested = MACRO_TEMPLATES["refund_general"]

            guard = GuardrailResult(
                allow_llm=False,
                action_type="DIRECT_REFUND_FORM",
                reason="Yêu cầu tài chính nhạy cảm. LLM bị khóa tuyệt đối để phòng tránh rủi ro hoàn tiền tự động.",
            )
            draft = (
                "Hệ thống phát hiện yêu cầu hoàn tiền / thanh toán. "
                "Vui lòng nhấn nút 'Xem hồ sơ đối soát' để kiểm tra dữ liệu đơn hàng và quyết định thủ công."
            )
            return guard, draft, suggested, AGENT_GUIDANCE["financial_risk"], "blocked_financial"

        # Case 3: Confidence thấp (< 60%) hoặc Ngoài phạm vi
        if not DISABLE_CONFIDENCE_GUARD and (confidence < INTENT_CONFIDENCE_THRESHOLD or not intent_resp.is_in_scope):
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason=f"Độ tin cậy thấp ({confidence:.1%}) hoặc ngoài phạm vi hỗ trợ; cần nhân viên xem lại ngữ cảnh.",
            )
            draft = "[CẦN NHÂN VIÊN XỬ LÝ: Vui lòng đọc lại ngữ cảnh đoạn chat và tự soạn phản hồi cho khách.]"
            return guard, draft, None, AGENT_GUIDANCE["low_confidence"], "low_confidence_abstain"

        # Case 4: Dính chính sách cũ hết hạn (Temporal Policy Trap)
        if has_expired_policy:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason="Tài liệu chính sách trích xuất đã hết hiệu lực theo mốc thời gian (Temporal Policy Guard).",
                temporal_status="EXPIRED",
            )
            draft = "[Cần nhân viên xử lý: Chính sách cũ đã hết hạn, sử dụng câu đệm an toàn để phản hồi.]"
            return (
                guard,
                draft,
                MACRO_TEMPLATES["expired_policy_buffer"],
                AGENT_GUIDANCE["expired_policy"],
                "blocked_expired_policy",
            )

        # Case 5: Happy path (Cho phép LLM sinh nháp)
        guard = GuardrailResult(
            allow_llm=True,
            action_type="PROCEED_TO_LLM",
            reason="Ý định hợp lệ, chính sách còn hạn và đạt ngưỡng tin cậy.",
        )
        return guard, "", None, AGENT_GUIDANCE["happy_path"], "proceed_to_llm"
