"""LLM-based Intent Classifier using OpenAI-compatible CKEY.VN endpoint (`FR-INT-003`).

Supports context-augmented queries from Conversation Service ([PREV_INTENT:...], [ORDER:...])
and delegates offline deterministic fallback to `OfflineIntentFallback`.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, Optional

from contracts.llm_failover import (
    DEFAULT_OPENAI_BASE_URL,
    call_chat_completion_sync_with_failover,
    get_available_api_keys,
    get_default_openai_model,
    is_external_llm_disabled,
)
from contracts.schemas import IntentPredictionResponse
from services.intent_service.src.offline_fallback import OfflineIntentFallback
from services.intent_service.src.pipeline.dataset import OOS_LABEL, TARGET_INTENTS

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai_compatible").lower()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", DEFAULT_OPENAI_BASE_URL).rstrip("/")
OPENAI_MODEL = get_default_openai_model()

INTENT_DESCRIPTIONS: Dict[str, str] = {
    "track_order": "Tra cứu thông tin, vị trí, giá tiền, tổng thanh toán, kiểm tra lại đơn, hóa đơn VAT, sản phẩm, tiến độ, trạng thái xử lý hoặc theo dõi bưu kiện đơn hàng (ví dụ: 'đơn ORD-1003 đang ở đâu', 'đơn hàng của mình bao nhiêu tiền', 'tôi muốn kiểm tra lại đơn', 'xuất hóa đơn VAT')",
    "cancel_order": "Yêu cầu hủy đơn hàng đã đặt (ví dụ: 'tôi muốn hủy đơn', 'cancel order please')",
    "delivery_time": "Hỏi về thời gian giao hàng, khi nào nhận được hàng, mất bao nhiêu ngày (ví dụ: 'khi nào giao tới', 'bao giờ nhận được hàng')",
    "delivery_issue": "Khiếu nại sự cố vận chuyển: giao trễ hạn, shipper không gọi, báo giao thành công nhưng chưa nhận được (ví dụ: 'giao quá chậm', 'delivery delay problem')",
    "shipping_costs": "Hỏi về biểu phí giao hàng, cước ship, có được miễn phí vận chuyển không (ví dụ: 'phí ship bao nhiêu', 'shipping fee')",
    "return_policy": "Hỏi về quy định, điều kiện, thời hạn, chính sách đổi hoặc trả hàng (ví dụ: 'chính sách đổi trả thế nào', 'đổi trả hàng trong bao nhiêu ngày')",
    "return_product": "Yêu cầu đổi hoặc trả một sản phẩm cụ thể bị lỗi, hỏng hóc hoặc không ưng ý (ví dụ: 'tôi muốn trả lại áo này do rách', 'đổi cái mới do lỗi')",
    "refund_policy": "Hỏi về quy định, điều kiện, phương thức hoàn lại tiền (ví dụ: 'chính sách hoàn tiền quy định sao', 'hoàn tiền mất bao lâu')",
    "request_refund": "Yêu cầu trực tiếp được hoàn tiền, hủy đơn lấy lại tiền (ví dụ: 'hoàn tiền lại cho tôi', 'tôi muốn lấy lại tiền')",
    "refund_status": "Tra cứu tiến độ hoàn tiền, hỏi tiền đã về thẻ/tài khoản ngân hàng chưa (ví dụ: 'tiền hoàn đã về chưa', 'refund status check')",
    "payment_issue": "Thắc mắc, hướng dẫn, lựa chọn hoặc sự cố thanh toán: các phương thức thanh toán (tiền mặt COD, thẻ ngân hàng, ví MoMo, VNPAY), cách thanh toán khi đặt hàng, lỗi trừ tiền nhiều lần, thẻ bị từ chối (ví dụ: 'chỉ cho thanh toán bằng tiền mặt thì làm sao', 'phương thức thanh toán gồm những gì', 'bị trừ tiền 2 lần')",
    "human_agent": "Yêu cầu gặp trực tiếp nhân viên tư vấn người thật, kết nối tổng đài viên (ví dụ: 'cho tôi gặp nhân viên', 'talk to human agent')",
    "warranty": "Hỏi về chính sách, thời hạn, điều kiện bảo hành, sửa chữa hoặc bảo dưỡng sản phẩm (ví dụ: 'chính sách bảo hành sản phẩm điện tử', 'bảo hành máy hút bụi bao lâu', 'hàng này có được bảo hành không')",
    "get_discounts": "Hỏi về chương trình khuyến mãi, ưu đãi, voucher, mã giảm giá, coupon hoặc quà tặng, tích xu (ví dụ: 'có ưu đãi gì không', 'có mã giảm giá không')",
    "create_account": "Hỏi cách đăng ký, mở tài khoản thành viên hoặc tạo tài khoản mới trên sàn (ví dụ: 'tạo tài khoản mới thế nào', 'đăng ký thành viên mới')",
    "recover_password": "Hỏi cách khôi phục, lấy lại hoặc đổi mật khẩu đăng nhập khi quên mật khẩu (ví dụ: 'quên mật khẩu đăng nhập', 'tôi muốn đổi mật khẩu tài khoản')",
    "out_of_scope": "Các câu hỏi hoàn toàn KHÔNG liên quan đến thương mại điện tử, mua sắm hoặc CSKH (ví dụ: hỏi thời tiết, giải toán, thể thao, nấu ăn, chính trị, triết học)",
}

INTENT_SYSTEM_PROMPT = f"""Bạn là chuyên gia NLU phân loại ý định khách hàng (Intent Classification) cho sàn thương mại điện tử Tiki.

