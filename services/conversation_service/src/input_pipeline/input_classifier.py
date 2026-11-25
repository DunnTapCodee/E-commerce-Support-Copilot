"""LLM-Primary Structured Utterance Classifier.

Online mode (`not is_external_llm_disabled()` with API keys) delegates utterance
classification directly to the LLM without keyword/regex pre-interception.
All offline deterministic rules live in `offline_fallback.py` (`OfflineInputFallback`).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, Tuple

from contracts.llm_failover import (
    call_chat_completion_with_failover,
    get_available_api_keys,
    is_external_llm_disabled,
)
from services.conversation_service.src.config import LLM_PROVIDER, OPENAI_API_KEY, OPENAI_MODEL
from services.conversation_service.src.input_pipeline.fact_extractor import extract_facts
from services.conversation_service.src.input_pipeline.offline_fallback import (
    InputCategory,
    OfflineInputFallback,
)


class InputClassifier:
    """LLM-Primary Utterance Classifier delegating offline/error fallback to OfflineInputFallback."""

    def __init__(self, api_key: Optional[str] = None):
        self.openai_key = api_key or OPENAI_API_KEY
        self.provider = LLM_PROVIDER

    def classify_fast_tier(
        self,
        text: str,
        facts: Dict[str, Any],
        active_intent: Optional[str] = None,
    ) -> Optional[InputCategory]:
        """Thin wrapper delegating deterministic offline classification to OfflineInputFallback."""
        return OfflineInputFallback.classify(text, facts, active_intent=active_intent)

    async def classify_utterance(
        self,
        text: str,
        active_intent: Optional[str] = None,
        context_summary: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> Tuple[InputCategory, Dict[str, Any], float]:
        """LLM-primary classification; offline fallback runs ONLY when LLM is unavailable or fails."""
        extracted = extract_facts(text, customer_id=customer_id)
        if not text.strip():
            return "chitchat", extracted, 1.0

        if not is_external_llm_disabled() and get_available_api_keys():
            prompt = self._build_prompt(text, active_intent, context_summary)
            try:
                res = await self._classify_with_openai_compatible(prompt)
                if res:
                    category, llm_facts, conf = res
                    extracted.update(llm_facts)
                    return category, extracted, conf
            except Exception:
                pass

        fallback_cat = self.classify_fast_tier(text, extracted, active_intent=active_intent)
        if fallback_cat:
            return fallback_cat, extracted, 0.90

        return "new_question", extracted, 0.85

    def _build_prompt(self, text: str, active_intent: Optional[str], context_summary: Optional[str]) -> str:
        return f"""Bạn là bộ phân loại câu hội thoại NLU cho trợ lý CSKH E-commerce Tiki.
Hãy phân loại tin nhắn của khách hàng vào ĐÚNG 1 TRONG 4 LOẠI:
1. "chitchat": Chỉ đơn thuần là lời chào, cảm ơn, xác nhận hoặc tạm biệt xã giao (không chứa câu hỏi hay yêu cầu nghiệp vụ).
2. "fact_supplement": Khách hàng chỉ bổ sung thông tin còn thiếu (mã đơn hàng, số điện thoại, địa chỉ, màu sắc, kích cỡ) cho yêu cầu đang trao đổi trước đó.
3. "negation_reversal": Khách hàng thay đổi ý định, phủ định hoặc hủy bỏ yêu cầu vừa đưa ra trước đó để chuyển sang yêu cầu khác.
4. "new_question": Khách hàng đặt câu hỏi mới, tra cứu chính sách, hỏi về đơn hàng, khiếu nại hoặc yêu cầu hỗ trợ mới (bao gồm cả câu vừa chào hỏi vừa đặt câu hỏi).

NGỮ CẢNH TRƯỚC ĐÓ:
- Ý định đang xử lý: {active_intent or 'Chưa có'}
- Tóm tắt bối cảnh: {context_summary or 'Chưa có'}

CÂU NÓI HIỆN TẠI CỦA KHÁCH:
"{text}"

Trả về DUY NHẤT một JSON hợp lệ:
{{"input_type": "chitchat" | "fact_supplement" | "negation_reversal" | "new_question", "order_id": "ORD-XXXX hoặc null", "confidence": 0.95}}"""

    async def _classify_with_openai_compatible(
        self, prompt: str
    ) -> Optional[Tuple[InputCategory, Dict[str, Any], float]]:
        payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": "Bạn là chuyên gia phân loại câu hội thoại CSKH Tiki. Trả về DUY NHẤT một JSON hợp lệ.",
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.0,
            "max_tokens": 150,
        }
        res_data = await call_chat_completion_with_failover(payload, timeout=10.0)
        if res_data and "choices" in res_data and res_data["choices"]:
            msg = res_data["choices"][0].get("message", {})
            raw_text = (msg.get("content") or msg.get("reasoning_content") or "").strip()
            return self._parse_json_result(raw_text)
        return None

    def _parse_json_result(self, raw_text: str) -> Optional[Tuple[InputCategory, Dict[str, Any], float]]:
        if not raw_text:
            return None
        match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not match:
            return None
        try:
            parsed = json.loads(match.group(0))
        except Exception:
            return None
        category = parsed.get("input_type", "new_question")
        if category not in {"chitchat", "fact_supplement", "negation_reversal", "new_question"}:
            category = "new_question"
        llm_facts: Dict[str, Any] = {}
        if parsed.get("order_id"):
            llm_facts["order_id"] = str(parsed["order_id"]).upper()
        conf = float(parsed.get("confidence", 0.90))
        return category, llm_facts, conf
