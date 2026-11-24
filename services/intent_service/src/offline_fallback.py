"""Offline / LLM-Unavailable Semantic Intent Fallback for Intent Service.

Separated from LLMIntentClassifier so rule-based heuristics only activate when
live LLM inference is disabled or unreachable.
"""
from __future__ import annotations

import re
from typing import Optional

from contracts.schemas import IntentPredictionResponse
from services.intent_service.src.normalizer import normalize_vietnamese_query
from services.intent_service.src.pipeline.dataset import OOS_LABEL, TARGET_INTENTS


class OfflineIntentFallback:
    """Deterministic keyword/regex fallback classifier for offline or degraded environments."""

    @classmethod
    def build_response(
        cls,
        intent: str,
        conf: float,
        query: str,
        is_in_scope: bool = True,
        model_name: str = "semantic_rule_fallback",
    ) -> IntentPredictionResponse:
        """Construct IntentPredictionResponse with language detection."""
        is_vi = bool(
            re.search(
                r"[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]",
                query.lower(),
            )
        )
        return IntentPredictionResponse(
            intent=intent,
            confidence=conf,
            is_in_scope=is_in_scope and intent in TARGET_INTENTS and intent != OOS_LABEL,
            language="vi" if is_vi else "en",
            model_name=model_name,
            all_probabilities={intent: conf},
        )

    @classmethod
    def classify(cls, query: str) -> IntentPredictionResponse:
        """Classify query deterministically using normalized Vietnamese/English cues."""
        norm_query, _ = normalize_vietnamese_query(query)
        q_lower = norm_query.lower()

        prev_intent: Optional[str] = None
        prev_match = re.search(r"\[prev_intent:([a-z_]+)\]", q_lower)
        if prev_match:
            prev_intent = prev_match.group(1)

        if any(w in q_lower for w in ["thôi không hủy", "thoi khong huy", "không muốn hủy", "đổi ý"]):
            if any(w in q_lower for w in ["giao", "khi nào", "bao giờ", "arrive", "time"]):
                return cls.build_response("delivery_time", 0.94, query)
            return cls.build_response("track_order", 0.90, query)

        if prev_intent and len(query.split()) <= 5 and ("ord-" in q_lower or "mã đơn" in q_lower or "số đt" in q_lower):
            return cls.build_response(prev_intent, 0.95, query)

        if re.search(r"\b(gặp.*(nhân viên|người thật|chuyên viên)|nói chuyện với người|tổng đài viên|human agent|live agent|support representative|support staff|nhân viên tư vấn|nhân viên trực|chuyển máy.*nhân viên|connect.*customer support|talk to real)\b", q_lower):
            return cls.build_response("human_agent", 0.96, query)

        if re.search(r"\b(yêu cầu hoàn tiền|hoàn lại tiền|muốn hoàn.*tiền|hoàn tiền cho tôi|hoàn trả.*tài khoản|hoàn tiền lại|lấy lại tiền|i want.*refund|demand.*refund|refund my money|hoàn tiền gấp|thủ tục.*lấy lại tiền|hủy.*hoàn tiền|hoàn tiền.*hủy|trả lại tiền cho tôi)\b", q_lower):
            return cls.build_response("request_refund", 0.95, query)

        if re.search(r"\b(tiền hoàn|tiến độ hoàn tiền|trạng thái.*hoàn tiền|refund.*status|when.*refund|refund.*processed|thông báo hoàn tiền)\b", q_lower):
            return cls.build_response("refund_status", 0.94, query)

        if re.search(r"\b(chính sách hoàn tiền|quy định.*hoàn|thời hạn hoàn tiền|điều kiện.*hoàn tiền|refund policy|refund terms|chính sách trả lại tiền|hoàn tiền.*mất bao lâu|refund process|hoàn tiền.*(momo|ví|ngân hàng|thẻ)|hoàn.*về ví)\b", q_lower):
            return cls.build_response("refund_policy", 0.94, query)

        if re.search(r"\b(hủy đơn|huy don|hủy lệnh|huy lenh|cancel.*order|cancel.*purchase|dừng đơn|dung don|không muốn mua|khong muon mua|muốn hủy đơn|hủy giúp tôi đơn)\b", q_lower):
            return cls.build_response("cancel_order", 0.95, query)

        if re.search(r"\b(tiền mặt|phương thức thanh toán|hình thức thanh toán|thanh toán bằng|cách thanh toán|trừ.*(2 lần|hai lần)|lỗi thanh toán|thanh toán thất bại|thẻ.*bị từ chối|vnpay|momo|zalopay|mã qr.*thanh toán|payment failed|payment error|charged twice|trừ tiền|credit card.*error|sự cố trừ tiền|không thanh toán được|chỉ cho thanh toán)\b", q_lower):
            return cls.build_response("payment_issue", 0.95, query)

        if re.search(r"\b(bảo hành|bao hanh|bảo dưỡng|chính sách bảo hành|có được bảo hành|sửa chữa bảo hành|warranty)\b", q_lower):
            return cls.build_response("warranty", 0.94, query)

        if re.search(r"\b(chính sách.*đổi trả|quy định.*(đổi|trả)|thời hạn.*(đổi|trả)|điều kiện.*(đổi|trả)|return policy|quy trình đổi trả|bóc seal.*đổi trả|newest.*return policy|đổi trả.*bao nhiêu ngày|return.*condition|can i return|hàng chính hãng|chính hãng)\b", q_lower):
            return cls.build_response("return_policy", 0.94, query)

        if re.search(r"\b(đổi.*size|đổi.*áo|trả lại hàng|trả hàng|hàng.*lỗi.*đổi|đổi cái mới|đổi sang|defective.*return|exchange|damaged.*product|hàng không đúng mô tả|đổi trả món đồ|muốn trả lại|yêu cầu trả lại|yêu cầu trả sản phẩm|trả lại cái|return this product)\b", q_lower):
            return cls.build_response("return_product", 0.93, query)

        if re.search(r"\b(phí ship|phi ship|phí vận chuyển|cước|freeship|shipping costs?|shipping fee|delivery fee|phí giao hàng|delivery free|free.*delivery|biểu phí giao hàng)\b", q_lower):
            return cls.build_response("shipping_costs", 0.95, query)

        if re.search(r"\b(chưa giao.*báo|giao trễ|giao chậm|chưa nhận được|quá hạn|shipper.*không|giao nhầm|nhầm địa chỉ|thất lạc|delivery delay|package delayed|courier|delivery problem)\b", q_lower):
            return cls.build_response("delivery_issue", 0.94, query)

        if re.search(r"\b(bao giờ.*(nhận|giao|tới)|khi nào.*(giao|tới|nhận)|mấy ngày.*(giao|có|nhận)|thời gian.*(giao|vận chuyển)|when.*arrive|how long.*(delivery|shipping)|estimated delivery|khi nào.*shipper|ngày mai có giao kịp|giao hàng tới|giao tới)\b", q_lower):
            return cls.build_response("delivery_time", 0.94, query)

        if re.search(r"\b(ưu đãi|khuyến mãi|khuyến mại|voucher|mã giảm|coupon|freeship|giảm giá|chiết khấu|quà tặng|tiki xu)\b", q_lower):
            return cls.build_response("get_discounts", 0.95, query)

        if re.search(r"\b(quên mật khẩu|đổi mật khẩu|khôi phục mật khẩu|lấy lại mật khẩu|reset password|recover password|forgot password)\b", q_lower):
            return cls.build_response("recover_password", 0.94, query)
        if re.search(r"\b(tạo tài khoản|đăng ký tài khoản|đăng ký thành viên|mở tài khoản|create account|sign up|register account)\b", q_lower):
            return cls.build_response("create_account", 0.94, query)

        if re.search(r"\b(track|tracking|ord-[a-z0-9-]+|đơn hàng.*ở đâu|đơn hàng.*đến đâu|kiểm tra.*đơn|kiểm tra lại đơn|tra cứu.*đơn|xuất kho|định vị|bưu kiện|tiến độ.*đơn|where is my|delivery status|bao nhiêu tiền|hết bao nhiêu|tổng tiền|giá bao nhiêu|đơn.*của mình.*là gì|hóa đơn.*vat|hóa đơn đỏ|xuất hóa đơn)\b", q_lower):
            return cls.build_response("track_order", 0.94, query)

        if "policy" in q_lower or "chính sách" in q_lower:
            return cls.build_response("return_policy", 0.85, query)

        return cls.build_response("out_of_scope", 0.90, query, is_in_scope=False)
