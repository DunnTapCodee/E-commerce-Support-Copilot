"""Four Distinct Approaches for Order Identification and Retrieval in Module 3.

Approaches:
1. PromptOrderMatcher: Pure LLM prompt zero-shot entity extraction & DB lookup
2. RuleOrderMatcher: Rule-based regex & text normalization
3. EmbeddingOrderMatcher: Dense semantic vector similarity matching on order profiles
4. HybridOrderMatcher: Cascade / Fusion of Keyword rules + Dense embedding matching
"""
from __future__ import annotations

import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from services.gateway.src.agent import extract_entities_advanced

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
ORDERS_JSON_PATH = ROOT_DIR / "data" / "mock_orders.json"


@dataclass
class MatchResult:
    order: Optional[Dict[str, Any]]
    method: str
    confidence: float
    latency_ms: float
    matched_by: str
    details: Dict[str, Any]


def load_all_orders(json_path: Path = ORDERS_JSON_PATH) -> List[Dict[str, Any]]:
    """Load all orders from JSON file."""
    if not json_path.exists():
        return []
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


# =====================================================================
# Bản 1: Pure Prompt (LLM Zero-Shot Entity Extraction)
# =====================================================================
class PromptOrderMatcher:
    """Method 1: Identify order by querying LLM with prompt to extract entities, then DB query."""

    name = "pure_prompt"

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

    async def match(self, query: str) -> MatchResult:
        """Call Gemini to extract order entities, then look up."""
        import httpx
        start = time.perf_counter()

        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY") or ""
        model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

        entities = {}
        if api_key and not api_key.startswith("your_"):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            prompt = (
                "Bạn là AI bóc tách thông tin đơn hàng thương mại điện tử Tiki. "
                "Từ câu của người dùng, trích xuất DUY NHẤT một JSON hợp lệ: "
                "{\"order_id\": string hoặc null (chuẩn hóa dạng ORD-XXXX, ví dụ 1003 -> ORD-1003), "
                "\"phone\": string hoặc null (chuẩn hóa chuỗi số liền), "
                "\"tracking_code\": string hoặc null (ví dụ GIAO..., GHN..., TIKI...), "
                "\"customer_name\": string hoặc null, "
                "\"product_keyword\": string hoặc null (tên món hàng nếu có)}"
            )
            payload = {
                "contents": [{"parts": [{"text": f"{prompt}\n\nCâu của khách: \"{query}\""}]}],
                "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"}
            }
            try:
                async with httpx.AsyncClient(timeout=8.0, verify=False) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        entities = json.loads(text)
            except Exception:
                pass

        matched_order = None
        matched_by = "none"
        conf = 0.0

        # 1. Match by order_id
        oid = entities.get("order_id")
        if oid and oid.upper() in self.orders_by_id:
            matched_order = self.orders_by_id[oid.upper()]
            matched_by = "order_id"
            conf = 1.0

        # 2. Match by tracking_code
        if not matched_order and entities.get("tracking_code"):
            trk = str(entities.get("tracking_code")).upper().strip()
            if trk in self.orders_by_tracking:
                matched_order = self.orders_by_tracking[trk]
                matched_by = "tracking_code"
                conf = 1.0

        # 3. Match by phone
        if not matched_order and entities.get("phone"):
            ph = re.sub(r"\D", "", str(entities.get("phone")))
            if ph in self.orders_by_phone:
                matched_order = self.orders_by_phone[ph][0]
                matched_by = "phone"
                conf = 0.95

        # 4. Match by customer name or product keyword
        if not matched_order:
            cname = (entities.get("customer_name") or "").lower().strip()
            kw = (entities.get("product_keyword") or "").lower().strip()
            for o in self.orders:
                cust = o.get("customer_name", "").lower()
                if cname and cname in cust:
                    matched_order = o
                    matched_by = "customer_name"
                    conf = 0.90
                    break
                for item in o.get("items", []):
                    iname = item.get("name", "").lower()
                    if kw and (kw in iname or iname in kw):
                        matched_order = o
                        matched_by = "product_keyword"
                        conf = 0.85
                        break
                if matched_order:
                    break

        latency_ms = (time.perf_counter() - start) * 1000
        return MatchResult(
            order=matched_order,
            method=self.name,
            confidence=conf,
            latency_ms=round(latency_ms, 2),
            matched_by=matched_by,
            details={"entities": entities}
        )


