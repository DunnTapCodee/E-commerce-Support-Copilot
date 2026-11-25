"""Customer Acknowledgement Engine (Phần 1: Trả lời đệm tức thì cho Khách hàng).

Cung cấp câu đệm tức thì (< 20ms), lịch sự chuẩn xưng hô CSKH ("em - anh/chị"),
định tuyến đồng nhất theo 16 TARGET_INTENTS chuẩn (không lặp lại bộ regex phân loại ý định).
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

GENERAL_BUFFERS: List[str] = [
    "Dạ anh/chị chờ em một xíu, nhân viên đang chuẩn bị thông tin cho mình ngay đây ạ!",
    "Dạ em đã nhận được yêu cầu của anh/chị. Em đang kiểm tra thông tin để hỗ trợ mình ngay nhé ạ!",
    "Dạ Tiki chào anh/chị, em đang đối soát dữ liệu trên hệ thống để giải đáp cho mình ngay đây ạ.",
    "Dạ vâng, anh/chị đợi em trong giây lát, chuyên viên CSKH đang chuẩn bị câu trả lời gửi mình nhé ạ!",
    "Dạ em đã ghi nhận tin nhắn của mình. Em đang tra cứu thông tin hỗ trợ anh/chị ngay đây ạ!",
    "Dạ anh/chị đợi em một chút nhé, em đang phối hợp kiểm tra hệ thống để hỗ trợ mình chu đáo nhất ạ.",
]

GREETING_BUFFERS: List[str] = [
    "Dạ Tiki chào anh/chị! Rất vui được hỗ trợ mình hôm nay. Anh/chị cần em hỗ trợ thông tin gì về đơn hàng hoặc mua sắm không ạ?",
    "Dạ em chào anh/chị ạ! Chúc anh/chị một ngày nhiều niềm vui. Em có thể hỗ trợ gì cho mình hôm nay ạ?",
    "Dạ em chào anh/chị, em sẵn sàng hỗ trợ giải đáp mọi thắc mắc của mình rồi ạ!",
]

THANKS_CONFIRM_BUFFERS: List[str] = [
    "Dạ không có gì ạ! Nếu cần hỗ trợ thêm bất kỳ điều gì, anh/chị cứ nhắn cho em nhé!",
    "Dạ em cảm ơn anh/chị. Anh/chị cần em hỗ trợ thêm thông tin gì nữa không ạ?",
    "Dạ vâng ạ, anh/chị đợi em trong giây lát nhé!",
]

ORDER_BUFFERS: List[str] = [
    "Dạ em đã ghi nhận yêu cầu tra cứu đơn hàng{order_clause}. Em đang kết nối hệ thống bưu tá kiểm tra lộ trình gửi anh/chị ngay nhé ạ!",
    "Dạ anh/chị chờ em một xíu, nhân viên đang kiểm tra dữ liệu đơn hàng{order_clause} cho mình ngay đây ạ.",
    "Dạ em đang đối soát vị trí và tiến độ đơn hàng{order_clause} để cập nhật cho anh/chị ngay ạ!",
]

SHIPPING_COST_BUFFERS: List[str] = [
    "Dạ em đã ghi nhận thắc mắc về cước phí vận chuyển{order_clause}. Em đang tra cứu biểu phí và ưu đãi Freeship gửi anh/chị ngay nhé ạ!",
    "Dạ anh/chị đợi em một lát, em đang kiểm tra chi tiết phí giao hàng cho mình ngay đây ạ.",
]

DISCOUNT_BUFFERS: List[str] = [
    "Dạ Tiki đã ghi nhận thắc mắc về ưu đãi và voucher{order_clause}. Em đang tra cứu các chương trình khuyến mãi hiện có gửi anh/chị ngay nhé ạ!",
    "Dạ anh/chị chờ em một lát, em đang tổng hợp các voucher và mã giảm giá tốt nhất gửi mình ngay nhé ạ!",
    "Dạ Tiki đang có nhiều ưu đãi hấp dẫn, anh/chị đợi em một xíu để em kiểm tra mã áp dụng cho mình nhé ạ!",
]

RETURN_REFUND_BUFFERS: List[str] = [
    "Dạ em đã tiếp nhận yêu cầu đổi trả / hoàn tiền{order_clause}. Em đang tra cứu quy định và hỗ trợ mình ngay đây ạ.",
    "Dạ anh/chị đợi em một chút, nhân viên đang đối soát chính sách để hướng dẫn các bước đổi trả thuận tiện nhất cho mình ạ.",
    "Dạ em đã ghi nhận vấn đề của mình. Em đang kiểm tra hồ sơ để xử lý nhanh nhất cho anh/chị ạ.",
]

PAYMENT_PRICE_BUFFERS: List[str] = [
    "Dạ em đã ghi nhận thắc mắc về giá trị đơn hàng và thanh toán. Em đang kiểm tra bảng kê chi tiết gửi anh/chị ngay đây ạ!",
    "Dạ anh/chị chờ em một xíu, em đang kiểm tra số tiền và thông tin thanh toán đơn hàng gửi mình ngay nhé ạ.",
]

WARRANTY_ACCOUNT_BUFFERS: List[str] = [
    "Dạ em đã tiếp nhận câu hỏi của anh/chị. Em đang tra cứu quy định và hướng dẫn chi tiết gửi mình ngay đây ạ!",
    "Dạ anh/chị chờ em một chút nhé, em đang kiểm tra hướng dẫn chính xác nhất để hỗ trợ mình ngay ạ.",
]

OUT_OF_SCOPE_BUFFERS: List[str] = [
    "Dạ em đã nhận được câu hỏi của anh/chị. Em đang kiểm tra thông tin để phản hồi ngay nhé ạ!",
    "Dạ anh/chị chờ em một xíu, em đang xử lý câu hỏi của mình ngay đây ạ.",
]

_GREETING_RE = re.compile(r"\b(h+i+|h+e+l+l*o+|a+l+o+|c+h+à+o+|c+h+a+o+)\b", re.IGNORECASE)
_THANKS_RE = re.compile(r"\b(cảm\s+ơn|cam\s+on|thanks|thank\s+you)\b", re.IGNORECASE)
_CONFIRM_RE = re.compile(r"\b(ok|oke|oki|okie|vâng|vang|đúng|dung|dạ)\b", re.IGNORECASE)
_ORDER_PRICE_RE = re.compile(
    r"\b(bao\s+nhiêu\s+tiền|tổng\s+tiền|giá\s+đơn\s+hàng|tiền\s+đơn\s+hàng|hết\s+bao\s+nhiêu)\b",
    re.IGNORECASE,
)


class CustomerAcknowledgementEngine:
    """Fast CSKH buffer generator driven by canonical intent + extracted dialogue state."""

    @classmethod
    def infer_quick_intent(
        cls,
        user_query: str,
        active_intent: Optional[str] = None,
        input_type: Optional[str] = None,
        facts: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Infer quick intent from dialogue state or shared offline classifier without duplicate regex tables."""
        q_low = " ".join((user_query or "").lower().split())
        facts = facts or {}

        if input_type == "chitchat":
            if _THANKS_RE.search(q_low):
                return "chitchat_thanks"
            if _CONFIRM_RE.search(q_low) and not _GREETING_RE.search(q_low):
                return "chitchat_confirm"
            return "chitchat_greeting"

        if input_type == "fact_supplement" and active_intent:
            return active_intent

        if "order_id" in facts and not active_intent:
            return "track_order"

        # Reuse shared OfflineIntentFallback when available in the repo; avoid duplicating 16 intent regexes
        try:
            from services.intent_service.src.offline_fallback import OfflineIntentFallback

            return OfflineIntentFallback.classify(user_query).intent
        except ImportError:
            pass

        if active_intent:
            return active_intent
        if "order_id" in facts or "ord-" in q_low:
            return "track_order"
        return "unknown_query"

    @classmethod
    def _pick_variant(cls, candidates: List[str], last_ack: Optional[str] = None) -> str:
        """Select a buffer message while avoiding immediate repetition against last_ack."""
        if not candidates:
            return GENERAL_BUFFERS[0]
        if not last_ack:
            return candidates[0]
        for c in candidates:
            if c[:30] not in last_ack:
                return c
        return candidates[0]

    @classmethod
    def generate(
        cls,
        intent: str,
        facts: Optional[Dict[str, Any]] = None,
        input_type: Optional[str] = None,
        user_query: str = "",
        last_ack: Optional[str] = None,
    ) -> str:
        """Generate a context-aware, polite CSKH acknowledgement strictly using 'em - anh/chị'."""
        facts = facts or {}
        q_lower = " ".join((user_query or "").lower().split())

        order_id = facts.get("order_id")
        order_clause = f" {order_id}" if order_id else ""
        product_name = facts.get("product_name")

        effective_intent = intent or cls.infer_quick_intent(user_query, input_type=input_type, facts=facts)

        if product_name and effective_intent in ("return_product", "return_policy"):
            return f"Dạ em rất tiếc về sự cố với {product_name} của mình. Em đang tra cứu quy định và hỗ trợ anh/chị ngay đây ạ."

        is_thanks = bool(_THANKS_RE.search(q_lower)) or effective_intent == "chitchat_thanks"
        is_greeting_only = (
            effective_intent == "chitchat_greeting"
            or (input_type == "chitchat" and bool(_GREETING_RE.search(q_lower)))
            or (bool(_GREETING_RE.search(q_lower)) and len(q_lower.split()) <= 3)
        )
        is_confirm_only = (
            effective_intent == "chitchat_confirm"
            or (bool(_CONFIRM_RE.search(q_lower)) and len(q_lower.split()) <= 3 and not order_id)
        )

        if is_thanks and len(q_lower.split()) <= 6:
            chosen = cls._pick_variant(THANKS_CONFIRM_BUFFERS, last_ack)
        elif is_greeting_only:
            chosen = cls._pick_variant(GREETING_BUFFERS, last_ack)
        elif is_confirm_only:
            chosen = cls._pick_variant(THANKS_CONFIRM_BUFFERS, last_ack)
        elif effective_intent == "get_discounts":
            chosen = cls._pick_variant(DISCOUNT_BUFFERS, last_ack)
        elif effective_intent == "shipping_costs":
            chosen = cls._pick_variant(SHIPPING_COST_BUFFERS, last_ack)
        elif effective_intent in ("return_policy", "return_product", "request_refund", "refund_policy", "refund_status", "cancel_order"):
            chosen = cls._pick_variant(RETURN_REFUND_BUFFERS, last_ack)
        elif effective_intent == "payment_issue" or (effective_intent == "track_order" and _ORDER_PRICE_RE.search(q_lower)):
            chosen = cls._pick_variant(PAYMENT_PRICE_BUFFERS, last_ack)
        elif effective_intent in ("track_order", "delivery_time", "delivery_issue"):
            if not order_id and any(k in q_lower for k in ("khi nào", "bao giờ", "giao chưa", "đến đâu", "tới nơi", "ở đâu")):
                return (
                    "Dạ em chào anh/chị! Anh/chị vui lòng cho em xin mã đơn hàng hoặc thông tin đơn hàng "
                    "để em kiểm tra ngay cho mình nhé ạ."
                )
            chosen = cls._pick_variant(ORDER_BUFFERS, last_ack)
        elif effective_intent in ("warranty", "create_account", "recover_password"):
            chosen = cls._pick_variant(WARRANTY_ACCOUNT_BUFFERS, last_ack)
        elif effective_intent == "out_of_scope":
            chosen = cls._pick_variant(OUT_OF_SCOPE_BUFFERS, last_ack)
        else:
            chosen = cls._pick_variant(GENERAL_BUFFERS, last_ack)

        try:
            return chosen.format(order_clause=order_clause)
        except Exception:
            return chosen
