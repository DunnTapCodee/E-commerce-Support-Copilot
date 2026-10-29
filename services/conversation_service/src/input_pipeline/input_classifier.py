"""2-tier input classifier: Fast Rule/Lexicon Engine + LLM Structured Classifier.
Inspired by VoiceAgent packs/public-service/new_policy.py.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Literal, Optional, Tuple
import httpx
from pydantic import BaseModel

from services.conversation_service.src.config import GEMINI_API_KEY, GEMINI_MODEL
from services.conversation_service.src.input_pipeline.fact_extractor import extract_facts

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


InputCategory = Literal["chitchat", "fact_supplement", "negation_reversal", "new_question"]


# Fast lexicons for Tier 1
_CHITCHAT_EXACT = frozenset({
    "ok", "oke", "okie", "da", "dạ", "vang", "vâng", "vâng ạ", "vang a", "da vang", "dạ vâng",
    "cam on", "cảm ơn", "cam on shop", "cảm ơn shop", "thanks", "thank you", "cảm ơn bạn",
    "chao shop", "chào shop", "alo", "ad oi", "ad ơi", "hi", "hello", "hi shop", "hello shop",
    "dung roi", "đúng rồi", "chuan roi", "chuẩn rồi", "dong y", "đồng ý", "uhm", "ừ", "u", "uh"
})

_NEGATION_PATTERNS = [
    re.compile(r"\b(?:thôi\s+không|thoi\s+khong|đổi\s+ý|doi\s+y|không\s+muốn\s+hủy|khong\s+muon\s+huy|không\s+hủy\s+nữa|khoan\s+đã|thôi\s+khỏi)\b", re.IGNORECASE),
]


class InputClassifier:
    """Hybrid Classifier combining instant regex (< 1ms) with Gemini 2.5 Flash (~300ms)."""

    def __init__(self, gemini_api_key: Optional[str] = None):
        self.api_key = gemini_api_key or GEMINI_API_KEY

    def classify_fast_tier(self, text: str, facts: Dict[str, Any]) -> Optional[InputCategory]:
        """Tier 1: Fast Rule / Lexicon evaluation."""
        cleaned = text.strip().lower()
        cleaned = re.sub(r"[^\w\s-]", "", cleaned).strip()

        # 1. Exact chitchat / courtesy match
        if cleaned in _CHITCHAT_EXACT:
            return "chitchat"

        # Compound courtesies (e.g. "dạ vâng cảm ơn shop", "vâng cảm ơn bạn", "ok cảm ơn nhé")
        if len(cleaned.split()) <= 6:
            courtesy_tokens = {
                "da", "dạ", "vang", "vâng", "a", "ạ", "cam", "on", "cảm", "ơn",
                "shop", "ban", "bạn", "nhe", "nhé", "ok", "oke", "okie", "thanks",
                "thank", "you", "chao", "chào", "ad", "oi", "ơi"
            }
            tokens = set(cleaned.split())
            if tokens and tokens.issubset(courtesy_tokens):
                return "chitchat"

        # 2. Pure fact input (e.g. customer sends just 'ORD-1003' or phone number)
        words = text.strip().split()
        if len(words) <= 3 and ("order_id" in facts or "phone" in facts):
            return "fact_supplement"

        # 3. Negation reversal cues
        for pat in _NEGATION_PATTERNS:
            if pat.search(text):
                return "negation_reversal"

        return None

    async def classify_utterance(
        self,
        text: str,
        active_intent: Optional[str] = None,
        context_summary: Optional[str] = None,
    ) -> Tuple[InputCategory, Dict[str, Any], float]:
        """Full hybrid classification: Tier 1 -> Tier 2 (LLM).
        Returns (category, extracted_facts, confidence).
        """
        extracted = extract_facts(text)
        fast_category = self.classify_fast_tier(text, extracted)
        if fast_category:
            return fast_category, extracted, 0.95

        # If length is long and has question cues, default to new_question
        if not self.api_key:
            return "new_question", extracted, 0.85

        # Tier 2: LLM Structured Output with Gemini Flash
        try:
            category, llm_facts, conf = await self._classify_with_gemini(text, active_intent, context_summary)
            extracted.update(llm_facts)
            return category, extracted, conf
        except Exception:
            return "new_question", extracted, 0.75

    async def _classify_with_gemini(
        self,
        text: str,
        active_intent: Optional[str],
        context_summary: Optional[str],
    ) -> Tuple[InputCategory, Dict[str, Any], float]:
        """Send concise context to Gemini 2.5 Flash for structured categorization."""
        prompt = f"""Bạn là bộ phân loại câu hội thoại cho trợ lý CSKH E-commerce.
Hãy phân tích tin nhắn của khách hàng và phân loại vào ĐÚNG 1 TRONG 4 LOẠI:
- "chitchat": Câu chào hỏi, cảm ơn, xã giao (ví dụ: "chào bạn", "cảm ơn nhiều nhé").
- "fact_supplement": Câu bổ sung mã đơn hàng, số điện thoại, chi tiết sản phẩm cho ý định trước đó mà không có ý định mới.
- "negation_reversal": Khách quay xe, đổi ý, phủ định ý định cũ (ví dụ: "thôi không hủy đơn nữa, xem bao giờ giao hộ tôi").
- "new_question": Khách hỏi một câu hỏi hoặc khiếu nại mới hoàn toàn.

NGỮ CẢNH TRƯỚC:
- Intent đang xử lý: {active_intent or 'Chưa có'}
- Tóm tắt bối cảnh: {context_summary or 'Chưa có'}

CÂU NÓI HIỆN TẠI CỦA KHÁCH:
"{text}"

YÊU CẦU: Trả về JSON hợp lệ theo định dạng:
{{"input_type": "...", "order_id": "...", "confidence": 0.95}}
Chỉ trả về JSON thuần túy, không thêm markdown.
"""
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.0,
                "maxOutputTokens": 500,
                "thinkingConfig": {
                    "thinkingBudget": 0
                },
            }
        }

        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                # Clean code blocks if returned
                raw_text = re.sub(r"^```(?:json)?", "", raw_text).strip()
                raw_text = re.sub(r"```$", "", raw_text).strip()
                import json
                parsed = json.loads(raw_text)
                category = parsed.get("input_type", "new_question")
                if category not in {"chitchat", "fact_supplement", "negation_reversal", "new_question"}:
                    category = "new_question"
                llm_facts = {}
                if parsed.get("order_id"):
                    llm_facts["order_id"] = parsed["order_id"].upper()
                conf = float(parsed.get("confidence", 0.90))
                return category, llm_facts, conf

        return "new_question", {}, 0.80
