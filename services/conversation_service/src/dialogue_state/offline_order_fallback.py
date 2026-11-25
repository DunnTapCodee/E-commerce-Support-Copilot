"""Offline / Fallback Order Status Filter & Portfolio Inquiry Heuristics.

Isolated from `order_context_resolver.py` so keyword-based status filter parsing
and portfolio inquiry heuristics run only as fallback or when intent is not yet supplied.
"""
from __future__ import annotations

import re
from typing import Optional, Tuple

ORDER_STATUS_FILTER_SPECS: Tuple[Tuple[Tuple[str, ...], set[str], str], ...] = (
    (("giao trễ", "bị trễ", "chậm giao", "quá hạn", "delay", "trễ hẹn"), {"DELIVERY_DELAYED"}, "đang bị giao trễ"),
    (("đang xử lý", "chờ xử lý", "chưa đóng gói", "processing"), {"PROCESSING"}, "đang xử lý"),
    (("đang giao", "đang vận chuyển", "trên đường giao", "shipping", "in_transit"), {"SHIPPING", "IN_TRANSIT"}, "đang vận chuyển"),
    (("đã giao", "hoàn thành", "delivered"), {"DELIVERED"}, "đã giao thành công"),
    (("đã hủy", "bị hủy", "cancelled"), {"CANCELLED"}, "đã hủy"),
    (("trả hàng", "hoàn hàng", "returned"), {"RETURNED", "RETURN_REQUESTED", "RETURN_APPROVED"}, "đổi/trả hàng"),
    (("lỗi thanh toán", "thanh toán thất bại", "payment_failed"), {"PAYMENT_FAILED"}, "lỗi thanh toán"),
)


class OfflineOrderFallback:
    """Deterministic fallback rules for unscoped multi-order query disambiguation."""

    @staticmethod
    def detect_order_status_filter(customer_query: str) -> Optional[Tuple[set[str], str]]:
        """Detect whether the customer is filtering their orders by canonical order_status."""
        q = (customer_query or "").lower()
        for cues, statuses, label in ORDER_STATUS_FILTER_SPECS:
            if any(k in q for k in cues):
                return set(statuses), label
        return None

    @staticmethod
    def is_multi_order_list_query(customer_query: str) -> bool:
        """Detect generic/list order inquiries that should disambiguate when customer has >1 order."""
        q = " ".join((customer_query or "").lower().split())
        return any(
            k in q
            for k in (
                "đơn nào",
                "những đơn",
                "các đơn",
                "danh sách đơn",
                "tất cả đơn",
                "kiểm tra đơn",
                "tra cứu đơn",
                "xem đơn",
                "đơn hàng của tôi",
                "đơn của tôi",
                "đơn hàng của mình",
                "đơn của mình",
                "lịch sử đơn",
                "lịch sử mua",
                "mấy đơn",
                "bao nhiêu đơn",
            )
        )

    @classmethod
    def is_personal_order_portfolio_inquiry(cls, customer_query: str) -> bool:
        """Return True only when an unscoped utterance asks about the customer's own orders or spending."""
        q = " ".join((customer_query or "").lower().split())
        if not q:
            return False

        if cls.is_multi_order_list_query(q):
            return True

        if re.search(
            r"\b(tổng\s+(tiền|thanh toán|chi tiêu|đơn)|đã\s+(thanh toán|chi|mua)\s+.*bao nhiêu|bao nhiêu tiền\s+rồi|hết bao nhiêu tiền)\b",
            q,
        ):
            return True

        has_ownership = any(p in q for p in ("của tôi", "của mình", "mình đặt", "tôi đặt", "em đặt", "vừa đặt"))
        if any(term in q for term in ("chính sách", "quy định", "điều khoản")) and not has_ownership:
            return False

        has_order_noun = bool(re.search(r"\b(đơn hàng|đơn mua|kiện hàng|bưu kiện|gói hàng)\b", q))
        has_status_cue = bool(
            re.search(r"\b(ở đâu|đến đâu|tới đâu|sao rồi|bao giờ|khi nào|tình trạng|tiến độ|xuất kho)\b", q)
        )
        return has_order_noun and (has_ownership or has_status_cue)
