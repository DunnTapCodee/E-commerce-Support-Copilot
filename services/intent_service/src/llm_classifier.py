"""LLM-based Intent Classifier using Google Gemini 2.5 Flash with structured output.
Supports context-augmented queries from Conversation Service ([PREV_INTENT:...], [ORDER:...]).
Includes intelligent semantic fallback for offline / test environments.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
from contracts.schemas import IntentPredictionResponse
from services.intent_service.src.pipeline.dataset import TARGET_INTENTS, OOS_LABEL
from services.intent_service.src.normalizer import normalize_vietnamese_query

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.xah.io/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openai-gpt-oss-20b")

INTENT_DESCRIPTIONS: Dict[str, str] = {
    "track_order": "Tra cứu thông tin, vị trí, giá tiền, tổng thanh toán, kiểm tra lại đơn, hóa đơn VAT, sản phẩm, tiến độ, trạng thái xử lý hoặc theo dõi bưu kiện đơn hàng (ví dụ: 'đơn ORD-1003 đang ở đâu', 'đơn hàng của mình bao nhiêu tiền', 'tôi muốn kiểm tra lại đơn', 'xuất hóa đơn VAT')",
    "cancel_order": "Yêu cầu hủy đơn hàng đã đặt (ví dụ: 'tôi muốn hủy đơn', 'cancel order please')",
    "delivery_time": "Hỏi về thời gian giao hàng, khi nào nhận được hàng, mất bao nhiêu ngày (ví dụ: 'khi nào giao tới', 'bao giờ nhận được hàng')",
    "delivery_issue": "Khiếu nại sự cố vận chuyển: giao trễ hạn, shipper không gọi, báo giao thành công nhưng chưa nhận được (ví dụ: 'giao quá chậm', 'delivery delay problem')",
    "shipping_costs": "Hỏi về biểu phí giao hàng, cước ship, có được miễn phí vận chuyển không (ví dụ: 'phí ship bao nhiêu', 'shipping fee')",
    "return_policy": "Hỏi về quy định, điều kiện, thời hạn, chính sách đổi hoặc trả hàng, chính sách bảo hành sản phẩm, sửa chữa hoặc bảo hành điện tử (ví dụ: 'chính sách đổi trả thế nào', 'hàng này có được bảo hành không', 'chính sách bảo hành')",
    "return_product": "Yêu cầu đổi hoặc trả một sản phẩm cụ thể bị lỗi, hỏng hóc hoặc không ưng ý (ví dụ: 'tôi muốn trả lại áo này do rách', 'đổi cái mới do lỗi')",
    "refund_policy": "Hỏi về quy định, điều kiện, phương thức hoàn lại tiền (ví dụ: 'chính sách hoàn tiền quy định sao', 'hoàn tiền mất bao lâu')",
    "request_refund": "Yêu cầu trực tiếp được hoàn tiền, hủy đơn lấy lại tiền (ví dụ: 'hoàn tiền lại cho tôi', 'tôi muốn lấy lại tiền')",
    "refund_status": "Tra cứu tiến độ hoàn tiền, hỏi tiền đã về thẻ/tài khoản ngân hàng chưa (ví dụ: 'tiền hoàn đã về chưa', 'refund status check')",
    "payment_issue": "Thắc mắc, hướng dẫn, lựa chọn hoặc sự cố thanh toán: các phương thức thanh toán (tiền mặt COD, thẻ ngân hàng, ví MoMo, VNPAY), cách thanh toán khi đặt hàng, lỗi trừ tiền nhiều lần, thẻ bị từ chối (ví dụ: 'chỉ cho thanh toán bằng tiền mặt thì làm sao', 'phương thức thanh toán gồm những gì', 'bị trừ tiền 2 lần')",
    "human_agent": "Yêu cầu gặp trực tiếp nhân viên tư vấn người thật, kết nối tổng đài viên (ví dụ: 'cho tôi gặp nhân viên', 'talk to human agent')",
    "get_discounts": "Hỏi về chương trình khuyến mãi, ưu đãi, voucher, mã giảm giá, coupon hoặc quà tặng, tích xu (ví dụ: 'có ưu đãi gì không', 'có mã giảm giá không')",
    "out_of_scope": "Các câu hỏi hoàn toàn KHÔNG liên quan đến thương mại điện tử, mua sắm hoặc CSKH (ví dụ: hỏi thời tiết, giải toán, thể thao, người nổi tiếng, chính trị, triết học)",
}

INTENT_SYSTEM_PROMPT = f"""Bạn là chuyên gia NLU phân loại ý định khách hàng (Intent Classification) cho sàn thương mại điện tử E-commerce Tiki/Shopee.

