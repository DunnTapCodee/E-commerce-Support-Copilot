"""Customer Acknowledgement Engine (Phần 1: Trả lời dạo tức thì cho User).
Cung cấp câu đệm tức thì (< 20ms), lịch sự, tự nhiên, đa dạng (20+ mẫu câu)
và tự động chống lặp lại giữa các lượt hội thoại.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional


# Kho mẫu câu phản hồi đệm phong phú (~20 samples) phân theo ngữ cảnh
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

PRICE_BUFFERS: List[str] = [
    "Dạ em đã ghi nhận thắc mắc về giá trị đơn hàng và thanh toán. Em đang kiểm tra bảng kê chi tiết gửi anh/chị ngay đây ạ!",
    "Dạ anh/chị chờ em một xíu, em đang kiểm tra số tiền và thanh toán đơn hàng gửi mình ngay nhé ạ.",
]

OUT_OF_SCOPE_BUFFERS: List[str] = [
    "Dạ em đã nhận được câu hỏi của anh/chị. Em đang kiểm tra thông tin để phản hồi ngay nhé ạ!",
    "Dạ anh/chị chờ em một xíu, em đang xử lý câu hỏi của mình ngay đây ạ.",
]


class CustomerAcknowledgementEngine:
    """Tự động chọn câu đệm tự nhiên, lịch sự, đa dạng (~20 mẫu) và chống lặp ngữ cảnh."""

    @classmethod
    def _pick_variant(cls, candidates: List[str], last_ack: Optional[str] = None) -> str:
        """Chọn câu đệm trong danh sách, ưu tiên câu khác với last_ack để chống lặp."""
        if not candidates:
            return GENERAL_BUFFERS[0]
        if not last_ack:
            return candidates[0]
        # Tìm câu khác với last_ack
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
        """Sinh câu trả lời dạo trước nhạy ngữ cảnh, chống lặp và tự nhiên."""
        facts = facts or {}
        q_lower = user_query.lower().strip()

        # Format slot clauses
        order_id = facts.get("order_id")
        order_clause = f" {order_id}" if order_id else ""
        product_name = facts.get("product_name")

        if product_name and intent in ("return_product", "complaint", "return_policy"):
            return f"Dạ em rất tiếc về sự cố với {product_name} của mình. Em đang tra cứu quy định và hỗ trợ mình ngay đây ạ."

        # 1. Chitchat greeting (Hỗ trợ cả kéo dài chữ như hiiiii, hellooo mà không bắt nhầm 'hiện tại', 'hiển thị')
        is_greeting = bool(re.search(r"\b(h+i+|h+e+l+l*o+|a+l+o+|c+h+à+o+|c+h+a+o+)\b", q_lower))
        is_thanks = bool(re.search(r"\b(cảm ơn|cam on|thanks|thank you)\b", q_lower))
        is_confirm = bool(re.search(r"\b(ok|oke|oki|vâng|vang|đúng|dung|dạ)\b", q_lower))

        # Check explicit keywords
        has_promo = bool(re.search(r"\b(ưu đãi|khuyến mãi|khuyến mại|voucher|mã giảm|coupon|freeship|giảm giá|tiki xu)\b", q_lower))
        has_return_refund = bool(re.search(r"\b(trả hàng|đổi hàng|đổi trả|hoàn tiền|refund|hủy đơn|huỷ đơn)\b", q_lower))
        has_order_tracking = bool(re.search(r"\b(vận đơn|bưu tá|đã giao chưa|giao chưa|khi nào tới|bao giờ tới|đơn hàng của mình|đơn của mình|ord-)\b", q_lower))
        has_order_price = bool(re.search(r"\b(đơn.*bao nhiêu tiền|tổng tiền.*đơn|giá đơn hàng|tiền đơn hàng|đơn hàng.*hết bao nhiêu)\b", q_lower))
        has_out_of_scope = bool(re.search(r"\b(thời tiết|giá xăng|xăng|ronaldo|messi|bóng đá|toán học|phương trình)\b", q_lower))

        # Decision routing
        if is_thanks or intent == "chitchat_thanks":
            chosen = cls._pick_variant(THANKS_CONFIRM_BUFFERS, last_ack)
        elif is_greeting and not has_promo and not has_return_refund and not has_order_tracking and len(q_lower.split()) <= 4:
            chosen = cls._pick_variant(GREETING_BUFFERS, last_ack)
        elif is_confirm and len(q_lower.split()) <= 3:
            chosen = cls._pick_variant(THANKS_CONFIRM_BUFFERS, last_ack)
        elif has_promo or intent in ("get_discounts", "promotion_policy"):
            chosen = cls._pick_variant(DISCOUNT_BUFFERS, last_ack)
        elif has_return_refund or intent in ("return_policy", "return_product", "request_refund", "refund_policy", "cancel_order"):
            chosen = cls._pick_variant(RETURN_REFUND_BUFFERS, last_ack)
        elif has_order_price or (intent == "track_order" and "bao nhiêu tiền" in q_lower):
            chosen = cls._pick_variant(PRICE_BUFFERS, last_ack)
        elif has_order_tracking or (intent in ("track_order", "delivery_time")):
            if not order_id and any(k in q_lower for k in ["khi nào", "bao giờ", "giao chưa", "đến đâu", "tới nơi"]):
                return "Dạ em chào anh/chị! Bạn vui lòng cho shop xin mã đơn hàng hoặc thông tin đơn hàng nhé để em kiểm tra ngay cho mình ạ."
            chosen = cls._pick_variant(ORDER_BUFFERS, last_ack)
        elif has_out_of_scope or intent == "out_of_scope":
            chosen = cls._pick_variant(OUT_OF_SCOPE_BUFFERS, last_ack)
        else:
            # General safe natural buffer: Rất thân thiện, không phỏng đoán bừa bãi
            chosen = cls._pick_variant(GENERAL_BUFFERS, last_ack)

        try:
            return chosen.format(order_clause=order_clause)
        except Exception:
            return chosen
