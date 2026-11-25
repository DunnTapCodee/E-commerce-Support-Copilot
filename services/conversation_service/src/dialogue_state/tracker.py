"""Dialogue Intent Transition Arbiter (LLM Primary + OfflineTrackerFallback).

Keeps LLM transition arbitration clean and delegates all deterministic keyword/regex
fallback logic to `offline_tracker_fallback.py` (`OfflineTrackerFallback`).
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, Optional, Tuple

from contracts.llm_failover import call_chat_completion_with_failover
from contracts.schemas import IntentPredictionResponse
from services.conversation_service.src.config import INTENT_CONFIDENCE_THRESHOLD, OPENAI_MODEL
from services.conversation_service.src.dialogue_state.offline_tracker_fallback import OfflineTrackerFallback
from services.conversation_service.src.dialogue_state.state import ConversationState

logger = logging.getLogger("dialogue_tracker")


class IntentTracker:
    """Decides whether to preserve existing intent, adapt via context, or switch topics."""

    @staticmethod
    def build_context_augmented_query(user_text: str, state: ConversationState) -> str:
        """Thin wrapper delegating context tagging to OfflineTrackerFallback."""
        return OfflineTrackerFallback.build_context_augmented_query(user_text, state)

    @classmethod
    def _fallback_regex_transition(
        cls,
        user_text: str,
        input_type: str,
        extracted_facts: Dict[str, Any],
        ml_intent_resp: Optional[IntentPredictionResponse],
        state: ConversationState,
    ) -> Tuple[str, float, bool]:
        """Thin wrapper delegating deterministic offline transition logic to OfflineTrackerFallback."""
        return OfflineTrackerFallback.resolve_transition_offline(
            user_text, input_type, extracted_facts, ml_intent_resp, state
        )

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
        """Arbiter deciding the effective intent and confidence."""
        if input_type in ("chitchat", "fact_supplement", "negation_reversal") or not state.active_intent:
            return cls._fallback_regex_transition(user_text, input_type, extracted_facts, ml_intent_resp, state)

        if ml_intent_resp and ml_intent_resp.confidence >= INTENT_CONFIDENCE_THRESHOLD:
            if ml_intent_resp.intent == state.active_intent:
                return state.active_intent, ml_intent_resp.confidence, False

            model_name = (getattr(ml_intent_resp, "model_name", None) or "").lower()
            is_local_ml_or_rule = (
                model_name in {"legacy_baseline", "module1_model", "semantic_rule_fallback", "unavailable_fallback"}
                or any(k in model_name for k in ("sklearn", "numpy", "onnx", "minilm", "tfidf"))
            )
            if not is_local_ml_or_rule or ml_intent_resp.confidence >= 0.85:
                return ml_intent_resp.intent, ml_intent_resp.confidence, True

        if use_llm and state.active_intent and len(user_text.split()) <= 7:
            try:
                system_prompt = (
                    "Bạn là chuyên gia phân loại chuyển tiếp ý định hội thoại (Dialogue State Tracker) cho CSKH Tiki.\n"
                    "Nhiệm vụ: Phân tích xem câu hỏi mới của khách hàng đang TIẾP TỤC CHỦ ĐỀ CŨ (CONTINUE) hay CHUYỂN SANG Ý ĐỊNH MỚI (SWITCH).\n"
                    "Chỉ trả về JSON duy nhất (không kèm markdown thừa):\n"
                    '{"action": "CONTINUE"|"SWITCH", "intent": "<intent_hợp_lý_nhất>", "confidence": 0.85, "reason": "<giải thích ngắn>"}'
                )

                user_prompt = (
                    f"Ý định phiên trước: {state.active_intent}\n"
                    f"Mã đơn liên kết: {state.active_order_id or 'Chưa có'}\n"
                    f'Câu nói mới của khách: "{user_text}"\n'
                    f"Phân loại sơ bộ: {ml_intent_resp.intent if ml_intent_resp else 'None'} "
                    f"(độ tin cậy: {ml_intent_resp.confidence if ml_intent_resp else 0.0})\n"
                    f"Loại đầu vào: {input_type}"
                )

                payload = {
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.1,
                    "max_tokens": 150,
                }

                resp_data = await call_chat_completion_with_failover(payload, timeout=4.0)
                if resp_data and "choices" in resp_data and resp_data["choices"]:
                    raw_text = (resp_data["choices"][0].get("message", {}).get("content") or "").strip()
                    if raw_text.startswith("```"):
                        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
                        raw_text = re.sub(r"\s*```$", "", raw_text)
                    parsed = json.loads(raw_text)
                    action = parsed.get("action", "CONTINUE").upper()
                    intent_cand = parsed.get("intent", state.active_intent)
                    try:
                        conf = max(0.0, min(1.0, float(parsed.get("confidence", 0.50))))
                    except (TypeError, ValueError):
                        conf = 0.0

                    if action == "CONTINUE":
                        return state.active_intent, max(conf, 0.85), False
                    return intent_cand, conf, (intent_cand != state.active_intent)
            except Exception as exc:
                logger.warning("[DialogueTracker] LLM transition check failed (%s). Falling back to offline rules.", exc)

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
