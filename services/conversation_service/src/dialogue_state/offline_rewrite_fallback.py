"""Offline / LLM-Unavailable Deterministic Scope Detection & Heuristic Query Rewriter.

Isolated from `query_rewriter.py` so rule-based scope regexes and heuristic expansions
only run when live LLM inference is disabled, unconfigured, or unreachable.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional, Tuple

from services.conversation_service.src.dialogue_state.state import ConversationState

SCOPE_OUT_OF_SERVICE = "out_of_service"
SCOPE_ORDER_SPECIFIC = "order_specific"
SCOPE_POLICY_GENERAL = "policy_general"
SCOPE_ORDER_POLICY_HYBRID = "order_policy_hybrid"

POLICY_GENERAL_INTENTS = frozenset({
    "return_policy",
    "refund_policy",
    "shipping_costs",
    "warranty",
    "get_discounts",
    "create_account",
    "recover_password",
})

ORDER_SPECIFIC_INTENTS = frozenset({
    "track_order",
    "cancel_order",
    "delivery_time",
    "delivery_issue",
    "return_product",
    "request_refund",
    "refund_status",
    "payment_issue",
})

OUT_OF_SERVICE_INTENTS = frozenset({
    "out_of_scope",
    "unknown_query",
    "human_agent",
    "chitchat_greeting",
    "chitchat_thanks",
    "chitchat_confirm",
    "chitchat",
    "greeting",
})

_EXPLICIT_ORDER_ID_RE = re.compile(r"(?:\bORD-[\w-]+\b|#\d{4,})", re.IGNORECASE)

_OFFLINE_SHORT_PHRASES = frozenset({
    "ok", "oke", "okie", "oki", "dạ", "vang", "vâng", "dạ vâng",
    "cảm ơn", "cam on", "thanks", "thank you", "bye", "tạm biệt",
    "được rồi", "hiểu rồi", "da vang", "ok shop", "oke shop",
    "chào", "chào bạn", "chào shop", "chào b", "chào em", "hi", "hello", "alo", "alo shop",
    "ad ơi", "shop ơi", "cho mình hỏi", "tư vấn giúp", "tư vấn mình",
    "thế à", "thế hả", "vậy à", "vậy hả", "vậy sao", "thế sao", "ừ", "đúng rồi", "chuẩn rồi",
})

_OFFLINE_ANAPHORIC_ORDER_RE = re.compile(
    r"\b(?:đơn\s+này|đơn\s+đó|đơn\s+kia|đơn\s+trước|đơn\s+khác|đơn\s+thứ\s+2|đơn\s+còn\s+lại|"
    r"đơn\s+của\s+mình|đơn\s+của\s+tôi|đơn\s+vừa\s+đặt|đơn\s+vừa\s+mua|"
    r"món\s+này|sản\s+phẩm\s+này|kiện\s+này|cái\s+này|nó)\b",
    re.IGNORECASE,
)

_OFFLINE_POLICY_STRUCT_RE = re.compile(
    r"\b(?:chính\s+sách|quy\s+định|quy\s+chế|điều\s+khoản|thể\s+lệ|biểu\s+phí|"
    r"đổi\s+trả|hoàn\s+tiền|bảo\s+hành|tài\s+khoản|mật\s+khẩu|ưu\s+đãi|khuyến\s+mãi|voucher|phí\s+ship)\b",
    re.IGNORECASE,
)

_OFFLINE_ORDER_STRUCT_RE = re.compile(
    r"\b(?:đơn\s+hàng|kiện\s+hàng|vận\s+đơn|hủy\s+đơn|giao\s+hàng|nhận\s+hàng|shipper)\b",
    re.IGNORECASE,
)


class OfflineRewriteFallback:
    """Deterministic fallback scope classifier and query expander when LLM is unavailable."""

    @classmethod
    def is_conversational_closing_or_ack(cls, text: str) -> bool:
        """Identify short chitchat, greetings, or acknowledgements."""
        cleaned = " ".join(re.sub(r"[^\w\s]", " ", text.strip().lower()).split())
        return cleaned in _OFFLINE_SHORT_PHRASES

    @classmethod
    def detect_query_scope(cls, query: str, intent: Optional[str] = None) -> str:
        """Determine query scope using canonical intent taxonomy or deterministic offline cues."""
        q_clean = " ".join(query.strip().lower().split())
        if not q_clean or cls.is_conversational_closing_or_ack(q_clean):
            return SCOPE_OUT_OF_SERVICE

        has_specific_order_ref = bool(_EXPLICIT_ORDER_ID_RE.search(query)) or bool(
            _OFFLINE_ANAPHORIC_ORDER_RE.search(q_clean)
        )

        if intent:
            if intent in OUT_OF_SERVICE_INTENTS:
                return SCOPE_OUT_OF_SERVICE
            if intent in POLICY_GENERAL_INTENTS:
                return SCOPE_ORDER_POLICY_HYBRID if has_specific_order_ref else SCOPE_POLICY_GENERAL
            if intent in ORDER_SPECIFIC_INTENTS:
                return SCOPE_ORDER_SPECIFIC

        has_policy_struct = bool(_OFFLINE_POLICY_STRUCT_RE.search(q_clean))
        if has_policy_struct and has_specific_order_ref:
            return SCOPE_ORDER_POLICY_HYBRID
        if has_policy_struct:
            return SCOPE_POLICY_GENERAL
        if has_specific_order_ref or _OFFLINE_ORDER_STRUCT_RE.search(q_clean):
            return SCOPE_ORDER_SPECIFIC
        return SCOPE_OUT_OF_SERVICE

    @classmethod
    def rewrite_offline(
        cls,
        query: str,
        scope: str,
        state: ConversationState,
        order_data: Optional[Dict[str, Any]],
    ) -> Tuple[str, str]:
        """Deterministic fallback query expansion when LLM is unavailable."""
        if scope in (SCOPE_OUT_OF_SERVICE, SCOPE_POLICY_GENERAL):
            return query, "heuristic_passthrough"

        order_id = state.active_order_id or (order_data.get("order_id") if order_data else None)
        if any(w in query.lower() for w in ("đơn kia", "đơn trước", "đơn khác", "đơn thứ 2", "đơn còn lại")):
            alt_order = state.get_alternative_order_id()
            if alt_order:
                order_id = alt_order

        item_names = ""
        if order_data and order_id == order_data.get("order_id") and isinstance(order_data.get("items"), list):
            item_names = ", ".join(it.get("name", "") for it in order_data["items"][:2] if it.get("name"))

        q_lower = query.lower()
        if order_id and order_id.lower() not in q_lower:
            extra = f" cho đơn hàng {order_id}"
            if item_names:
                extra += f" ({item_names})"
            return f"{query}{extra}", "heuristic_order_expansion"

        return query, "heuristic_direct"
