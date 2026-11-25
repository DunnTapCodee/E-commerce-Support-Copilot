"""LLM-Primary Contextual Query Rewriter & Multi-turn Coreference Resolver.

Online mode delegates contextual disambiguation and policy-vs-order separation directly
to the LLM without regex pre-interception. All offline scope/heuristic rules live in
`offline_rewrite_fallback.py` (`OfflineRewriteFallback`).
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from contracts.llm_failover import (
    call_chat_completion_with_failover,
    get_available_api_keys,
    is_external_llm_disabled,
)
from services.conversation_service.src.config import OPENAI_MODEL
from services.conversation_service.src.dialogue_state.offline_rewrite_fallback import (
    ORDER_SPECIFIC_INTENTS,
    OUT_OF_SERVICE_INTENTS,
    POLICY_GENERAL_INTENTS,
    SCOPE_ORDER_POLICY_HYBRID,
    SCOPE_ORDER_SPECIFIC,
    SCOPE_OUT_OF_SERVICE,
    SCOPE_POLICY_GENERAL,
    OfflineRewriteFallback,
)
from services.conversation_service.src.dialogue_state.state import ConversationState


class QueryRewriter:
    """LLM-Primary 4-Scope Query Rewriter delegating offline fallback to OfflineRewriteFallback."""

    SCOPE_OUT_OF_SERVICE = SCOPE_OUT_OF_SERVICE
    SCOPE_ORDER_SPECIFIC = SCOPE_ORDER_SPECIFIC
    SCOPE_POLICY_GENERAL = SCOPE_POLICY_GENERAL
    SCOPE_ORDER_POLICY_HYBRID = SCOPE_ORDER_POLICY_HYBRID

    @classmethod
    def is_conversational_closing_or_ack(cls, text: str) -> bool:
        """Thin wrapper delegating to OfflineRewriteFallback."""
        return OfflineRewriteFallback.is_conversational_closing_or_ack(text)

    @classmethod
    def detect_query_scope(cls, query: str, intent: Optional[str] = None) -> str:
        """Thin wrapper delegating scope detection to OfflineRewriteFallback."""
        return OfflineRewriteFallback.detect_query_scope(query, intent=intent)

    @classmethod
    async def rewrite_query(
        cls,
        user_query: str,
        state: ConversationState,
        order_data: Optional[Dict[str, Any]] = None,
        openai_key: Optional[str] = None,
        intent: Optional[str] = None,
    ) -> Tuple[str, str]:
        """LLM-primary contextual rewrite; offline fallback runs ONLY when LLM is unavailable or fails."""
        clean_query = user_query.strip()
        if not clean_query:
            return clean_query, "empty_query"

        if intent and intent in OUT_OF_SERVICE_INTENTS:
            return clean_query, "scope_out_of_service_passthrough"

        has_api_key = bool(openai_key or os.getenv("OPENAI_API_KEY", "") or get_available_api_keys())
        if not is_external_llm_disabled() and has_api_key:
            history_lines = []
            for t in (state.turns[-3:] if state.turns else []):
                if t.customer_query:
                    history_lines.append(f"Khách: {t.customer_query}")
                if t.agent_response and not getattr(t, "is_acknowledgement", False):
                    history_lines.append(f"CSKH: {t.agent_response[:100]}...")
            history_str = "\n".join(history_lines) if history_lines else "Lượt trao đổi đầu tiên."

            order_id = state.active_order_id or (order_data.get("order_id") if order_data else None)
            order_ctx = "Không có đơn hàng đang ghim."
            if order_data:
                items = ", ".join(f"{it.get('name')} (x{it.get('quantity', 1)})" for it in order_data.get("items", [])) or "Sản phẩm"
                status = order_data.get("order_status") or order_data.get("status", "N/A")
                order_ctx = f"Mã đơn: {order_id or 'N/A'} | Sản phẩm: {items} | Trạng thái: {status}"
            elif order_id:
                order_ctx = f"Mã đơn: {order_id}"

            prompt = (
                "Bạn là bộ tiền xử lý truy vấn tìm kiếm cho CSKH Tiki.\n"
                "Nhiệm vụ: Viết lại câu nói của khách thành MỘT CÂU truy vấn rõ nghĩa, độc lập để tìm kiếm tài liệu/đơn hàng.\n"
                "QUY TẮC BẮT BUỘC:\n"
                "- Nếu câu hỏi là xã giao, ngoài phạm vi TMĐT, hoặc hỏi về chính sách/tài khoản/mật khẩu chung (không hỏi về đơn cụ thể): giữ nguyên ý định chung, TUYỆT ĐỐI KHÔNG chèn mã đơn ORD-... vào.\n"
                "- Chỉ chèn mã đơn hàng từ HỒ SƠ ĐƠN khi khách thực sự đang hỏi hoặc nối tiếp ngữ cảnh về đơn hàng đó.\n"
                f"HỒ SƠ ĐƠN HIỆN TẠI: {order_ctx}\n"
                f"LỊCH SỬ GẦN ĐÂY:\n{history_str}\n"
                f'CÂU NÓI CỦA KHÁCH: "{clean_query}"\n'
                "Trả về DUY NHẤT 1 câu truy vấn tiếng Việt, không giải thích."
            )
            res = await cls._call_llm_rewriter(prompt)
            if res:
                return res

        scope = cls.detect_query_scope(clean_query, intent=intent)
        return cls._heuristic_rewrite(clean_query, scope, state, order_data)

    @classmethod
    async def _call_llm_rewriter(cls, prompt: str) -> Optional[Tuple[str, str]]:
        """Execute bounded LLM chat completion call with automatic multi-key failover."""
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 200,
        }

        try:
            res_data = await call_chat_completion_with_failover(payload, timeout=10.0)
            if res_data and "choices" in res_data and res_data["choices"]:
                candidate = (res_data["choices"][0].get("message", {}).get("content") or "").strip()
                candidate = candidate.strip('"\n\r ')
                if candidate and len(candidate) > 4 and not candidate.startswith("```"):
                    return candidate, "llm_query_rewriter"
        except Exception as exc:
            print(f"[QueryRewriter] LLM call failed: {exc}")

        return None

    @classmethod
    def _heuristic_rewrite(
        cls,
        query: str,
        scope: str,
        state: ConversationState,
        order_data: Optional[Dict[str, Any]],
    ) -> Tuple[str, str]:
        """Thin wrapper delegating offline heuristic rewrite to OfflineRewriteFallback."""
        return OfflineRewriteFallback.rewrite_offline(query, scope, state, order_data)


__all__ = [
    "QueryRewriter",
    "POLICY_GENERAL_INTENTS",
    "ORDER_SPECIFIC_INTENTS",
    "OUT_OF_SERVICE_INTENTS",
]
