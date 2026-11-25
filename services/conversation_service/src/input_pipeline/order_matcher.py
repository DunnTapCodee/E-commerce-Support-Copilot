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

from contracts.llm_failover import (
    call_chat_completion_with_failover,
    get_available_api_keys,
    is_external_llm_disabled,
)
from services.conversation_service.src.config import OPENAI_MODEL
from services.conversation_service.src.input_pipeline.offline_order_matcher_fallback import (
    OfflineOrderMatcherFallback,
)

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

    # 4. Offline coarse action & cancellation reason fallback (delegated cleanly)
    action_type, cancel_reason = OfflineOrderMatcherFallback.infer_offline_action_and_reason(query)

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

    def match(self, query: str, customer_id: Optional[str] = None) -> MatchResult:
        start = time.perf_counter()
        from contracts.safety import is_order_owned_by_customer

        entities = extract_entities_advanced(query)

        matched_order = None
        matched_by = "none"
        conf = 0.0

        trk_match = RE_TRACKING.search(query)
        if trk_match:
            trk_code = trk_match.group(0).upper()
            if trk_code in self.orders_by_tracking:
                cand = self.orders_by_tracking[trk_code]
                if not customer_id or is_order_owned_by_customer(cand, customer_id):
                    matched_order = cand
                    matched_by = "tracking_code"
                    conf = 1.0

        if not matched_order:
            oid = entities.get("order_id")
            if oid and oid.upper() in self.orders_by_id:
                cand = self.orders_by_id[oid.upper()]
                if not customer_id or is_order_owned_by_customer(cand, customer_id):
                    matched_order = cand
                    matched_by = "order_id"
                    conf = 1.0

        if not matched_order and entities.get("phone"):
            ph = re.sub(r"\D", "", str(entities.get("phone")))
            if ph in self.orders_by_phone:
                owned = [
                    o for o in self.orders_by_phone[ph]
                    if not customer_id or is_order_owned_by_customer(o, customer_id)
                ]
                if owned:
                    matched_order = owned[0]
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

    def match_all(self, query: str, customer_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Return all owned orders matching explicit IDs, tracking codes, or phone in query."""
        from contracts.safety import is_order_owned_by_customer
        from services.conversation_service.src.input_pipeline.fact_extractor import extract_all_order_ids

        results: List[Dict[str, Any]] = []
        seen: set[str] = set()

        for trk in RE_TRACKING.findall(query or ""):
            cand = self.orders_by_tracking.get(trk.upper())
            if cand and (not customer_id or is_order_owned_by_customer(cand, customer_id)):
                oid = str(cand.get("order_id", ""))
                if oid and oid not in seen:
                    seen.add(oid)
                    results.append(cand)

        for oid in extract_all_order_ids(query or ""):
            cand = self.orders_by_id.get(oid.upper())
            if cand and (not customer_id or is_order_owned_by_customer(cand, customer_id)):
                key = str(cand.get("order_id", ""))
                if key and key not in seen:
                    seen.add(key)
                    results.append(cand)

        if not results:
            entities = extract_entities_advanced(query or "")
            if entities.get("phone"):
                ph = re.sub(r"\D", "", str(entities["phone"]))
                for cand in self.orders_by_phone.get(ph, []):
                    if not customer_id or is_order_owned_by_customer(cand, customer_id):
                        key = str(cand.get("order_id", ""))
                        if key and key not in seen:
                            seen.add(key)
                            results.append(cand)

        return results[:limit]


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

    def match(
        self, query: str, threshold: float = 0.22, customer_id: Optional[str] = None
    ) -> MatchResult:
        start = time.perf_counter()
        from contracts.safety import is_order_owned_by_customer

        q_lower = query.lower()
        is_general = customer_id is None and OfflineOrderMatcherFallback.is_non_order_store_inquiry(query)

        matched_order = None
        best_score = 0.0

        if not is_general and self.vectorizer is not None and self.matrix is not None:
            try:
                from sklearn.metrics.pairwise import cosine_similarity
                query_vec = self.vectorizer.transform([query])
                scores = cosine_similarity(query_vec, self.matrix)[0]
                import numpy as np
                ranked_indices = np.argsort(scores)[::-1]
                for idx in ranked_indices:
                    cand_score = float(scores[int(idx)])
                    if cand_score < threshold:
                        break
                    cand_order = self.orders[int(idx)]
                    if customer_id and not is_order_owned_by_customer(cand_order, customer_id):
                        continue
                    best_score = cand_score
                    matched_order = cand_order
                    break
            except Exception:
                pass

        if not matched_order and not is_general and self.orders:
            tokens = set(q_lower.split())
            best_overlap = 0
            best_idx = -1
            for idx, o in enumerate(self.orders):
                if customer_id and not is_order_owned_by_customer(o, customer_id):
                    continue
                items = " ".join(it.get("name", "").lower() for it in o.get("items", []))
                overlap = sum(1 for t in tokens if len(t) > 2 and t in items)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_idx = idx
            if best_overlap >= 2 and best_idx >= 0:
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

    def match_all(
        self,
        query: str,
        threshold: float = 0.22,
        customer_id: Optional[str] = None,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Return all owned orders above similarity threshold, sorted descending."""
        from contracts.safety import is_order_owned_by_customer

        scored: List[tuple[float, Dict[str, Any]]] = []
        if self.vectorizer is not None and self.matrix is not None and len(self.orders) > 0:
            try:
                from sklearn.metrics.pairwise import cosine_similarity

                q_vec = self.vectorizer.transform([query])
                sims = cosine_similarity(q_vec, self.matrix).flatten()
                tokens = [t for t in re.split(r"\W+", (query or "").lower()) if len(t) > 2]
                for idx in sims.argsort()[::-1]:
                    score = float(sims[idx])
                    if score < threshold:
                        break
                    cand = self.orders[idx]
                    if customer_id and not is_order_owned_by_customer(cand, customer_id):
                        continue
                    items_txt = " ".join(it.get("name", "").lower() for it in cand.get("items", []))
                    if score < 0.45 and not any(t in items_txt for t in tokens):
                        continue
                    scored.append((score, cand))
            except Exception:
                scored = []

        if not scored:
            tokens = [t for t in re.split(r"\W+", (query or "").lower()) if len(t) > 2]
            for cand in self.orders:
                if customer_id and not is_order_owned_by_customer(cand, customer_id):
                    continue
                items = " ".join(it.get("name", "").lower() for it in cand.get("items", []))
                overlap = sum(1 for t in tokens if t in items)
                if overlap >= 2:
                    scored.append((min(0.85, 0.4 + overlap * 0.15), cand))
            scored.sort(key=lambda pair: pair[0], reverse=True)

        return [cand for _, cand in scored[:limit]]


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

    def match(self, query: str, customer_id: Optional[str] = None) -> MatchResult:
        start = time.perf_counter()
        rule_res = self.rule_matcher.match(query, customer_id=customer_id)

        matched_order = None
        matched_by = "none"
        conf = 0.0

        if rule_res.order and rule_res.matched_by in ("order_id", "tracking_code", "phone"):
            matched_order = rule_res.order
            matched_by = f"exact_{rule_res.matched_by}"
            conf = 1.0
        else:
            emb_res = self.embedding_matcher.match(query, customer_id=customer_id)
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

    def match_all(self, query: str, customer_id: Optional[str] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """Return all owned orders matching exact rules or semantic similarity."""
        exact = self.rule_matcher.match_all(query, customer_id=customer_id, limit=limit)
        if exact:
            return exact
        return self.embedding_matcher.match_all(query, customer_id=customer_id, limit=limit)


class PromptOrderMatcher:
    """Method 4: LLM Structured Entity Extraction with honest rule_fallback."""

    name = "pure_prompt"

    def __init__(self, orders: Optional[List[Dict[str, Any]]] = None):
        self.orders = orders if orders is not None else load_all_orders()
        self.rule_matcher = RuleOrderMatcher(self.orders)
        self.embedding_matcher = EmbeddingOrderMatcher(self.orders)

    async def match(self, query: str, customer_id: Optional[str] = None) -> MatchResult:
        """Use OpenAI-compatible LLM to extract order references; report honest rule_fallback when unavailable."""
        start = time.perf_counter()
        if not is_external_llm_disabled() and get_available_api_keys():
            prompt = (
                "Trích xuất thông tin định danh đơn hàng từ câu hỏi khách hàng.\n"
                "Trả về DUY NHẤT một JSON hợp lệ: "
                '{"order_id": "ORD-XXXX hoặc null", "tracking_code": "mã vận đơn hoặc null", '
                '"phone": "SĐT hoặc null", "product_hint": "tên sản phẩm hoặc null"}.\n'
                f'Câu hỏi: "{query}"'
            )
            payload = {
                "model": OPENAI_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.0,
                "max_tokens": 120,
            }
            try:
                data = await call_chat_completion_with_failover(payload, timeout=10.0)
                if data and data.get("choices"):
                    raw_text = (data["choices"][0].get("message", {}).get("content") or "").strip()
                    m = re.search(r"\{.*\}", raw_text, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group(0))
                        lookup_bits = [
                            str(parsed.get(k) or "").strip()
                            for k in ("order_id", "tracking_code", "phone")
                            if parsed.get(k)
                        ]
                        if lookup_bits:
                            rule_hit = self.rule_matcher.match(" ".join(lookup_bits), customer_id=customer_id)
                            if rule_hit.order:
                                return MatchResult(
                                    order=rule_hit.order,
                                    method=self.name,
                                    confidence=rule_hit.confidence,
                                    latency_ms=round((time.perf_counter() - start) * 1000, 2),
                                    matched_by=f"prompt_{rule_hit.matched_by}",
                                    details={"extracted": parsed},
                                )
                        product_hint = str(parsed.get("product_hint") or "").strip()
                        if product_hint:
                            emb_hit = self.embedding_matcher.match(product_hint, customer_id=customer_id)
                            if emb_hit.order:
                                return MatchResult(
                                    order=emb_hit.order,
                                    method=self.name,
                                    confidence=emb_hit.confidence,
                                    latency_ms=round((time.perf_counter() - start) * 1000, 2),
                                    matched_by="prompt_product_hint",
                                    details={"extracted": parsed},
                                )
            except Exception as exc:
                print(f"[PromptOrderMatcher] LLM extraction failed, falling back to rule_fallback: {exc}")

        res = self.rule_matcher.match(query, customer_id=customer_id)
        res.method = "rule_fallback"
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
