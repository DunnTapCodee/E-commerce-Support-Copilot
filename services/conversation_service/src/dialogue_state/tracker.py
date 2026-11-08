"""Context-augmented query builder and intent transition arbiter using LLM with regex fallback."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from contracts.llm_failover import call_chat_completion_with_failover
from contracts.schemas import IntentPredictionResponse
from services.conversation_service.src.dialogue_state.state import ConversationState

logger = logging.getLogger("dialogue_tracker")


class IntentTracker:
    """Decides whether to preserve existing intent, adapt via context, or switch topics.
    Uses LLM for nuanced transition arbitration with multi-key failover and fast regex fallback.
    """

    @staticmethod
    def build_context_augmented_query(user_text: str, state: ConversationState) -> str:
        """Create a targeted prompt for Intent Service only when utterance is ambiguous or elliptical slot-filling."""
        q_low = user_text.lower().strip()
        words = q_low.split()

        # If user is asking a clear, full question or switching topic, keep query purely raw!
        TOPIC_SWITCH_KEYWORDS = [
            "ưu đãi", "khuyến mãi", "khuyến mại", "voucher", "mã giảm", "coupon", "freeship", "giảm giá",
            "bao nhiêu tiền", "hết bao nhiêu", "tổng tiền", "giá bao nhiêu", "chi phí",
            "trả hàng", "đổi hàng", "đổi trả", "hoàn tiền", "hủy đơn", "huỷ đơn",
            "chính sách", "quy định", "bảo hành", "khiếu nại", "gặp nhân viên"
        ]
        if any(k in q_low for k in TOPIC_SWITCH_KEYWORDS):
            return user_text

        # If utterance is complete (> 5 words), do NOT prepend context tags
        if len(words) > 5:
            return user_text

        if not state.active_intent and not state.active_order_id:
            return user_text

        ctx_parts = []
        if state.active_intent:
            ctx_parts.append(f"PREV_INTENT:{state.active_intent}")
        if state.active_order_id:
            ctx_parts.append(f"ORDER:{state.active_order_id}")
        if state.awaiting_slot:
            ctx_parts.append(f"AWAITING:{state.awaiting_slot}")

        prefix = " ".join(f"[{p}]" for p in ctx_parts)
        return f"{prefix} {user_text}"

    @classmethod
    def _fallback_regex_transition(
        cls,
        user_text: str,
        input_type: str,
        extracted_facts: Dict[str, Any],
        ml_intent_resp: Optional[IntentPredictionResponse],
        state: ConversationState,
    ) -> Tuple[str, float, bool]:
        """Fast heuristic/regex transition arbiter used as fallback or for instant cases."""
        # 1. Chitchat / courtesy bypass: Cleanly preserve active_intent if domain session ongoing
        if input_type == "chitchat":
            if state.active_intent and state.active_intent not in (
                "chitchat_greeting", "chitchat_thanks", "chitchat_confirm", "greeting", "chitchat"
            ):
                return state.active_intent, 0.90, False
            q_low = user_text.lower().strip()
            if any(k in q_low for k in ["cam on", "cảm ơn", "thanks", "thank"]):
                return "chitchat_thanks", 0.95, (state.active_intent != "chitchat_thanks")
            if any(k in q_low for k in ["ok", "oke", "vâng", "vang", "đúng", "dung", "dạ", "thế à", "vậy à", "ừ", "uhm"]):
                return "chitchat_confirm", 0.95, (state.active_intent != "chitchat_confirm")
            return "chitchat_greeting", 0.95, (state.active_intent != "chitchat_greeting")

        # 2. Fact supplement (e.g. user just provides ORD-1003 or product detail)
        if input_type == "fact_supplement" or (extracted_facts and len(user_text.split()) <= 4):
            if state.active_intent and state.active_intent not in (
                "chitchat_greeting", "chitchat_thanks", "chitchat_confirm", "greeting", "chitchat"
            ):
                return state.active_intent, 0.90, False
            elif "order_id" in extracted_facts:
                return "track_order", 0.85, True

        # 3. Negation reversal (e.g. "thôi không hủy nữa, xem bao giờ giao")
        if input_type == "negation_reversal":
            if ml_intent_resp and ml_intent_resp.intent != state.active_intent and ml_intent_resp.confidence >= 0.50:
                return ml_intent_resp.intent, ml_intent_resp.confidence, True
            if state.active_intent == "cancel_order":
                return "delivery_time", 0.75, True

        # 4. ML prediction evaluation
        if ml_intent_resp:
            new_intent = ml_intent_resp.intent
            new_conf = ml_intent_resp.confidence

            # Clear switch if confident (threshold >= 0.50)
            if new_conf >= 0.50:
                switched = (new_intent != state.active_intent)
                return new_intent, new_conf, switched

            # If low confidence but user already has active order and question seems related
            if state.active_intent and new_conf < 0.50:
                if any(k in user_text.lower() for k in ["nó", "đơn", "hàng", "sản phẩm", "ship"]):
                    return state.active_intent, 0.65, False

            return new_intent, new_conf, (new_intent != state.active_intent)

        return state.active_intent or "track_order", 0.50, False

    @classmethod
    async def resolve_intent_transition(
        cls,
        user_text: str,
        input_type: str,
        extracted_facts: Dict[str, Any],
        ml_intent_resp: Optional[IntentPredictionResponse],
        state: ConversationState,
        use_llm: bool = True,
    ) -> Tuple[str, float, bool]:
        """Arbiter deciding the effective intent and confidence.
        Combines fast filter for obvious cases, LLM arbitration with multi-key failover
        for nuanced transitions, and regex fallback upon timeout/error.
        """
        # Case A: Instant deterministic cases (no need to call LLM)
        if input_type in ("chitchat", "fact_supplement") or not state.active_intent:
            return cls._fallback_regex_transition(user_text, input_type, extracted_facts, ml_intent_resp, state)

        # Case B: If ML classifier is extremely confident (>= 0.90) and clearly different topic
        if ml_intent_resp and ml_intent_resp.confidence >= 0.90 and ml_intent_resp.intent != state.active_intent:
            return ml_intent_resp.intent, ml_intent_resp.confidence, True

        # Case C: Nuanced transition / topic arbitration with active_intent -> Consult LLM
        if use_llm and state.active_intent:
            try:
                system_prompt = (
                    "Bạn là chuyên gia phân loại chuyển tiếp ý định (Dialogue State Tracker) cho CSKH E-commerce Tiki.\n"
                    "Nhiệm vụ: Phân tích xem câu hỏi mới của khách hàng đang tiếp tục chủ đề cũ (CONTINUE) hay chuyển sang ý định mới (SWITCH).\n"
                    "12 Intent chuẩn E-commerce Tiki:\n"
                    "- track_order: Tra cứu tình trạng, vị trí đơn hàng.\n"
                    "- cancel_order: Hủy đơn hàng.\n"
                    "- return_product: Đổi trả hàng do lỗi hoặc không vừa ý.\n"
                    "- delivery_time: Hỏi thời gian giao hàng, khi nào nhận được.\n"
                    "- payment_issue: Sự cố thanh toán, chuyển khoản, tiền COD.\n"
                    "- change_shipping_address: Thay đổi địa chỉ nhận hàng, số điện thoại.\n"
                    "- get_discounts: Tìm kiếm, tra cứu mã giảm giá, khuyến mãi, Tiki Xu.\n"
                    "- return_policy: Hỏi chính sách, quy định đổi trả chung.\n"
                    "- refund_policy: Hỏi chính sách hoàn tiền, thời gian tiền về.\n"
                    "- promotion_policy: Hỏi thể lệ khuyến mãi, điều kiện voucher.\n"
                    "- complaint: Khiếu nại dịch vụ, thái độ phục vụ.\n"
                    "- human_agent: Yêu cầu gặp nhân viên trực tiếp.\n"
                    "- out_of_scope: Ngoài phạm vi mua sắm thương mại điện tử Tiki.\n\n"
                    "Chỉ trả về JSON duy nhất:\n"
                    '{"action": "CONTINUE"|"SWITCH", "intent": "<intent_hợp_lý_nhất>", "confidence": 0.85, "reason": "<giải thích ngắn>"}'
                )

                user_prompt = (
                    f"Ý định phiên trước: {state.active_intent}\n"
                    f"Mã đơn liên kết: {state.active_order_id or 'Chưa có'}\n"
                    f"Câu nói mới của khách: \"{user_text}\"\n"
                    f"Phân loại sơ bộ từ ML: {ml_intent_resp.intent if ml_intent_resp else 'None'} "
                    f"(độ tin cậy: {ml_intent_resp.confidence if ml_intent_resp else 0.0})\n"
                    f"Loại đầu vào: {input_type}"
                )

                payload = {
                    "model": "openai-gpt-oss-20b",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 150,
                }

                resp_data = await call_chat_completion_with_failover(payload, timeout=4.0)
                if resp_data and "choices" in resp_data and resp_data["choices"]:
                    raw_text = resp_data["choices"][0].get("message", {}).get("content", "").strip()
                    if raw_text.startswith("```"):
                        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                        raw_text = re.sub(r"\s*```$", "", raw_text)
                    parsed = json.loads(raw_text)
                    action = parsed.get("action", "CONTINUE").upper()
                    intent_cand = parsed.get("intent", state.active_intent)
                    conf = float(parsed.get("confidence", 0.85))

                    if action == "CONTINUE":
                        return state.active_intent, max(conf, 0.85), False
                    else:
                        is_switched = (intent_cand != state.active_intent)
                        return intent_cand, conf, is_switched
            except Exception as exc:
                logger.warning("[DialogueTracker] LLM transition check failed (%s). Falling back to regex.", exc)

        # Fallback to Regex/Heuristics
        return cls._fallback_regex_transition(user_text, input_type, extracted_facts, ml_intent_resp, state)

    @classmethod
    def resolve_intent_transition_sync(
        cls,
        user_text: str,
        input_type: str,
        extracted_facts: Dict[str, Any],
        ml_intent_resp: Optional[IntentPredictionResponse],
        state: ConversationState,
    ) -> Tuple[str, float, bool]:
        """Synchronous wrapper for unit tests and legacy sync callers."""
        return cls._fallback_regex_transition(user_text, input_type, extracted_facts, ml_intent_resp, state)
