"""2-tier input classifier: Fast Rule/Lexicon Engine + LLM Structured Classifier.
Inspired by VoiceAgent packs/public-service/new_policy.py.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any, Dict, Literal, Optional, Tuple
import httpx
from pydantic import BaseModel

from services.conversation_service.src.config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    LLM_PROVIDER,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)
from services.conversation_service.src.input_pipeline.fact_extractor import extract_facts

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


InputCategory = Literal["chitchat", "fact_supplement", "negation_reversal", "new_question"]


# Fast lexicons for Tier 1
_CHITCHAT_EXACT = frozenset({
    "ok", "oke", "okie", "da", "dạ", "vang", "vâng", "vâng ạ", "vang a", "da vang", "dạ vâng",
    "cam on", "cảm ơn", "cam on shop", "cảm ơn shop", "thanks", "thank you", "cảm ơn bạn",
    "chao shop", "chào shop", "alo", "ad oi", "ad ơi", "hi", "hello", "hi shop", "hello shop",
    "dung roi", "đúng rồi", "chuan roi", "chuẩn rồi", "dong y", "đồng ý", "uhm", "ừ", "u", "uh", "helllllo", "helo"
})

_NEGATION_PATTERNS = [
    re.compile(r"\b(?:thôi\s+không|thoi\s+khong|đổi\s+ý|doi\s+y|không\s+muốn\s+hủy|khong\s+muon\s+huy|không\s+hủy\s+nữa|khoan\s+đã|thôi\s+khỏi)\b", re.IGNORECASE),
]

_QUESTION_PATTERNS = [
    re.compile(r"(?:\?|gì|sao|thế nào|như nào|ở đâu|khi nào|bao giờ|bao lâu|mấy ngày|kiểm tra|tra cứu|hỏi|xem|đơn hàng|đơn|hàng|hủy|đổi|trả|hoàn tiền|ship|phí|bảo hành|voucher|mã|thanh toán|tiền|giao|nhận|mua|chính sách|quy định)", re.IGNORECASE),
]


class InputClassifier:
    """Ultra-fast Hybrid Classifier combining instant rules (< 0.1ms) with LLM Classifier (openai-gpt-oss-20b)."""

    def __init__(self, gemini_api_key: Optional[str] = None):
        self.api_key = gemini_api_key or GEMINI_API_KEY
        self.openai_key = OPENAI_API_KEY
        self.provider = LLM_PROVIDER

    def classify_fast_tier(self, text: str, facts: Dict[str, Any]) -> Optional[InputCategory]:
        """Tier 1: Fast Rule / Lexicon evaluation (< 0.1ms)."""
        cleaned = text.strip().lower()
        cleaned = re.sub(r"[^\w\s-]", "", cleaned).strip()

        # 1. Exact chitchat / courtesy match
        if cleaned in _CHITCHAT_EXACT:
            return "chitchat"

        # Compound courtesies
        if len(cleaned.split()) <= 6:
            courtesy_tokens = {
                "da", "dạ", "vang", "vâng", "a", "ạ", "cam", "on", "cảm", "ơn",
                "shop", "ban", "bạn", "nhe", "nhé", "ok", "oke", "okie", "thanks",
                "thank", "you", "chao", "chào", "ad", "oi", "ơi", "hi", "hello"
            }
            tokens = set(cleaned.split())
            if tokens and tokens.issubset(courtesy_tokens):
                return "chitchat"

        # 2. Pure fact input
        words = text.strip().split()
        if len(words) <= 4 and ("order_id" in facts or "phone" in facts or "phone_number" in facts):
            return "fact_supplement"

        # 3. Negation reversal cues
        for pat in _NEGATION_PATTERNS:
            if pat.search(text):
                return "negation_reversal"

        # 4. Fast Question / Inquiry heuristic detection (< 0.1ms)
        for pat in _QUESTION_PATTERNS:
            if pat.search(text):
                return "new_question"

        if len(words) >= 4:
            return "new_question"

        return None

    async def classify_utterance(
        self,
        text: str,
        active_intent: Optional[str] = None,
        context_summary: Optional[str] = None,
    ) -> Tuple[InputCategory, Dict[str, Any], float]:
        """Full hybrid classification: Tier 1 -> Tier 2 (LLM)."""
        extracted = extract_facts(text)
        fast_category = self.classify_fast_tier(text, extracted)
        if fast_category:
            return fast_category, extracted, 0.95

        # Tier 2: LLM Structured Output
        prompt = self._build_prompt(text, active_intent, context_summary)

        # 1. Try OpenAI-compatible (openai-gpt-oss-20b)
        if self.openai_key:
            try:
                res = await self._classify_with_openai_compatible(prompt)
                if res:
                    category, llm_facts, conf = res
                    extracted.update(llm_facts)
                    return category, extracted, conf
            except Exception:
                pass

        return "new_question", extracted, 0.85

    def _build_prompt(self, text: str, active_intent: Optional[str], context_summary: Optional[str]) -> str:
        return f"""Bạn là bộ phân loại câu hội thoại cho trợ lý CSKH E-commerce.
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

    async def _classify_with_openai_compatible(
        self, prompt: str
    ) -> Optional[Tuple[InputCategory, Dict[str, Any], float]]:
        url = f"{OPENAI_BASE_URL}/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.openai_key}",
        }
        payload = {
            "model": OPENAI_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.0,
            "max_tokens": 600,
        }
        async with httpx.AsyncClient(timeout=6.0) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                msg = resp.json()["choices"][0]["message"]
                raw_text = msg.get("content", "").strip()
                if not raw_text:
                    raw_text = msg.get("reasoning_content", "").strip()
                return self._parse_json_result(raw_text)
        return None

    def _parse_json_result(self, raw_text: str) -> Optional[Tuple[InputCategory, Dict[str, Any], float]]:
        if not raw_text:
            return None
        raw_text = re.sub(r"^```(?:json)?", "", raw_text).strip()
        raw_text = re.sub(r"```$", "", raw_text).strip()
        try:
            parsed = json.loads(raw_text)
        except Exception:
            return None
        category = parsed.get("input_type", "new_question")
        if category not in {"chitchat", "fact_supplement", "negation_reversal", "new_question"}:
            category = "new_question"
        llm_facts = {}
        if parsed.get("order_id"):
            llm_facts["order_id"] = str(parsed["order_id"]).upper()
        conf = float(parsed.get("confidence", 0.90))
        return category, llm_facts, conf
