"""Offline Heuristic Helpers for OrderMatcher.

Isolated from `order_matcher.py` so deterministic keyword-based action detection,
reason splitting, and store-inquiry filtering stay separated from structured ID parsing,
TF-IDF product matching, and LLM extraction.
"""
from __future__ import annotations

from typing import Tuple

_CANCEL_KEYWORDS = (
    "hủy đơn", "hủy hàng", "cancel", "bỏ đơn", "không mua nữa",
    "trả lại tiền", "hủy giúp", "hủy ord", "muốn hủy", "hủy order", "stop order",
)
_DETAILS_KEYWORDS = (
    "chi tiết", "những món gì", "tổng tiền", "hóa đơn", "xem đơn",
    "mua gì", "món gì", "detail", "details", "item", "items",
)
_STATUS_KEYWORDS = (
    "trạng thái", "tới đâu", "ở đâu", "giao chưa", "khi nào nhận",
    "vận chuyển", "tracking", "bưu tá", "bao giờ tới", "bao giờ nhận",
    "lịch trình", "đi tới", "người giao", "thời gian giao", "kiểm tra",
    "tra cứu", "check", "track", "status", "where is", "delivery",
)
_CUSTOMER_LIST_KEYWORDS = (
    "các đơn", "danh sách đơn", "tất cả đơn", "lịch sử đơn",
    "đã mua những gì", "list order", "all orders", "my orders",
)
_NON_ORDER_STORE_INQUIRIES = (
    "có bán", "mua ở đâu", "tư vấn giúp", "tổng đài", "thời gian làm việc", "mã giảm giá",
)


class OfflineOrderMatcherFallback:
    """Deterministic keyword fallback separated from core OrderMatcher logic."""

    @staticmethod
    def infer_offline_action_and_reason(query: str) -> Tuple[str, str]:
        """Infer coarse order action label and cancellation reason without live LLM."""
        q_lower = (query or "").lower()
        action_type = "lookup"
        if any(k in q_lower for k in _CANCEL_KEYWORDS):
            action_type = "cancel"
        elif any(k in q_lower for k in _DETAILS_KEYWORDS):
            action_type = "details"
        elif any(k in q_lower for k in _STATUS_KEYWORDS):
            action_type = "status"
        elif any(k in q_lower for k in _CUSTOMER_LIST_KEYWORDS):
            action_type = "customer_orders"

        cancel_reason = "Khách hàng yêu cầu hủy đơn qua chat"
        if action_type == "cancel":
            for marker in (" vì ", " do "):
                if marker in q_lower:
                    idx = q_lower.find(marker)
                    extracted = query[idx + len(marker):].strip(" .,?!")
                    if extracted:
                        cancel_reason = extracted
                        break
        return action_type, cancel_reason

    @staticmethod
    def is_non_order_store_inquiry(query: str) -> bool:
        """Detect generic pre-purchase / store-info questions when customer_id is not scoped."""
        q_lower = (query or "").lower()
        return any(gi in q_lower for gi in _NON_ORDER_STORE_INQUIRIES) and not any(
            k in q_lower for k in ("đơn", "order", "ord", "giao", "hủy")
        )
