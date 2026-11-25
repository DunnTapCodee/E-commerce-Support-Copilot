"""Offline / LLM-Unavailable Deterministic Input Classification Fallback.

Isolated from `input_classifier.py` so rule-based lexicons and regexes only run
when live LLM inference is disabled, unconfigured, or unreachable.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Literal, Optional

InputCategory = Literal["chitchat", "fact_supplement", "negation_reversal", "new_question"]

_OFFLINE_CHITCHAT_EXACT = frozenset({
    "ok", "oke", "okie", "oki", "da", "dạ", "vang", "vâng", "vâng ạ", "vang a", "da vang", "dạ vâng",
    "cam on", "cảm ơn", "cam on shop", "cảm ơn shop", "thanks", "thank you", "cảm ơn bạn", "cảm ơn b", "cam on b",
    "cảm ơn em", "cam on em", "cảm ơn ad",
    "chao shop", "chào shop", "chao b", "chào b", "chao ban", "chào bạn", "chao", "chào", "chào nha", "chao nha",
    "chào em", "chao em",
    "alo", "alo b", "ad oi", "ad ơi", "hi", "hi b", "hello", "hello b", "hi shop", "hello shop",
    "dung roi", "đúng rồi", "chuan roi", "chuẩn rồi", "dong y", "đồng ý", "uhm", "ừ", "u", "uh", "helllllo", "helo",
    "the a", "thế à", "the ha", "thế hả", "vay a", "vậy à", "vay ha", "vậy hả", "vay sao", "vậy sao",
    "the sao", "thế sao", "o vay a", "ồ vậy à", "tam biet", "tạm biệt", "bye",
})

_OFFLINE_COURTESY_TOKENS = frozenset({
    "da", "dạ", "vang", "vâng", "a", "ạ", "cam", "on", "cảm", "ơn", "em", "anh", "chị",
    "shop", "ban", "bạn", "b", "c", "e", "nha", "nhe", "nhé", "ok", "oke", "okie", "oki",
    "thanks", "thank", "you", "chao", "chào", "ad", "oi", "ơi", "hi", "hello", "nhiều", "nhieu",
})

_OFFLINE_NEGATION_RE = re.compile(
    r"\b(?:thôi\s+không|thoi\s+khong|đổi\s+ý|doi\s+y|không\s+muốn\s+hủy|khong\s+muon\s+huy|"
    r"không\s+hủy\s+nữa|khong\s+huy\s+nua|khoan\s+đã|khoan\s+hãy|thôi\s+khỏi)\b",
    re.IGNORECASE,
)

_OFFLINE_INTERROGATIVE_RE = re.compile(
    r"(?:\?|"
    r"\b(?:gì|sao|thế\s+nào|như\s+thế\s+nào|như\s+nào|ra\s+sao|ở\s+đâu|đến\s+đâu|tới\s+đâu|"
    r"khi\s+nào|bao\s+giờ|bao\s+lâu|mấy\s+ngày|bao\s+nhiêu|tại\s+sao|vì\s+sao|làm\s+sao|"
    r"được\s+không|có\s+được|phải\s+không|chưa\s+ạ|chưa\s+shop|chưa\s+vậy|"
    r"kiểm\s+tra|tra\s+cứu|cho\s+hỏi|cho\s+mình\s+hỏi|cho\s+tôi\s+hỏi|tư\s+vấn|"
    r"what|where|when|why|how|can\s+i|could\s+you)\b)",
    re.IGNORECASE,
)


class OfflineInputFallback:
    """Deterministic linguistic fallback for utterance classification when LLM is unavailable."""

    @classmethod
    def classify(
        cls,
        text: str,
        facts: Dict[str, Any],
        active_intent: Optional[str] = None,
    ) -> Optional[InputCategory]:
        """Classify utterance using deterministic rules strictly for offline/fallback execution."""
        raw = text.strip()
        if not raw:
            return "chitchat"

        cleaned = " ".join(re.sub(r"[^\w\s-]", " ", raw.lower()).split())
        words = cleaned.split()

        if _OFFLINE_NEGATION_RE.search(raw):
            return "negation_reversal"

        has_question = bool(_OFFLINE_INTERROGATIVE_RE.search(raw))
        has_extracted_entity = any(k in facts for k in ("order_id", "phone", "phone_number", "carrier"))

        if not has_extracted_entity and not has_question:
            if cleaned in _OFFLINE_CHITCHAT_EXACT:
                return "chitchat"
            if len(words) <= 6 and words and set(words).issubset(_OFFLINE_COURTESY_TOKENS):
                return "chitchat"

        if not has_question and has_extracted_entity and len(words) <= 12:
            return "fact_supplement"

        if has_question:
            return "new_question"

        if active_intent and len(words) <= 6:
            return "fact_supplement"

        return None