# =====================================================================
# Bản 2: Rule / Regex & Text Normalization
# =====================================================================
class RuleOrderMatcher:
    """Method 2: Identify order using normalized regex patterns & dictionary lookups."""

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
        """Execute rule-based regex extraction and local lookup."""
        start = time.perf_counter()
        entities = extract_entities_advanced(query)

        matched_order = None
        matched_by = "none"
        conf = 0.0

        # Check tracking codes directly from query (including TIKI, GIAO, GHN, VTP, SPX)
        trk_match = re.search(r"\b(?:GIAO|GHN|VTP|SPX|TIKI)[A-Z0-9]{6,}\b", query, re.IGNORECASE)
        if trk_match:
            trk_code = trk_match.group(0).upper()
            if trk_code in self.orders_by_tracking:
                matched_order = self.orders_by_tracking[trk_code]
                matched_by = "tracking_code"
                conf = 1.0

        # Check order_id
        if not matched_order:
            oid = entities.get("order_id")
            if oid and oid.upper() in self.orders_by_id:
                matched_order = self.orders_by_id[oid.upper()]
                matched_by = "order_id"
                conf = 1.0

        # Check phone
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
            details={"entities": entities}
        )


# =====================================================================
# Bản 3: Embedding (Dense Vector Semantic Matching)
# =====================================================================
class EmbeddingOrderMatcher:
    """Method 3: Vectorize orders and calculate semantic cosine similarity with query."""

    name = "dense_embedding"

    def __init__(self, orders: Optional[List[Dict[str, Any]]] = None):
        self.orders = orders if orders is not None else load_all_orders()
        self.documents = []
        for o in self.orders:
            oid = str(o.get("order_id", ""))
            oid_num = oid.replace("ORD-", "")
            ph = str(o.get("phone", ""))
            ph_digits = re.sub(r"\D", "", ph)
            trk = str(o.get("tracking_code", ""))
            cname = str(o.get("customer_name", ""))
            items = " ".join(it.get("name", "") for it in o.get("items", []))

            # Rich semantic document
            doc = (
                f"{oid} {oid_num} ord {oid_num} {cname} {ph} {ph_digits} {trk} {items} "
                f"đơn hàng {oid} của {cname}"
            )
            self.documents.append(doc)

        # Word + Character n-grams for typo-tolerant dense retrieval
        self.vectorizer = TfidfVectorizer(
            ngram_range=(1, 2),
            sublinear_tf=True
        )
        self.matrix = self.vectorizer.fit_transform(self.documents)

    def match(self, query: str, threshold: float = 0.22) -> MatchResult:
        """Compute cosine similarity between query and all indexed order documents."""
        start = time.perf_counter()

        # Negative intent guard: if query is clearly asking general catalog/policy without order intent
        q_lower = query.lower()
        general_intents = ["có bán", "mua ở đâu", "tư vấn giúp", "tổng đài", "thời gian làm việc", "mã giảm giá"]
        is_general = any(gi in q_lower for gi in general_intents) and not any(k in q_lower for k in ["đơn", "order", "ord", "giao", "hủy"])

        matched_order = None
        best_score = 0.0
        best_idx = 0

        if not is_general:
            query_vec = self.vectorizer.transform([query])
            scores = cosine_similarity(query_vec, self.matrix)[0]
            best_idx = int(np.argmax(scores))
            best_score = float(scores[best_idx])

            if best_score >= threshold:
                matched_order = self.orders[best_idx]

        latency_ms = (time.perf_counter() - start) * 1000
        return MatchResult(
            order=matched_order,
            method=self.name,
            confidence=round(best_score, 4),
            latency_ms=round(latency_ms, 2),
            matched_by="semantic_similarity" if matched_order else "none",
            details={
                "top_score": best_score,
                "top_order_id": self.orders[best_idx].get("order_id") if not is_general else None
            }
        )


# =====================================================================
# Bản 4: Hybrid (Keyword / Rule + Dense Embedding)
# =====================================================================
class HybridOrderMatcher:
    """Method 4: Combines exact keyword/rule matching with dense semantic similarity."""

    name = "hybrid_keyword_embedding"

    def __init__(self, orders: Optional[List[Dict[str, Any]]] = None):
        self.orders = orders if orders is not None else load_all_orders()
        self.rule_matcher = RuleOrderMatcher(self.orders)
        self.embedding_matcher = EmbeddingOrderMatcher(self.orders)

    def match(self, query: str) -> MatchResult:
        """Two-tier cascade: check rule exact match first, blend with embedding."""
        start = time.perf_counter()

        # Step 1: Fast Rule / Lexical Match (< 0.1ms)
        rule_res = self.rule_matcher.match(query)

        matched_order = None
        matched_by = "none"
        conf = 0.0

        # Scenario A: Rule found an exact ID, Phone, or Tracking code -> 100% confidence
        if rule_res.order and rule_res.matched_by in ("order_id", "tracking_code", "phone"):
            matched_order = rule_res.order
            matched_by = f"exact_{rule_res.matched_by}"
            conf = 1.0
        else:
            # Scenario B: Rule did not find exact ID, fallback to semantic embedding
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
            }
        )