Hệ thống có các Ý ĐỊNH CHÍNH (TARGET_INTENTS) sau:
{chr(10).join(f"- {name}: {desc}" for name, desc in INTENT_DESCRIPTIONS.items())}

QUY TẮC PHÂN LOẠI & PHẠM VI (SCOPE BOUNDARY):
1. Đọc kỹ câu hỏi khách hàng (hỗ trợ cả Tiếng Việt và Tiếng Anh).
2. TẤT CẢ câu hỏi liên quan đến mua sắm, đặt hàng, thanh toán, vận chuyển, đổi trả, bảo hành, voucher, CSKH trên sàn TMĐT ĐỀU LÀ IN-SCOPE và BẮT BUỘC gán vào 1 trong 12 intent nghiệp vụ ở trên:
   - Thắc mắc phương thức thanh toán (tiền mặt COD, thẻ, ví điện tử) -> gán `payment_issue`.
   - Hỏi về bảo hành, sửa chữa sản phẩm -> gán `return_policy`.
   - Hỏi kiểm tra lại thông tin đơn, xuất hóa đơn VAT -> gán `track_order`.
3. TUYỆT ĐỐI CHỈ DÙNG `out_of_scope` khi câu hỏi hoàn toàn không thuộc về mua sắm hay TMĐT (như thời tiết, toán học, ronaldo, bóng đá, thơ ca).
4. XỬ LÝ NGỮ CẢNH HỘI THOẠI:
   - Nếu câu hỏi bắt đầu bằng các thẻ ngữ cảnh hội thoại như `[PREV_INTENT: ...]`, `[ORDER: ...]`, `[AWAITING: ...]`, bạn PHẢI cân nhắc ngữ cảnh này.
   - Ví dụ: `[PREV_INTENT:track_order] [AWAITING:order_id] ORD-1003` -> Đây là câu bổ sung thông tin cho `track_order`.
   - Nếu khách đảo ý định: `[PREV_INTENT:cancel_order] thôi không hủy nữa, xem bao giờ giao` -> Intent chuyển sang `delivery_time`.
