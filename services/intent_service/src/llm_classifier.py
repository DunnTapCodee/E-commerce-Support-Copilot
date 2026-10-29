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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.xah.io/v1").rstrip("/")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "openai-gpt-oss-20b")

INTENT_DESCRIPTIONS: Dict[str, str] = {
    "track_order": "Tra cứu vị trí, tiến độ, trạng thái xử lý hoặc theo dõi bưu kiện đơn hàng (ví dụ: 'đơn ORD-1003 đang ở đâu', 'track my order status')",
    "cancel_order": "Yêu cầu hủy đơn hàng đã đặt (ví dụ: 'tôi muốn hủy đơn', 'cancel order please')",
    "delivery_time": "Hỏi về thời gian giao hàng, khi nào nhận được hàng, mất bao nhiêu ngày (ví dụ: 'khi nào giao tới', 'how long does shipping take')",
    "delivery_issue": "Khiếu nại sự cố vận chuyển: giao trễ hạn, shipper không gọi, báo giao thành công nhưng chưa nhận được (ví dụ: 'giao quá chậm', 'delivery delay problem')",
    "shipping_costs": "Hỏi về biểu phí giao hàng, cước ship, có được miễn phí vận chuyển không (ví dụ: 'phí ship bao nhiêu', 'shipping fee')",
    "return_policy": "Hỏi về quy định, điều kiện, thời hạn, chính sách đổi hoặc trả hàng (ví dụ: 'chính sách đổi trả thế nào', 'return policy guidelines')",
    "return_product": "Yêu cầu đổi hoặc trả một sản phẩm cụ thể bị lỗi, hỏng hóc hoặc không ưng ý (ví dụ: 'tôi muốn trả lại áo này do rách', 'return this damaged item')",
    "refund_policy": "Hỏi về quy định, điều kiện, phương thức hoàn lại tiền (ví dụ: 'chính sách hoàn tiền quy định sao', 'refund policy')",
    "request_refund": "Yêu cầu trực tiếp được hoàn tiền, hủy đơn lấy lại tiền (ví dụ: 'hoàn tiền lại cho tôi', 'i want a refund')",
    "refund_status": "Tra cứu tiến độ hoàn tiền, hỏi tiền đã về thẻ/tài khoản ngân hàng chưa (ví dụ: 'tiền hoàn đã về chưa', 'refund status check')",
    "payment_issue": "Sự cố giao dịch thanh toán: bị trừ tiền nhiều lần, lỗi cổng VNPAY/MoMo, thẻ bị từ chối (ví dụ: 'tài khoản bị trừ 2 lần', 'payment failed')",
    "human_agent": "Yêu cầu gặp trực tiếp nhân viên tư vấn người thật, kết nối tổng đài viên (ví dụ: 'cho tôi gặp nhân viên', 'talk to human agent')",
    "out_of_scope": "Các câu hỏi nằm ngoài phạm vi thương mại điện tử CSKH (ví dụ: thời tiết, toán học, chém gió không liên quan)",
}

