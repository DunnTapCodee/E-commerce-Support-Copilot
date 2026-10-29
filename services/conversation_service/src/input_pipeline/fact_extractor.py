"""Fact and entity extractor for e-commerce customer conversations.
Inspired by VoiceAgent packs/public-service/facts.py.
"""
from __future__ import annotations

import re
from typing import Any, Dict


ORDER_RE = re.compile(r"\bORD-[A-Za-z0-9-]+\b", re.IGNORECASE)
LOOSE_ORDER_RE = re.compile(r"(?:đơn\s*(?:hàng)?\s*(?:số|mã)?\s*#?|(?:mã\s*đơn\s*#?))\s*(\d{4,6})\b", re.IGNORECASE)
DIGIT_ORDER_RE = re.compile(r"^\s*#?(\d{4,6})\s*$")
PHONE_RE = re.compile(r"\b(0[35789]\d{8})\b")
AMOUNT_RE = re.compile(r"\b(\d{1,3}(?:[.,]\d{3})*|\d+)\s*(?:k|đ|vnđ|vnd|dong|đồng)\b", re.IGNORECASE)
CARRIER_RE = re.compile(r"\b(tikinow|ghn|ghtk|viettel\s*post|ninja\s*van|j&t|shopee\s*express)\b", re.IGNORECASE)


def extract_facts(text: str) -> Dict[str, Any]:
    """Extract domain facts from customer utterance."""
    facts: Dict[str, Any] = {}

    order_match = ORDER_RE.search(text)
    if order_match:
        facts["order_id"] = order_match.group(0).upper()
    else:
        loose_match = LOOSE_ORDER_RE.search(text)
        if loose_match:
            facts["order_id"] = f"ORD-{loose_match.group(1)}"
        else:
            digit_match = DIGIT_ORDER_RE.search(text.strip())
            if digit_match:
                facts["order_id"] = f"ORD-{digit_match.group(1)}"

    phone_match = PHONE_RE.search(text)
    if phone_match:
        phone_val = phone_match.group(0)
        facts["phone"] = phone_val
        facts["phone_number"] = phone_val

    amount_match = AMOUNT_RE.search(text)
    if amount_match:
        facts["amount_str"] = amount_match.group(0)

    carrier_match = CARRIER_RE.search(text)
    if carrier_match:
        facts["carrier"] = carrier_match.group(0).upper()

    return facts
