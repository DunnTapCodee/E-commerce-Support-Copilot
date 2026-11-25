"""Offline / Deterministic Dialogue Intent Transition Fallback.

Isolated from `tracker.py` so keyword-based context tagging and regex transition
heuristics stay cleanly separated from LLM transition arbitration.
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from contracts.schemas import IntentPredictionResponse
from services.conversation_service.src.config import INTENT_CONFIDENCE_THRESHOLD
from services.conversation_service.src.dialogue_state.state import ConversationState

TOPIC_SWITCH_KEYWORDS = (
    "ưu đãi", "khuyến mãi", "khuyến mại", "voucher", "mã giảm", "coupon", "freeship", "giảm giá",
    "bao nhiêu tiền", "hết bao nhiêu", "tổng tiền", "giá bao nhiêu", "chi phí",
    "trả hàng", "đổi hàng", "đổi trả", "hoàn tiền", "hủy đơn", "huỷ đơn",
    "chính sách", "quy định", "bảo hành", "khiếu nại", "gặp nhân viên",
)

_CHITCHAT_INTENTS = frozenset({
    "chitchat_greeting", "chitchat_thanks", "chitchat_confirm", "greeting", "chitchat",
})


class OfflineTrackerFallback:
    """Deterministic context tagging and fallback intent transition rules."""

    @staticmethod
    def build_context_augmented_query(user_text: str, state: ConversationState) -> str:
        """Create a context-tagged query only when utterance is short/elliptical slot-filling."""
        q_low = user_text.lower().strip()
        words = q_low.split()

        if any(k in q_low for k in TOPIC_SWITCH_KEYWORDS):
            return user_text

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
    def resolve_transition_offline(
        cls,
        user_text: str,
        input_type: str,
        extracted_facts: Dict[str, Any],
        ml_intent_resp: Optional[IntentPredictionResponse],
        state: ConversationState,
    ) -> Tuple[str, float, bool]:
        """Deterministic transition arbiter used for offline/fallback and non-LLM turns."""
        if input_type == "chitchat":
            if state.active_intent and state.active_intent not in _CHITCHAT_INTENTS:
                return state.active_intent, 0.90, False
            q_low = user_text.lower().strip()
            if any(k in q_low for k in ("cam on", "cảm ơn", "thanks", "thank")):
                return "chitchat_thanks", 0.95, (state.active_intent != "chitchat_thanks")
            if any(k in q_low for k in ("ok", "oke", "vâng", "vang", "đúng", "dung", "dạ", "thế à", "vậy à", "ừ", "uhm")):
                return "chitchat_confirm", 0.95, (state.active_intent != "chitchat_confirm")
            return "chitchat_greeting", 0.95, (state.active_intent != "chitchat_greeting")

        if input_type == "fact_supplement" or (extracted_facts and len(user_text.split()) <= 4):
            if state.active_intent and state.active_intent not in _CHITCHAT_INTENTS:
                return state.active_intent, 0.90, False
            if "order_id" in extracted_facts:
                return "track_order", 0.85, True

        if input_type == "negation_reversal":
            if (
                ml_intent_resp
                and ml_intent_resp.intent != state.active_intent
                and ml_intent_resp.confidence >= INTENT_CONFIDENCE_THRESHOLD
            ):
                return ml_intent_resp.intent, ml_intent_resp.confidence, True
            if state.active_intent == "cancel_order":
                return "delivery_time", 0.75, True

        if ml_intent_resp:
            new_intent = ml_intent_resp.intent
            new_conf = ml_intent_resp.confidence

            if new_conf >= INTENT_CONFIDENCE_THRESHOLD:
                return new_intent, new_conf, (new_intent != state.active_intent)

            if state.active_intent and new_conf < INTENT_CONFIDENCE_THRESHOLD:
                if any(k in user_text.lower() for k in ("nó", "đơn", "hàng", "sản phẩm", "ship")):
                    return state.active_intent, 0.65, False

            return new_intent, new_conf, (new_intent != state.active_intent)

        return state.active_intent or "track_order", 0.50, False
