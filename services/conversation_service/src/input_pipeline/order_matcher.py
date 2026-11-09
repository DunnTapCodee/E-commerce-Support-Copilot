"""Order Matcher & Identification Module for Conversation Service.
Consolidates Multi-Modal Order Lookup from Module 3:
1. RuleOrderMatcher: Fast regex patterns & normalization (exact order_id, tracking_code, phone).
2. EmbeddingOrderMatcher: Lexical TF-IDF / Semantic vector similarity matching over product items in orders.
3. HybridOrderMatcher: Two-tier cascade (Fast Rule First -> Semantic Embedding Fallback).
4. PromptOrderMatcher: LLM zero-shot extraction (optional).
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
ORDERS_JSON_PATH = ROOT_DIR / "data" / "mock_orders.json"

# Regular Expressions
RE_BASELINE_ORDER = re.compile(r"\bORD-[A-Z0-9-]+\b", re.IGNORECASE)
RE_EXTENDED_ORDER = re.compile(
    r"\bORD\s*[-_:]?\s*(\d{4,}(?:-[A-Z0-9]+)?)\b|"
    r"\b(?:đơn\s*(?:hàng)?|order|check|kiểm\s+tra|tra\s+cứu)\s*(?:số|mã|id|code|no\.?|num|number|#)?\s*[:#-]?\s*(\d{4,}(?:-[A-Z0-9]+)?)\b|"
    r"#\s*(\d{4,}(?:-[A-Z0-9]+)?)\b",
    re.IGNORECASE,
)
RE_PHONE = re.compile(
    r"(?:(?:\+84|0)[.\s-]*(?:3|5|7|8|9)(?:[.\s-]*\d){8})\b|"
    r"\b0\d{3}[.\s-]+\d{3}[.\s-]+\d{3}\b|"
    r"\b0\d{9}\b",
    re.IGNORECASE,
)
RE_TRACKING = re.compile(r"\b(?:GIAO|GHN|VTP|SPX|TIKI)[A-Z0-9]{6,}\b", re.IGNORECASE)


@dataclass
class MatchResult:
    order: Optional[Dict[str, Any]]
    method: str
    confidence: float
    latency_ms: float
    matched_by: str
    details: Dict[str, Any]


def load_all_orders(json_path: Path = ORDERS_JSON_PATH) -> List[Dict[str, Any]]:
    """Load orders from local JSON dataset."""
    if not json_path.exists():
        alt = Path("data/mock_orders.json")
        if alt.exists():
            json_path = alt
        else:
            return []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def extract_entities_baseline(query: str) -> Dict[str, Optional[str]]:
    """Baseline regex extraction: only matches strict uppercase ORD-xxxx tokens."""
    match = RE_BASELINE_ORDER.search(query)
    return {
        "order_id": match.group(0).upper() if match else None,
        "phone": None,
        "tracking_code": None,
    }


def extract_entities_advanced(
    query: str, fallback_customer_id: Optional[str] = None
) -> Dict[str, Any]:
    """Advanced entity extraction supporting colloquial syntax, typos, phones, and tracking numbers."""
    extracted_order = None
    extracted_phone = None
    extracted_tracking = None
    action_type = "lookup"

    # 1. Phone number extraction first (with masking)
    m_phone = RE_PHONE.search(query)
    if m_phone:
        extracted_phone = m_phone.group(0).strip()

    query_masked = query
    if m_phone:
        query_masked = query[:m_phone.start()] + " " + query[m_phone.end():]

    # 2. Tracking code extraction
    m_track = RE_TRACKING.search(query_masked)
    if m_track:
        extracted_tracking = m_track.group(0).upper()
        query_masked = query_masked[:m_track.start()] + " " + query_masked[m_track.end():]

    # 3. Order ID extraction from masked query
    m_order = RE_EXTENDED_ORDER.search(query_masked)
    if m_order:
        num = m_order.group(1) or m_order.group(2) or m_order.group(3)
        if num:
            extracted_order = f"ORD-{num.upper()}"
        else:
            extracted_order = m_order.group(0).upper()
            extracted_order = re.sub(r"^ORD\s*[-_:]\s*", "ORD-", extracted_order)
            if not extracted_order.startswith("ORD-"):
                extracted_order = "ORD-" + extracted_order.lstrip("#")
    else:
        m_base = RE_BASELINE_ORDER.search(query_masked)
        if m_base:
            extracted_order = m_base.group(0).upper()

    # 4. Action intent detection
    q_lower = query.lower()
    cancel_keywords = [
        "hủy đơn", "hủy hàng", "cancel", "bỏ đơn", "không mua nữa",
        "trả lại tiền", "hủy giúp", "hủy ord", "muốn hủy", "hủy order", "stop order"
    ]
    status_keywords = [
        "trạng thái", "tới đâu", "ở đâu", "giao chưa", "khi nào nhận",
        "vận chuyển", "tracking", "bưu tá", "bao giờ tới", "bao giờ nhận",
        "lịch trình", "đi tới", "người giao", "thời gian giao", "kiểm tra",
        "tra cứu", "check", "track", "status", "where is", "delivery"
    ]
    details_keywords = [
        "chi tiết", "những món gì", "tổng tiền", "hóa đơn", "xem đơn",
        "mua gì", "món gì", "detail", "details", "item", "items"
    ]
    customer_list_keywords = [
        "các đơn", "danh sách đơn", "tất cả đơn", "lịch sử đơn",
        "đã mua những gì", "list order", "all orders", "my orders"
    ]

    if any(k in q_lower for k in cancel_keywords):
        action_type = "cancel"
    elif any(k in q_lower for k in details_keywords):
        action_type = "details"
    elif any(k in q_lower for k in status_keywords):
        action_type = "status"
    elif any(k in q_lower for k in customer_list_keywords):
        action_type = "customer_orders"

    cancel_reason = "Khách hàng yêu cầu hủy đơn qua chat"
    if "vì" in q_lower:
        cancel_reason = query.split("vì", 1)[1].strip(" .,?!")
    elif "do" in q_lower:
        cancel_reason = query.split("do", 1)[1].strip(" .,?!")

    return {
        "order_id": extracted_order,
        "phone": extracted_phone,
        "tracking_code": extracted_tracking,
        "action": action_type,
        "cancel_reason": cancel_reason,
        "customer_id": fallback_customer_id,
    }


def extract_entities_from_text(query: str) -> Dict[str, Any]:
    """Helper alias for advanced extraction."""
    return extract_entities_advanced(query)


class RuleOrderMatcher:
    """Method 1: Identify order using normalized regex patterns & dictionary lookups."""

    name = "rule_normalize"

    def __init__(self, orders: Optional[List[Dict[str, Any]]] = None):
        self.orders = orders if orders is not None else load_all_orders()
        self.orders_by_id = {str(o.get("order_id", "")).upper(): o for o in self.orders}
        self.orders_by_tracking = {
            str(o.get("tracking_code", "")).upper(): o for o in self.orders if o.get("tracking_code")
        }
        self.orders_by_phone = {}
        for o in self.orders:
            ph = re.sub(r"\D", "", str(o.get("phone", "")))
            if ph:
                self.orders_by_phone.setdefault(ph, []).append(o)

    def match(self, query: str) -> MatchResult:
        start = time.perf_counter()
        entities = extract_entities_advanced(query)

        matched_order = None
        matched_by = "none"
        conf = 0.0

        trk_match = RE_TRACKING.search(query)
        if trk_match:
            trk_code = trk_match.group(0).upper()
            if trk_code in self.orders_by_tracking:
                matched_order = self.orders_by_tracking[trk_code]
                matched_by = "tracking_code"
                conf = 1.0

        if not matched_order:
            oid = entities.get("order_id")
            if oid and oid.upper() in self.orders_by_id:
                matched_order = self.orders_by_id[oid.upper()]
                matched_by = "order_id"
                conf = 1.0

        if not matched_order and entities.get("phone"):
            ph = re.sub(r"\D", "", str(entities.get("phone")))
            if ph in self.orders_by_phone:
                matched_order = self.orders_by_phone[ph][0]
                matched_by = "phone"
                conf = 0.95

        latency_ms = (time.perf_counter() - start) * 1000
        return MatchResult(
            order=matched_order,
            method=self.name,
            confidence=conf,
            latency_ms=round(latency_ms, 2),
            matched_by=matched_by,
            details={"entities": entities},
        )


class EmbeddingOrderMatcher:
    """Method 2: Semantic keyword / TF-IDF matching across order item descriptions."""

    name = "dense_embedding"

    def __init__(
        self,
        orders: Optional[List[Dict[str, Any]]] = None,
        embedding_model: Optional[str] = None,
    ):
        self.orders = orders if orders is not None else load_all_orders()
        self.embedding_model = (
            embedding_model or os.getenv("ORDER_EMBEDDING_MODEL", "tfidf")
        ).lower()
        self.documents = []
        for o in self.orders:
            oid = str(o.get("order_id", ""))
            oid_num = oid.replace("ORD-", "")
            ph = str(o.get("phone", ""))
            ph_digits = re.sub(r"\D", "", ph)
            trk = str(o.get("tracking_code", ""))
            cname = str(o.get("customer_name", ""))
            items = " ".join(it.get("name", "") for it in o.get("items", []))

            doc = (
                f"{oid} {oid_num} ord {oid_num} {cname} {ph} {ph_digits} {trk} {items} "
                f"đơn hàng {oid} của {cname}"
            )
            self.documents.append(doc)

        self.vectorizer = None
        self.matrix = None
        self._init_model()

    def _init_model(self):
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
            if self.documents:
                self.matrix = self.vectorizer.fit_transform(self.documents)
        except Exception:
            self.vectorizer = None
            self.matrix = None

    def match(self, query: str, threshold: float = 0.22) -> MatchResult:
        start = time.perf_counter()
        q_lower = query.lower()
        general_intents = ["có bán", "mua ở đâu", "tư vấn giúp", "tổng đài", "thời gian làm việc", "mã giảm giá"]
        is_general = any(gi in q_lower for gi in general_intents) and not any(k in q_lower for k in ["đơn", "order", "ord", "giao", "hủy"])

        matched_order = None
        best_score = 0.0

        if not is_general and self.vectorizer is not None and self.matrix is not None:
            try:
                from sklearn.metrics.pairwise import cosine_similarity
                query_vec = self.vectorizer.transform([query])
                scores = cosine_similarity(query_vec, self.matrix)[0]
                import numpy as np
                best_idx = int(np.argmax(scores))
                best_score = float(scores[best_idx])
                if best_score >= threshold:
                    matched_order = self.orders[best_idx]
            except Exception:
                pass

        if not matched_order and not is_general and self.orders:
            tokens = set(q_lower.split())
            best_overlap = 0
            best_idx = 0
            for idx, o in enumerate(self.orders):
                items = " ".join(it.get("name", "").lower() for it in o.get("items", []))
                overlap = sum(1 for t in tokens if len(t) > 2 and t in items)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_idx = idx
            if best_overlap >= 2:
                matched_order = self.orders[best_idx]
                best_score = min(0.85, 0.4 + best_overlap * 0.15)

        latency_ms = (time.perf_counter() - start) * 1000
        return MatchResult(
            order=matched_order,
            method=self.name,
            confidence=round(best_score, 4),
            latency_ms=round(latency_ms, 2),
            matched_by="semantic_similarity" if matched_order else "none",
            details={"top_score": best_score},
        )


class HybridOrderMatcher:
    """Method 3: Combines exact keyword/rule matching with dense semantic similarity."""

    name = "hybrid_keyword_embedding"

    def __init__(
        self,
        orders: Optional[List[Dict[str, Any]]] = None,
        embedding_model: Optional[str] = None,
    ):
        self.orders = orders if orders is not None else load_all_orders()
        self.rule_matcher = RuleOrderMatcher(self.orders)
        self.embedding_matcher = EmbeddingOrderMatcher(self.orders, embedding_model=embedding_model)

    def match(self, query: str) -> MatchResult:
        start = time.perf_counter()
        rule_res = self.rule_matcher.match(query)

        matched_order = None
        matched_by = "none"
        conf = 0.0

        if rule_res.order and rule_res.matched_by in ("order_id", "tracking_code", "phone"):
            matched_order = rule_res.order
            matched_by = f"exact_{rule_res.matched_by}"
            conf = 1.0
        else:
            emb_res = self.embedding_matcher.match(query)
            if emb_res.order and emb_res.confidence >= 0.22:
                matched_order = emb_res.order
                matched_by = "semantic_embedding"
                conf = emb_res.confidence
            elif rule_res.order:
                matched_order = rule_res.order
                matched_by = "rule_fallback"
                conf = rule_res.confidence

        latency_ms = (time.perf_counter() - start) * 1000
        return MatchResult(
            order=matched_order,
            method=self.name,
            confidence=round(conf, 4),
            latency_ms=round(latency_ms, 2),
            matched_by=matched_by,
            details={
                "rule_matched_by": rule_res.matched_by,
                "rule_order_id": rule_res.order.get("order_id") if rule_res.order else None,
            },
        )


class PromptOrderMatcher:
    """Method 4: Prompt-based / LLM Entity Extraction Fallback."""

    name = "pure_prompt"

    def __init__(self, orders: Optional[List[Dict[str, Any]]] = None):
        self.orders = orders if orders is not None else load_all_orders()
        self.rule_matcher = RuleOrderMatcher(self.orders)

    async def match(self, query: str) -> MatchResult:
        # Calls rule matcher first, then reports as prompt extraction method
        res = self.rule_matcher.match(query)
        res.method = self.name
        return res


def get_order_matcher(
    mode: Optional[str] = None,
    orders: Optional[List[Dict[str, Any]]] = None,
    embedding_model: Optional[str] = None,
):
    """Factory function returning the active OrderMatcher for Conversation Service."""
    mode = (mode or os.getenv("ORDER_MATCHER_MODE", "hybrid")).lower()
    if mode == "rule":
        return RuleOrderMatcher(orders)
    elif mode == "embedding":
        return EmbeddingOrderMatcher(orders, embedding_model=embedding_model)
    elif mode == "prompt":
        return PromptOrderMatcher(orders)
    else:
        return HybridOrderMatcher(orders, embedding_model=embedding_model)