Hệ thống có 16 Ý ĐỊNH CHÍNH (TARGET_INTENTS) và `out_of_scope` sau:
{chr(10).join(f"- {name}: {desc}" for name, desc in INTENT_DESCRIPTIONS.items())}

QUY TẮC PHÂN LOẠI & PHẠM VI (SCOPE BOUNDARY):
1. Đọc kỹ câu hỏi khách hàng (hỗ trợ cả Tiếng Việt và Tiếng Anh).
2. TẤT CẢ câu hỏi liên quan đến mua sắm, đặt hàng, tài khoản, thanh toán, vận chuyển, đổi trả, bảo hành, voucher, CSKH trên sàn TMĐT ĐỀU LÀ IN-SCOPE và BẮT BUỘC gán vào 1 trong 16 intent nghiệp vụ ở trên:
   - Thắc mắc phương thức thanh toán (tiền mặt COD, thẻ, ví điện tử) -> gán `payment_issue`.
   - Hỏi về bảo hành, sửa chữa, bảo dưỡng sản phẩm -> gán `warranty`.
   - Hỏi tạo mới / đăng ký tài khoản -> gán `create_account`; quên / đổi / khôi phục mật khẩu -> gán `recover_password`.
   - Hỏi kiểm tra lại thông tin đơn, xuất hóa đơn VAT, giá đơn hàng -> gán `track_order`.
   - Yêu cầu gặp nhân viên, chuyển máy hỗ trợ -> BẮT BUỘC gán `human_agent`.
3. TUYỆT ĐỐI CHỈ DÙNG `out_of_scope` khi câu hỏi hoàn toàn không thuộc về mua sắm hay TMĐT (như thời tiết, giải toán, bóng đá, nấu ăn, thơ ca).
4. XỬ LÝ NGỮ CẢNH HỘI THOẠI:
   - Nếu câu hỏi bắt đầu bằng các thẻ ngữ cảnh hội thoại như `[PREV_INTENT: ...]`, `[ORDER: ...]`, `[AWAITING: ...]`, bạn PHẢI cân nhắc ngữ cảnh này.
   - Ví dụ: `[PREV_INTENT:track_order] [AWAITING:order_id] ORD-1003` -> Đây là câu bổ sung thông tin cho `track_order`.
   - Nếu khách đảo ý định: `[PREV_INTENT:cancel_order] thôi không hủy nữa, xem bao giờ giao` -> Intent chuyển sang `delivery_time`.

