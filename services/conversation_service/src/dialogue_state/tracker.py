"""Context-augmented query builder and intent transition arbiter."""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
from contracts.schemas import IntentPredictionResponse
from services.conversation_service.src.dialogue_state.state import ConversationState


class IntentTracker:
    """Decides whether to preserve existing intent, adapt via context, or switch topics."""

    @staticmethod
    def build_context_augmented_query(user_text: str, state: ConversationState) -> str:
        """Create a targeted prompt for Intent Service that incorporates previous context without wordy noise."""
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

    @staticmethod
    def resolve_intent_transition(
        user_text: str,
        input_type: str,
        extracted_facts: Dict[str, Any],
        ml_intent_resp: Optional[IntentPredictionResponse],
        state: ConversationState,
    ) -> Tuple[str, float, bool]:
        """Arbiter deciding the effective intent and confidence.
        Returns:
            (effective_intent, effective_confidence, intent_switched_bool)
        """
        # 1. Chitchat / courtesy bypass
        if input_type == "chitchat":
            return state.active_intent or "greeting", 0.95, False

        # 2. Fact supplement (e.g. user just provides ORD-1003 or product detail)
        if input_type == "fact_supplement" or (extracted_facts and len(user_text.split()) <= 4):
            if state.active_intent:
                # Retain previous intent with high confidence because slot is filled
                return state.active_intent, 0.90, False
            elif "order_id" in extracted_facts:
                return "track_order", 0.85, True

        # 3. Negation reversal (e.g. "thôi không hủy nữa, xem bao giờ giao")
        if input_type == "negation_reversal":
            # If ML prediction was made, prefer the candidate that is NOT the old intent
            if ml_intent_resp and ml_intent_resp.intent != state.active_intent and ml_intent_resp.confidence >= 0.50:
                return ml_intent_resp.intent, ml_intent_resp.confidence, True
            # Fallback heuristic: if old was cancel, switch to delivery_time or track_order
            if state.active_intent == "cancel_order":
                return "delivery_time", 0.75, True

        # 4. New Question evaluated by Intent Service
        if ml_intent_resp:
            new_intent = ml_intent_resp.intent
            new_conf = ml_intent_resp.confidence

            # Clear switch if confident
            if new_conf >= 0.60:
                switched = (new_intent != state.active_intent)
                return new_intent, new_conf, switched

            # If low confidence but user already has active order and question seems related
            if state.active_intent and new_conf < 0.60:
                # If question is ambiguous and no new topic strongly indicated, preserve with moderate conf
                if any(k in user_text.lower() for k in ["nó", "đơn", "hàng", "sản phẩm", "ship"]):
                    return state.active_intent, 0.65, False

            return new_intent, new_conf, (new_intent != state.active_intent)

        return state.active_intent or "track_order", 0.50, False