INTENT_SYSTEM_PROMPT = f"""Bạn là chuyên gia NLU phân loại ý định khách hàng (Intent Classification) cho sàn thương mại điện tử E-commerce Tiki/Shopee.

Hệ thống có 12 Ý ĐỊNH CHÍNH (TARGET_INTENTS) sau:
{chr(10).join(f"- {name}: {desc}" for name, desc in INTENT_DESCRIPTIONS.items())}

QUY TẮC PHÂN LOẠI:
1. Đọc kỹ câu hỏi khách hàng (hỗ trợ cả Tiếng Việt và Tiếng Anh).
2. XỬ LÝ NGỮ CẢNH HỘI THOẠI:
   - Nếu câu hỏi bắt đầu bằng các thẻ ngữ cảnh hội thoại như `[PREV_INTENT: ...]`, `[ORDER: ...]`, `[AWAITING: ...]`, bạn PHẢI cân nhắc ngữ cảnh này.
   - Ví dụ: `[PREV_INTENT:track_order] [AWAITING:order_id] ORD-1003` -> Đây là câu bổ sung thông tin cho `track_order`.
   - Nếu khách đảo ý định: `[PREV_INTENT:cancel_order] thôi không hủy nữa, xem bao giờ giao` -> Intent chuyển sang `delivery_time`.
3. PHÂN BIỆT RÕ CẶP INTENT DỄ NHẦM LẪN:
   - `return_policy` (hỏi điều kiện/chính sách đổi trả) vs `return_product` (yêu cầu đổi trả sản phẩm cụ thể).
   - `refund_policy` (hỏi chính sách/thời hạn hoàn tiền) vs `request_refund` (yêu cầu hoàn tiền ngay).
   - `request_refund` (yêu cầu hoàn tiền) vs `refund_status` (hỏi tiến độ/tiền đã về tài khoản chưa).
   - `delivery_time` (hỏi bao giờ tới) vs `delivery_issue` (khiếu nại shipper, trễ hạn nghiêm trọng, mất hàng).
4. ĐỊNH DẠNG ĐẦU RA:
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

    def __init__(self, api_key: Optional[str] = None, timeout: int = 8):
        self.api_key = api_key or GEMINI_API_KEY
        self.timeout = timeout

    def predict(self, query: str) -> IntentPredictionResponse:
        """Synchronously predict intent using LLM or rule-based fallback."""
        start_time = time.perf_counter()
        clean_query = query.strip()

        provider = os.getenv("LLM_PROVIDER", LLM_PROVIDER).lower()
        openai_key = os.getenv("OPENAI_API_KEY", OPENAI_API_KEY)
        gemini_key = self.api_key or os.getenv("GEMINI_API_KEY", "")

        # 1. Try OpenAI-compatible endpoint if configured (e.g. ckey.vn openai-gpt-oss-20b)
        if provider == "openai_compatible" and openai_key:
            try:
                result = self._call_openai_compatible(clean_query, openai_key)
                if result:
                    latency = (time.perf_counter() - start_time) * 1000
                    result.latency_ms = round(latency, 2)
                    return result
            except Exception as e:
                print(f"[LLMIntentClassifier] OpenAI-compatible call failed: {e}")

        # 2. Try Gemini API if key is configured
        if gemini_key and gemini_key != "your_gemini_api_key_here":
            try:
                result = self._call_gemini(clean_query)
                if result:
                    latency = (time.perf_counter() - start_time) * 1000
                    result.latency_ms = round(latency, 2)
                    return result
            except Exception as e:
                print(f"[LLMIntentClassifier] Gemini API call failed: {e}. Using semantic fallback.")

        # 3. Fallback to OpenAI if Gemini failed
        if openai_key and provider != "openai_compatible":
            try:
                result = self._call_openai_compatible(clean_query, openai_key)
                if result:
                    latency = (time.perf_counter() - start_time) * 1000
                    result.latency_ms = round(latency, 2)
                    return result
            except Exception as e:
                print(f"[LLMIntentClassifier] OpenAI fallback failed: {e}")

        # High-precision semantic heuristic fallback
        fallback_resp = self._semantic_fallback(clean_query)
        fallback_resp.latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return fallback_resp

    def _call_openai_compatible(self, query: str, api_key: str) -> Optional[IntentPredictionResponse]:
        """Call OpenAI-compatible chat completion for intent classification."""
        base_url = os.getenv("OPENAI_BASE_URL", OPENAI_BASE_URL).rstrip("/")
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)
        url = f"{base_url}/chat/completions"

        messages = [
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": f"Phân loại câu hỏi sau:\n\"{query}\""}
        ]
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1
        }

        resp = requests.post(url, json=payload, headers=headers, timeout=self.timeout)
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices:
                raw_text = choices[0].get("message", {}).get("content", "")
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
        resp = requests.post(url, json=payload, timeout=self.timeout)

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
        """Accurate fallback classifier for testing and offline environments."""
        q_lower = query.lower()

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
        if re.search(r"\b(yêu cầu hoàn tiền|hoàn tiền cho tôi|hoàn trả.*tài khoản|hoàn tiền lại|lấy lại tiền|i want.*refund|demand.*refund|refund my money|hoàn tiền gấp|thủ tục.*lấy lại tiền|hủy.*hoàn tiền|hoàn tiền.*hủy|trả lại tiền cho tôi)\b", q_lower):
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

        # 8. Payment issues
        if re.search(r"\b(trừ.*(2 lần|hai lần)|lỗi thanh toán|thanh toán thất bại|thẻ.*bị từ chối|vnpay|momo|mã qr.*thanh toán|payment failed|payment error|charged twice|trừ tiền|credit card.*error|sự cố trừ tiền)\b", q_lower):
            return self._build_resp("payment_issue", 0.95, query)

        # 9. Return policy (guidelines/rules for returns)
        if re.search(r"\b(chính sách.*đổi trả|quy định.*(đổi|trả)|thời hạn.*(đổi|trả)|điều kiện.*(đổi|trả)|return policy|quy trình đổi trả|bóc seal.*đổi trả|newest.*return policy|đổi trả.*bao nhiêu ngày|return.*condition|can i return)\b", q_lower):
            return self._build_resp("return_policy", 0.94, query)

        # 10. Return product (action on a specific item)
        if re.search(r"\b(đổi.*size|đổi.*áo|trả lại hàng|trả hàng|hàng.*lỗi.*đổi|đổi cái mới|đổi sang|defective.*return|exchange|damaged.*product|hàng không đúng mô tả|đổi trả món đồ|muốn trả lại hàng|yêu cầu trả sản phẩm|return this product)\b", q_lower):
            return self._build_resp("return_product", 0.93, query)

        # 11. Shipping costs
        if re.search(r"\b(phí ship|phi ship|phí vận chuyển|cước|freeship|shipping costs?|shipping fee|delivery fee|phí giao hàng|delivery free|free.*delivery|biểu phí giao hàng)\b", q_lower):
            return self._build_resp("shipping_costs", 0.95, query)

        # 12. Delivery issues (complaints about delivery)
        if re.search(r"\b(chưa giao.*báo|giao trễ|giao chậm|chưa nhận được|quá hạn|shipper.*không|giao nhầm|nhầm địa chỉ|thất lạc|delivery delay|package delayed|courier|delivery problem)\b", q_lower):
            return self._build_resp("delivery_issue", 0.94, query)

        # 13. Delivery time (asking when parcel will arrive)
        if re.search(r"\b(bao giờ.*nhận|khi nào.*giao|mấy ngày.*(giao|có|nhận)|thời gian.*(giao|vận chuyển)|when.*arrive|how long.*(delivery|shipping)|estimated delivery|khi nào.*shipper|ngày mai có giao kịp|giao hàng tới)\b", q_lower):
            return self._build_resp("delivery_time", 0.94, query)

        # 14. Track order
        if re.search(r"\b(track|tracking|ord-[a-z0-9-]+|đơn hàng.*ở đâu|đơn hàng.*đến đâu|kiểm tra.*đơn|tra cứu.*đơn|xuất kho|định vị|bưu kiện|tiến độ.*đơn|where is my|delivery status)\b", q_lower):
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