ĐỊNH DẠNG ĐẦU RA:
Trả về DUY NHẤT một khối JSON hợp lệ theo cấu trúc sau (không kèm markdown ngoài):
{{
  "intent": "<tên intent thuộc danh sách trên>",
  "confidence": <số thực từ 0.00 đến 1.00 phản ánh đúng mức độ chắc chắn; chỉ >= 0.85 khi rõ ràng, dưới 0.60 nếu câu hỏi mơ hồ hoặc thiếu ngữ cảnh>,
  "reasoning": "<lý do ngắn gọn>",
  "is_in_scope": <true nếu thuộc 16 intent, false nếu out_of_scope>,
  "probabilities": {{
    "<top_intent_1>": <xác suất>,
    "<top_intent_2>": <xác suất>
  }}
}}
"""


class LLMIntentClassifier:
    """Classifies customer intents via OpenAI-compatible CKEY.VN endpoint with offline fallback."""

    def __init__(self, api_key: Optional[str] = None, timeout: int = 20):
        self.api_key = api_key or OPENAI_API_KEY
        self.timeout = timeout

    def predict(self, query: str) -> IntentPredictionResponse:
        """Synchronously predict intent using OpenAI-compatible CKEY.VN endpoint with offline fallback."""
        start_time = time.perf_counter()
        clean_query = query.strip()

        try:
            result = self._call_openai_compatible(clean_query)
            if result:
                result.latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
                return result
        except Exception as exc:
            print(f"[LLMIntentClassifier] OpenAI-compatible call failed: {exc}")

        fallback_resp = self._semantic_fallback(clean_query)
        fallback_resp.latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return fallback_resp

    def _call_openai_compatible(self, query: str) -> Optional[IntentPredictionResponse]:
        """Call OpenAI-compatible chat completion for intent classification with multi-key failover."""
        if is_external_llm_disabled() or not get_available_api_keys():
            return None

        base_url = os.getenv("OPENAI_BASE_URL", OPENAI_BASE_URL).rstrip("/")
        model = os.getenv("OPENAI_MODEL", OPENAI_MODEL)

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": INTENT_SYSTEM_PROMPT},
                {"role": "user", "content": f'Phân loại câu hỏi sau:\n"{query}"'},
            ],
            "temperature": 0.1,
            "max_tokens": 350,
        }

        data = call_chat_completion_sync_with_failover(payload, base_url=base_url, timeout=self.timeout)
        if data:
            choices = data.get("choices", [])
            if choices:
                msg = choices[0].get("message", {})
                raw_text = (msg.get("content") or msg.get("reasoning_content") or "").strip()
                parsed = self._parse_json(raw_text)
                if parsed and "intent" in parsed:
                    intent = parsed["intent"]
                    if intent not in INTENT_DESCRIPTIONS:
                        intent = "out_of_scope"

                    try:
                        conf = max(0.0, min(1.0, float(parsed.get("confidence", 0.50))))
                    except (TypeError, ValueError):
                        conf = 0.0
                    is_in_scope = intent != OOS_LABEL and intent in TARGET_INTENTS
                    probs = parsed.get("probabilities", {intent: conf})

                    return IntentPredictionResponse(
                        intent=intent,
                        confidence=conf,
                        is_in_scope=is_in_scope,
                        language=(
                            "vi"
                            if re.search(
                                r"[àáảãạăắằẳẵặâấầẩẫậđèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵ]",
                                query.lower(),
                            )
                            else "en"
                        ),
                        model_name=model,
                        all_probabilities=probs,
                        latency_ms=0.0,
                    )
        return None

    def _parse_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Safely extract and parse JSON object from LLM response text."""
        try:
            return json.loads(text)
        except Exception:
            pass

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except Exception:
                pass

        match = re.search(r"\{.*?\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass

        return None

    def _semantic_fallback(self, query: str) -> IntentPredictionResponse:
        """Delegate offline semantic classification to OfflineIntentFallback."""
        return OfflineIntentFallback.classify(query)

    def _build_resp(
        self,
        intent: str,
        conf: float,
        query: str,
        is_in_scope: bool = True,
        model_name: str = "semantic_rule_fallback",
    ) -> IntentPredictionResponse:
        """Construct IntentPredictionResponse via OfflineIntentFallback."""
        return OfflineIntentFallback.build_response(
            intent, conf, query, is_in_scope=is_in_scope, model_name=model_name
        )
