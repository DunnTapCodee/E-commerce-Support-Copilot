"""Customer Acknowledgement Engine (Phần 1: Trả lời dạo tức thì cho User).
Deterministic, slot-filled templates providing instant (<20ms), safe acknowledgement.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# Centralized, customizable acknowledgement templates per intent & sub-topic
ACK_TEMPLATES = {
    # 1. Tra cứu đơn hàng
    "track_order": (
        "Dạ Tiki chào anh/chị! Em đã ghi nhận yêu cầu tra cứu đơn hàng{order_clause}. "
        "Em đang kết nối hệ thống bưu tá để kiểm tra lộ trình gửi anh/chị ngay nhé ạ!"
    ),
    "track_order_alt": (
        "Dạ em đang đối soát vị trí bưu kiện đơn hàng{order_clause} từ bưu cục "
        "để cập nhật tình trạng giao nhận cho anh/chị ngay đây ạ!"
    ),
    # 2. Thời gian giao hàng / Giao trễ
    "delivery_time": (
        "Dạ em rất xin lỗi vì đơn hàng{order_clause} khiến anh/chị phải chờ đợi. "
        "Em đang kiểm tra tiến độ giao hàng từ bưu cục gửi anh/chị ngay đây ạ!"
    ),
    # 3. Sự cố giao hàng
    "delivery_issue": (
        "Dạ em rất tiếc về sự cố giao nhận đơn hàng{order_clause} của mình. "
        "Em đang liên hệ đội ngũ bưu tá để xử lý gấp cho anh/chị ngay ạ!"
    ),
    # 4. Đổi trả sản phẩm cụ thể (bị lỗi, vỡ, móp méo)
    "return_product": (
        "Dạ em rất tiếc về sự cố sản phẩm{product_clause} của anh/chị. "
        "Em đang kiểm tra chính sách đổi trả và bảo hành phù hợp gửi anh/chị ngay ạ!"
    ),
    "return_followup": (
        "Dạ em đã nắm được thắc mắc tiếp theo của anh/chị về quy trình đổi trả. "
        "Em đang tra cứu hướng dẫn chi tiết gửi mình ngay đây ạ!"
    ),
    # 5. Phí ship thu hồi / Shipper lấy tận nhà khi đổi trả
    "return_shipping": (
        "Dạ em đang tra cứu quy định về hình thức thu hồi tận nhà và cước phí vận chuyển đổi trả "
        "gửi anh/chị ngay nhé ạ!"
    ),
    # 6. Quy trình / Thủ tục các bước thực hiện
    "procedure_steps": (
        "Dạ em đang tra cứu các bước thực hiện chi tiết để hướng dẫn anh/chị thao tác thuận tiện nhất nhé ạ!"
    ),
    # 7. Chính sách đổi trả chung
    "return_policy": (
        "Dạ em đang tra cứu quy định và điều kiện đổi trả hiện hành của Tiki "
        "để giải đáp chi tiết cho anh/chị ngay nhé ạ!"
    ),
    # 8. Yêu cầu hoàn tiền (An toàn nghiệp vụ)
    "request_refund": (
        "Dạ em đã tiếp nhận yêu cầu đối soát hoàn tiền cho đơn hàng{order_clause}. "
        "Em đang kiểm tra dữ liệu giao dịch từ hệ thống để hỗ trợ anh/chị ngay đây ạ."
    ),
    # 9. Chính sách hoàn tiền chung
    "refund_policy": (
        "Dạ em đang tra cứu quy định về thời gian và phương thức hoàn tiền "
        "để gửi hướng dẫn cụ thể cho anh/chị ngay nhé ạ!"
    ),
    # 10. Trạng thái hoàn tiền
    "refund_status": (
        "Dạ em đã ghi nhận yêu cầu tra cứu tiến độ hoàn tiền{order_clause}. "
        "Em đang đối soát với cổng thanh toán để cập nhật trạng thái tiền về cho anh/chị ngay ạ!"
    ),
    # 11. Lỗi thanh toán / Trừ tiền trùng
    "payment_issue": (
        "Dạ Tiki đã tiếp nhận phản ánh về sự cố thanh toán{order_clause}. "
        "Em đang đối soát giao dịch với ngân hàng để hỗ trợ anh/chị ngay đây ạ!"
    ),
    # 12. Phí giao hàng / Freeship
    "shipping_costs": (
        "Dạ em đang tra cứu biểu phí vận chuyển và chính sách Freeship "
        "áp dụng cho khu vực của mình gửi ngay nhé ạ!"
    ),
    # 13. Hủy đơn hàng
    "cancel_order": (
        "Dạ em đã tiếp nhận yêu cầu hủy đơn hàng{order_clause} của anh/chị. "
        "Em đang kiểm tra trạng thái xuất kho của kiện hàng ngay đây ạ!"
    ),
    # 14. Gặp nhân viên trực tiếp
    "human_agent": (
        "Dạ em đang chuyển cuộc trò chuyện đến chuyên viên CSKH phụ trách trực tiếp. "
        "Anh/chị chờ em trong giây lát nhé ạ!"
    ),
    # 15. Dịch vụ ngoài luồng / Thanh lý / Thu mua / Sản phẩm cũ
    "service_inquiry": (
        "Dạ Tiki đã ghi nhận câu hỏi của anh/chị về dịch vụ này. "
        "Em đang kiểm tra thông tin để giải đáp chi tiết cho mình ngay nhé ạ!"
    ),
    # 16. Chitchat cảm ơn kết hợp câu hỏi mới ("cảm ơn em, tiện thể hỏi luôn...")
    "thanks_and_question": (
        "Dạ em cảm ơn anh/chị! Về câu hỏi tiếp theo của mình, "
        "em đang kiểm tra thông tin để giải đáp ngay cho anh/chị đây ạ!"
    ),
    # 17. Chitchat chào hỏi thuần túy
    "chitchat_greeting": (
        "Dạ Tiki chào anh/chị! Rất vui được hỗ trợ mình hôm nay. Anh/chị cần em hỗ trợ thông tin gì về đơn hàng "
        "hoặc chính sách mua sắm không ạ?"
    ),
    # 18. Chitchat cảm ơn thuần túy
    "chitchat_thanks": (
        "Dạ không có gì ạ! Chúc anh/chị có trải nghiệm mua sắm thật vui vẻ cùng Tiki. "
        "Nếu cần hỗ trợ thêm bất cứ điều gì, anh/chị cứ nhắn cho em nhé!"
    ),
    # 19. Chitchat xác nhận thuần túy
    "chitchat_confirm": (
        "Dạ em đã ghi nhận thông tin của anh/chị. Em đang kiểm tra hỗ trợ mình ngay đây ạ!"
    ),
    # 20. Mặc định
    "default": (
        "Dạ em đã ghi nhận thông tin của anh/chị và đang kiểm tra hỗ trợ ngay đây ạ!"
    ),
}


class CustomerAcknowledgementEngine:
    """Tự động điền dữ liệu thực tế (Slot-filling) và nhận diện sắc thái câu hỏi cho câu trả lời dạo."""

    @classmethod
    def generate(
        cls,
        intent: str,
        facts: Optional[Dict[str, Any]] = None,
        input_type: Optional[str] = None,
        user_query: str = "",
        last_ack: Optional[str] = None,
    ) -> str:
        """Sinh câu trả lời dạo trước nhạy ngữ cảnh, chống lặp và slot-filling chính xác."""
        facts = facts or {}
        q_lower = user_query.lower().strip()

        has_thanks = any(k in q_lower for k in ["cam on", "cảm ơn", "thanks", "thank you"])
        has_inquiry = any(k in q_lower for k in ["tiện thể", "hỏi", "thanh lý", "thu mua", "thế còn", "vậy còn", "?", "không", "sao", "thế nào", "bao nhiêu"])

        # 1. Compound: Courtesy / Thanks + New Question
        if has_thanks and has_inquiry:
            template_key = "thanks_and_question"

        # 2. Service inquiry / Off-topic trade-in (e.g. thanh lý iPhone cũ)
        elif any(k in q_lower for k in ["thanh lý", "thu mua", "thu cũ", "đổi mới", "bán lại", "mua lại", "iphone cũ", "máy cũ", "đồ cũ"]):
            template_key = "service_inquiry"

        # 3. Return shipping fees / Shipper home pick-up (e.g. ai chịu phí ship, shipper đến tận nhà lấy)
        elif any(k in q_lower for k in ["ai chịu", "ai trả", "chịu phí", "trả phí", "phí ship", "cước ship", "shipper đến", "tận nhà", "thu hồi tận nhà", "lấy tận nhà"]):
            template_key = "return_shipping"

        # 4. Procedure / Step-by-step guidance
        elif any(k in q_lower for k in ["thủ tục", "quy trình", "các bước", "làm sao để", "cần làm gì"]):
            template_key = "procedure_steps"

        # 5. Pure chitchat
        elif input_type == "chitchat":
            if has_thanks:
                template_key = "chitchat_thanks"
            elif any(k in q_lower for k in ["ok", "oke", "vâng", "vang", "đúng", "dung", "dạ"]):
                template_key = "chitchat_confirm"
            else:
                template_key = "chitchat_greeting"

        # 6. Intent-based mapping with anti-repetition fallback
        else:
            template_key = intent
            if intent == "return_product" and last_ack and "sự cố sản phẩm" in last_ack:
                template_key = "return_followup"
            elif intent == "track_order" and last_ack and "kết nối hệ thống bưu tá" in last_ack:
                template_key = "track_order_alt"

        template = ACK_TEMPLATES.get(template_key, ACK_TEMPLATES.get(intent, ACK_TEMPLATES["default"]))

        # Format slot clauses
        order_id = facts.get("order_id")
        order_clause = f" {order_id}" if order_id else ""

        product = facts.get("product_name") or facts.get("item")
        issue = facts.get("issue")
        if product and issue:
            product_clause = f" {product} ({issue})"
        elif product:
            product_clause = f" {product}"
        elif issue:
            product_clause = f" ({issue})"
        else:
            product_clause = ""

        try:
            return template.format(
                order_clause=order_clause,
                product_clause=product_clause,
            )
        except Exception:
            return ACK_TEMPLATES["default"]