5. ĐỊNH DẠNG ĐẦU RA:
   Trả về DUY NHẤT một khối JSON hợp lệ theo cấu trúc sau (không kèm markdown ngoài):
{{
  "intent": "<tên intent thuộc danh sách trên>",
  "confidence": <số thực từ 0.70 đến 0.99>,
  "reasoning": "<lý do ngắn gọn>",
  "is_in_scope": <true nếu thuộc 12 intent, false nếu out_of_scope>,
  "probabilities": {{
    "<top_intent_1>": <xác suất>,
    "<top_intent_2>": <xác suất>
  }}
}}
"""


class LLMIntentClassifier:
    """Classifies customer intents using Gemini 2.5 Flash with structured output and robust fallback."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = 20):
        self.api_key = api_key or GEMINI_API_KEY
        self.timeout = timeout

    def predict(self, query: str) -> IntentPredictionResponse:
        """Synchronously predict intent using OpenAI-compatible GPT-OSS model with robust fallback."""
        start_time = time.perf_counter()
        clean_query = query.strip()

        openai_key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)

        # 1. Primary: OpenAI-compatible (openai-gpt-oss-20b) with multi-key failover
        try:
            result = self._call_openai_compatible(clean_query)
            if result:
                latency = (time.perf_counter() - start_time) * 1000
                result.latency_ms = round(latency, 2)
                return result
        except Exception as e:
            print(f"[LLMIntentClassifier] OpenAI-compatible call failed: {e}")

        # High-precision semantic heuristic fallback
        fallback_resp = self._semantic_fallback(clean_query)
        fallback_resp.latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return fallback_resp

    def _call_openai_compatible(self, query: str, api_key: Optional[str] = None) -> Optional[IntentPredictionResponse]:
        """Call OpenAI-compatible chat completion for intent classification with multi-key failover."""
        from contracts.llm_failover import call_chat_completion_sync_with_failover

        base_url = os.getenv("OPENAI_BASE_URL", OPENAI_BASE_URL).rstrip("/")
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)

        messages = [
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Phân loại câu hỏi sau:\n\"{query}\""}
        ]
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2048,
        }

        data = call_chat_completion_sync_with_failover(payload, base_url=base_url, timeout=self.timeout)
        if data:
            choices = data.get("choices", [])
            if choices:
                raw_text = choices[0].get("message", {}).get("content", "")
                if not raw_text.strip():
                    raw_text = choices[0].get("message", {}).get("reasoning_content", "")
                parsed = self._parse_json(raw_text)
                if parsed and "intent" in parsed:
                    intent = parsed["intent"]
                    if intent not in INTENT_DESCRIPTIONS:
                        intent = "out_of_scope"

                    conf = float(parsed.get("confidence", 0.90))
                    is_in_scope = bool(parsed.get("is_in_scope", intent != OOS_LABEL and intent in TARGET_INTENTS))
                    probs = parsed.get("probabilities", {intent: conf})

                    return IntentPredictionResponse(
                        intent=intent,
                        confidence=conf,
                        is_in_scope=is_in_scope,
                        language="vi" if re.search(r"[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]", query.lower()) else "en",
                        model_name=model,
                        all_probabilities=probs,
                        latency_ms=0.0,
                    )
        return None

    def _call_gemini(self, query: str) -> Optional[IntentPredictionResponse]:
        """Send prompt to Gemini 2.5 Flash and parse structured JSON."""
        payload = {
            "systemInstruction": {
                "parts": [{"text": INTENT_SYSTEM_PROMPT}]
            },
            "contents": [
                {
                    "parts": [{"text": f"Phân loại câu hỏi sau:\n\"{query}\""}]
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "thinkingConfig": {
                    "thinkingBudget": 0
                },
            },
        }

        url = f"{GEMINI_API_URL}?key={self.api_key}"
        resp = requests.post(url, json=payload, timeout=self.timeout, verify=False)

        if resp.status_code == 200:
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
                parsed = self._parse_json(raw_text)
                if parsed and "intent" in parsed:
                    intent = parsed["intent"]
                    if intent not in INTENT_DESCRIPTIONS:
                        intent = "out_of_scope"

                    conf = float(parsed.get("confidence", 0.90))
                    is_in_scope = bool(parsed.get("is_in_scope", intent != OOS_LABEL and intent in TARGET_INTENTS))
                    probs = parsed.get("probabilities", {intent: conf})

                    return IntentPredictionResponse(
                        intent=intent,
                        confidence=conf,
                        is_in_scope=is_in_scope,
                        language="vi" if re.search(r"[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]", query.lower()) else "en",
                        model_name="gemini-2.5-flash",
                        all_probabilities=probs,
                    )
        return None

    def _parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Safely extract and parse JSON object from LLM response text."""
        try:
            return json.loads(text)
        except Exception:
            pass

        # Match markdown block ```json ... ```
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        # Match raw JSON object
        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass

        return None

    def _semantic_fallback(self, query: str) -> IntentPredictionResponse:
        """Accurate fallback classifier for testing and offline environments with unaccented normalization."""
        norm_query, _ = normalize_vietnamese_query(query)
        q_lower = norm_query.lower()

        # Handle context tags from conversation service
        prev_intent = None
        prev_match = re.search(r"\[prev_intent:([a-z_]+)\]", q_lower)
        if prev_match:
            prev_intent = prev_match.group(1)

        # 1. Negation switch cues (e.g. "thôi không hủy nữa, xem bao giờ giao")
        if any(w in q_lower for w in ["thôi không hủy", "thoi khong huy", "không muốn hủy", "đổi ý"]):
            if any(w in q_lower for w in ["giao", "khi nào", "bao giờ", "arrive", "time"]):
                return self._build_resp("delivery_time", 0.94, query)
            return self._build_resp("track_order", 0.90, query)

        # 2. Context carryover for slot filling (e.g. query is just ORD-XXXX or short answer)
        if prev_intent and len(query.split()) <= 5 and ("ord-" in q_lower or "mã đơn" in q_lower or "số đt" in q_lower):
            return self._build_resp(prev_intent, 0.95, query)

        # 3. Explicit Human Agent
        if re.search(r"\b(gặp.*(nhân viên|người thật|chuyên viên)|nói chuyện với người|tổng đài viên|human agent|live agent|support representative|support staff|nhân viên tư vấn|nhân viên trực|chuyển máy.*nhân viên|connect.*customer support|talk to real)\b", q_lower):
            return self._build_resp("human_agent", 0.96, query)

        # 4. Request refund (action of requesting money back - prioritized over cancel if refund is asked)
        if re.search(r"\b(yêu cầu hoàn tiền|hoàn lại tiền|muốn hoàn.*tiền|hoàn tiền cho tôi|hoàn trả.*tài khoản|hoàn tiền lại|lấy lại tiền|i want.*refund|demand.*refund|refund my money|hoàn tiền gấp|thủ tục.*lấy lại tiền|hủy.*hoàn tiền|hoàn tiền.*hủy|trả lại tiền cho tôi)\b", q_lower):
            return self._build_resp("request_refund", 0.95, query)

        # 5. Refund status (asking if refund arrived / checking status)
        if re.search(r"\b(tiền hoàn|tiến độ hoàn tiền|trạng thái.*hoàn tiền|refund.*status|when.*refund|refund.*processed|thông báo hoàn tiền)\b", q_lower):
            return self._build_resp("refund_status", 0.94, query)

        # 6. Refund policy (rules/terms/methods of refunding)
        if re.search(r"\b(chính sách hoàn tiền|quy định.*hoàn|thời hạn hoàn tiền|điều kiện.*hoàn tiền|refund policy|refund terms|chính sách trả lại tiền|hoàn tiền.*mất bao lâu|refund process|hoàn tiền.*(momo|ví|ngân hàng|thẻ)|hoàn.*về ví)\b", q_lower):
            return self._build_resp("refund_policy", 0.94, query)

        # 7. Cancel order (checked after refund)
        if re.search(r"\b(hủy đơn|huy don|hủy lệnh|huy lenh|cancel.*order|cancel.*purchase|dừng đơn|dung don|không muốn mua|khong muon mua|muốn hủy đơn|hủy giúp tôi đơn)\b", q_lower):
            return self._build_resp("cancel_order", 0.95, query)

        # 8. Payment issues & payment methods
        if re.search(r"\b(tiền mặt|phương thức thanh toán|hình thức thanh toán|thanh toán bằng|cách thanh toán|trừ.*(2 lần|hai lần)|lỗi thanh toán|thanh toán thất bại|thẻ.*bị từ chối|vnpay|momo|zalopay|mã qr.*thanh toán|payment failed|payment error|charged twice|trừ tiền|credit card.*error|sự cố trừ tiền|không thanh toán được|chỉ cho thanh toán)\b", q_lower):
            return self._build_resp("payment_issue", 0.95, query)

        # 9. Return policy & Warranty (guidelines/rules for returns and warranties)
        if re.search(r"\b(chính sách.*đổi trả|quy định.*(đổi|trả)|thời hạn.*(đổi|trả)|điều kiện.*(đổi|trả)|return policy|quy trình đổi trả|bóc seal.*đổi trả|newest.*return policy|đổi trả.*bao nhiêu ngày|return.*condition|can i return|bảo hành|bảo dưỡng|chính sách bảo hành|có được bảo hành|hàng chính hãng|chính hãng)\b", q_lower):
            return self._build_resp("return_policy", 0.94, query)

        # 10. Return product (action on a specific item)
        if re.search(r"\b(đổi.*size|đổi.*áo|trả lại hàng|trả hàng|hàng.*lỗi.*đổi|đổi cái mới|đổi sang|defective.*return|exchange|damaged.*product|hàng không đúng mô tả|đổi trả món đồ|muốn trả lại|yêu cầu trả lại|yêu cầu trả sản phẩm|trả lại cái|return this product)\b", q_lower):
            return self._build_resp("return_product", 0.93, query)

        # 11. Shipping costs
        if re.search(r"\b(phí ship|phi ship|phí vận chuyển|cước|freeship|shipping costs?|shipping fee|delivery fee|phí giao hàng|delivery free|free.*delivery|biểu phí giao hàng)\b", q_lower):
            return self._build_resp("shipping_costs", 0.95, query)

        # 12. Delivery issues (complaints about delivery)
        if re.search(r"\b(chưa giao.*báo|giao trễ|giao chậm|chưa nhận được|quá hạn|shipper.*không|giao nhầm|nhầm địa chỉ|thất lạc|delivery delay|package delayed|courier|delivery problem)\b", q_lower):
            return self._build_resp("delivery_issue", 0.94, query)

        # 13. Delivery time (asking when parcel will arrive)
        if re.search(r"\b(bao giờ.*(nhận|giao|tới)|khi nào.*(giao|tới|nhận)|mấy ngày.*(giao|có|nhận)|thời gian.*(giao|vận chuyển)|when.*arrive|how long.*(delivery|shipping)|estimated delivery|khi nào.*shipper|ngày mai có giao kịp|giao hàng tới|giao tới)\b", q_lower):
            return self._build_resp("delivery_time", 0.94, query)

        # 13b. Get discounts / Promotions / Vouchers
        if re.search(r"\b(ưu đãi|khuyến mãi|khuyến mại|voucher|mã giảm|coupon|freeship|giảm giá|chiết khấu|quà tặng|tiki xu)\b", q_lower):
            return self._build_resp("get_discounts", 0.95, query)

        # 14. Track order & Order details (status, progress, price, amount, VAT invoice)
        if re.search(r"\b(track|tracking|ord-[a-z0-9-]+|đơn hàng.*ở đâu|đơn hàng.*đến đâu|kiểm tra.*đơn|kiểm tra lại đơn|tra cứu.*đơn|xuất kho|định vị|bưu kiện|tiến độ.*đơn|where is my|delivery status|bao nhiêu tiền|hết bao nhiêu|tổng tiền|giá bao nhiêu|đơn.*của mình.*là gì|hóa đơn.*vat|hóa đơn đỏ|xuất hóa đơn)\b", q_lower):
            return self._build_resp("track_order", 0.94, query)

        # 15. General keywords
        if "policy" in q_lower or "chính sách" in q_lower:
            return self._build_resp("return_policy", 0.85, query)

        # 16. Out of scope (weather, math, general trivia, unrelated chat)
        return self._build_resp("out_of_scope", 0.90, query, is_in_scope=False)

    def _build_resp(self, intent: str, conf: float, query: str, is_in_scope: bool = True) -> IntentPredictionResponse:
        """Construct IntentPredictionResponse with language detection."""
        is_vi = bool(re.search(r"[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]", query.lower()))
        return IntentPredictionResponse(
            intent=intent,
            confidence=conf,
            is_in_scope=is_in_scope and intent in TARGET_INTENTS and intent != OOS_LABEL,
            language="vi" if is_vi else "en",
            model_name="llm_intent_classifier",
            all_probabilities={intent: conf},
        )
