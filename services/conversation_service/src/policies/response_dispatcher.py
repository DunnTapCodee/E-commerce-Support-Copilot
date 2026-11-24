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
        unauthorized_order_reason: Optional[str] = None,
        has_multi_order_context: bool = False,
    ) -> Tuple[GuardrailResult, str, Optional[str], Optional[str], str]:
        """Dispatch policy based on dialogue state.
        Returns:
            (guardrail_decision, draft_text, suggested_reply, agent_guidance, generation_mode)
        """
        intent_name = intent_resp.intent
        confidence = intent_resp.confidence

        # Case -1: Prompt Injection & Adversarial Attack Hard Block
        from services.conversation_service.src.policies.safety_guard import (
            detect_brand_competitor_bait,
            detect_fabricated_prior_promise,
            detect_warehouse_seal_request,
            evaluate_prompt_injection,
        )

        is_injection, injection_msg = evaluate_prompt_injection(user_query)
        if is_injection:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason=injection_msg,
                is_hard_fail=True,
                violations=[injection_msg],
            )
            draft = "[CẢNH BÁO AN NINH: Phát hiện tấn công Prompt Injection / Jailbreak. Chuyển cho nhân viên bảo mật xử lý.]"
            return guard, draft, None, "🔴 CẢNH BÁO AN NINH: Nghi vấn người dùng cố tình bẻ khóa chỉ dẫn hệ thống.", "blocked_security_guard"

        # Case -0.5: Cross-customer Order / IDOR Security Block
        if unauthorized_order_reason:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason=unauthorized_order_reason,
                is_hard_fail=True,
                violations=[unauthorized_order_reason],
            )
            draft = MACRO_TEMPLATES["unauthorized_order_access"]
            return (
                guard,
                draft,
                draft,
                AGENT_GUIDANCE["unauthorized_order_access"],
                "blocked_unauthorized_order_access",
            )

        # Case -0.2: Pre-generation Anti-Manipulation, Warehouse Seal & Brand Sensitivity Guards
        # Evaluated before Chitchat (Case 0) and human_agent (Case 1) so greetings or phrasing
        # like "tổng đài viên trước đã đồng ý..." cannot mask manipulation alerts.
        manipulation_msg = detect_fabricated_prior_promise(user_query)
        if manipulation_msg:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason=manipulation_msg,
                is_hard_fail=True,
                violations=[manipulation_msg],
            )
            draft = MACRO_TEMPLATES["manipulation_voucher_escalate"]
            return (
                guard,
                draft,
                draft,
                AGENT_GUIDANCE["manipulation_risk"],
                "blocked_manipulation_guard",
            )

        seal_msg = detect_warehouse_seal_request(user_query)
        if seal_msg:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason=seal_msg,
                is_hard_fail=True,
                violations=[seal_msg],
            )
            draft = MACRO_TEMPLATES["warehouse_seal_blocked"]
            return (
                guard,
                draft,
                draft,
                AGENT_GUIDANCE["warehouse_seal"],
                "blocked_warehouse_guard",
            )

        brand_msg = detect_brand_competitor_bait(user_query)
        if brand_msg:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason=brand_msg,
                is_hard_fail=False,
                violations=[brand_msg],
            )
            draft = MACRO_TEMPLATES["brand_comparison_neutral"]
            return (
                guard,
                draft,
                draft,
                AGENT_GUIDANCE["brand_sensitivity"],
                "blocked_brand_sensitivity",
            )

        # Case 0: Chitchat greeting or thanks
        if input_type == "chitchat" or intent_name.startswith("chitchat_") or intent_name == "greeting":
            q_lower = user_query.lower()
            if any(k in q_lower for k in ["cam on", "cảm ơn", "thanks", "thank you"]) or intent_name == "chitchat_thanks":
                reply = MACRO_TEMPLATES["chitchat_thanks"]
            elif any(k in q_lower for k in ["ok", "oke", "vâng", "vang", "đúng", "dung"]) or intent_name == "chitchat_confirm":
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

        # Case 2b: Câu hỏi Ngoài phạm vi nghiệp vụ (Out of Scope từ Intent Service)
        if intent_name == "out_of_scope":
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason="Câu hỏi nằm ngoài phạm vi hỗ trợ thông tin đơn hàng và mua sắm (Out of Scope).",
            )
            draft = (
                "Dạ em chào anh/chị! Câu hỏi này hiện nằm ngoài phạm vi hỗ trợ thông tin đơn hàng và mua sắm của Tiki rồi ạ 😊. "
                "Anh/chị có cần em hỗ trợ thêm thông tin gì về đơn hàng, vận chuyển hay các chính sách mua sắm trên sàn Tiki không ạ?"
            )
            return (
                guard,
                draft,
                draft,
                "🟡 NGOÀI PHẠM VI HỖ TRỢ: Câu hỏi không thuộc nghiệp vụ sàn. Đã soạn sẵn lời từ chối lịch sự và điều hướng lại cuộc trò chuyện.",
                "out_of_scope_abstain",
            )

        # Case 3: Confidence thấp hoặc Ngoài phạm vi / Dịch vụ phân loại không khả dụng
        intent_unavailable = getattr(intent_resp, "model_name", None) == "unavailable_fallback"
        if intent_unavailable:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason="Dịch vụ phân loại ý định tạm gián đoạn; chuyển nhân viên xử lý.",
            )
            draft = (
                "Dạ em chào anh/chị! Em đã tiếp nhận thông tin yêu cầu của mình. "
                "Em đang chuyển tiếp để nhân viên kiểm tra chi tiết và hỗ trợ anh/chị ngay đây ạ."
            )
            return guard, draft, None, AGENT_GUIDANCE["low_confidence"], "blocked_intent_unavailable"

        if not intent_resp.is_in_scope or intent_name == "unknown_query":
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason="Không xác định được ý định hợp lệ hoặc dịch vụ phân loại tạm gián đoạn; chuyển nhân viên xử lý.",
            )
            draft = (
                "Dạ em chào anh/chị! Em đã tiếp nhận thông tin yêu cầu của mình. "
                "Em đang chuyển tiếp để nhân viên kiểm tra chi tiết và hỗ trợ anh/chị ngay đây ạ."
            )
            return guard, draft, None, AGENT_GUIDANCE["low_confidence"], "blocked_intent_unavailable"

        if not DISABLE_CONFIDENCE_GUARD and confidence < INTENT_CONFIDENCE_THRESHOLD:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason="Yêu cầu nằm ngoài phạm vi chính sách mặc định hoặc cần đối soát ngữ cảnh.",
            )
            draft = (
                "Dạ em chào anh/chị! Em đã tiếp nhận thông tin yêu cầu của mình. "
                "Em đang kiểm tra chi tiết trên hệ thống để hỗ trợ giải đáp cho anh/chị ngay đây ạ. "
                "Anh/chị vui lòng đợi em trong giây lát nhé!"
            )
            return guard, draft, None, AGENT_GUIDANCE["low_confidence"], "low_confidence_abstain"

        # Case 4: Dính chính sách cũ hết hạn (Temporal Policy Trap)
        if has_expired_policy:
            guard = GuardrailResult(
                allow_llm=False,
                action_type="ESCALATE_HUMAN",
                reason="Tài liệu chính sách trích xuất đã hết hiệu lực theo mốc thời gian (Temporal Policy Guard).",
                temporal_status="EXPIRED",
            )
            draft = (
                "Dạ em chào anh/chị, về vấn đề này hiện Tiki đang cập nhật quy định điều khoản mới nhất. "
                "Em xin phép kiểm tra lại và thông tin chính xác đến anh/chị ngay nhé ạ!"
            )
            return (
                guard,
                draft,
                MACRO_TEMPLATES["expired_policy_buffer"],
                AGENT_GUIDANCE["expired_policy"],
                "blocked_expired_policy",
            )

        # Case 4b: Truy vấn đa đơn hàng hợp lệ (đã vượt qua mọi cổng an toàn bắt buộc)
        if has_multi_order_context:
            guard = GuardrailResult(
                allow_llm=True,
                action_type="PROCEED_TO_LLM",
                reason="Phát hiện truy vấn liên quan nhiều đơn hàng của khách; tiến hành liệt kê hoặc xác nhận mã đơn.",
            )
            return (
                guard,
                "",
                None,
                "📦 NHIỀU ĐƠN HÀNG: Hệ thống đã lọc các đơn phù hợp và yêu cầu xác nhận mã đơn cụ thể trước khi thao tác.",
                "multi_order_disambiguation",
            )

        # Case 5: Happy path (Cho phép LLM sinh nháp)
        guard = GuardrailResult(
            allow_llm=True,
            action_type="PROCEED_TO_LLM",
            reason="Ý định hợp lệ, chính sách còn hạn và đạt ngưỡng tin cậy.",
        )
        return guard, "", None, AGENT_GUIDANCE["happy_path"], "proceed_to_llm"
