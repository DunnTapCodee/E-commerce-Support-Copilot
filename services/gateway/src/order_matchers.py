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
# Bản 1: Pure Prompt (LLM Zero-Shot Multi-Attribute Entity Extraction)
# =====================================================================
class PromptOrderMatcher:
    """Method 1: Identify order by querying LLM to extract full entity attributes, then multi-criteria DB query."""

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
        """Call LLM (Ckey OpenAI-compatible or Gemini) to extract comprehensive order entities, then score & look up."""
        import httpx
        start = time.perf_counter()

        api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
        provider = os.getenv("LLM_PROVIDER", "auto").lower()
        base_url = os.getenv("LLM_BASE_URL", "")

        entities = {}
        if api_key and not api_key.startswith("your_"):
            system_prompt = (
                "Bạn là AI chuyên gia bóc tách thực thể tra cứu đơn hàng thương mại điện tử Tiki.\n"
                "Nhiệm vụ: Phân tích kỹ câu của khách hàng và trích xuất TẤT CẢ các thông tin liên quan dưới dạng DUY NHẤT một chuỗi JSON hợp lệ không kèm bất kỳ giải thích nào:\n"
                "{\n"
                '  "order_id": string hoặc null (chuẩn hóa về dạng ORD-XXXX, ví dụ "1003", "#1003", "ORD 1003" -> "ORD-1003"),\n'
                '  "phone": string hoặc null (chuẩn hóa chuỗi số liền không khoảng trắng, ví dụ "0999 532 448" -> "0999532448"),\n'
                '  "tracking_code": string hoặc null (mã vận đơn, ví dụ GHN..., GIAO..., TIKI...),\n'
                '  "customer_name": string hoặc null (tên khách hàng người mua, ví dụ "Hoàng Mai Yến", "Trần Đức Nam"),\n'
                '  "product_name": string hoặc null (tên hoặc loại sản phẩm được nhắc tới, ví dụ "bình giữ nhiệt", "sạc dự phòng", "tai nghe"),\n'
                '  "brand_or_attributes": string hoặc null (thương hiệu, kích thước, dung tích, màu sắc, ví dụ "Lock&Lock", "800ml", "inox 304"),\n'
                '  "status_hint": string hoặc null (gợi ý trạng thái đơn: "Shipping", "Cancelled", "Delivered", "Processing", "Returned"),\n'
                '  "action": string ("status", "cancel", "details", "search", "customer_orders"),\n'
                '  "cancel_reason": string hoặc null\n'
                "}"
            )

            is_openai = provider == "openai" or bool(base_url) or (api_key.startswith("sk-") and not api_key.startswith("AQ."))

            try:
                if is_openai:
                    endpoint = f"{base_url.rstrip('/')}/chat/completions" if base_url else "https://api.xah.io/v1/chat/completions"
                    model = os.getenv("LLM_MODEL", "openai-gpt-oss-20b")
                    payload = {
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": query},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 800,
                    }
                    async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
                        resp = await client.post(
                            endpoint,
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json=payload,
                        )
                        if resp.status_code == 200:
                            data = resp.json()
                            msg = data["choices"][0]["message"]
                            content = (msg.get("content") or "").strip()
                            reasoning = (msg.get("reasoning_content") or "").strip()

                            # Helper parser
                            def try_parse_json(text: str) -> Optional[Dict[str, Any]]:
                                if not text:
                                    return None
                                cleaned = text
                                if "```json" in cleaned:
                                    cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
                                elif "```" in cleaned:
                                    cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
                                try:
                                    return json.loads(cleaned)
                                except Exception:
                                    # Try to find { ... } substring
                                    m = re.search(r"\{[\s\S]*\}", cleaned)
                                    if m:
                                        try:
                                            return json.loads(m.group(0))
                                        except Exception:
                                            pass
                                return None

                            parsed = try_parse_json(content)
                            if not parsed and reasoning:
                                parsed = try_parse_json(reasoning)
                            if parsed:
                                entities = parsed
                else:
                    model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                    payload = {
                        "contents": [{"parts": [{"text": f"{system_prompt}\n\nCâu của khách: \"{query}\""}]}],
                        "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
                    }
                    async with httpx.AsyncClient(timeout=10.0, verify=False) as client:
                        resp = await client.post(url, json=payload)
                        if resp.status_code == 200:
                            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                            entities = json.loads(text)
            except Exception:
                pass

        matched_order = None
        matched_by = "none"
        conf = 0.0
        details_extra: Dict[str, Any] = {"entities": entities}

        # 1. Khớp theo mã định danh duy nhất (Hard unique identifier)
        oid = entities.get("order_id")
        if oid and oid.upper() in self.orders_by_id:
            matched_order = self.orders_by_id[oid.upper()]
            matched_by = "order_id"
            conf = 1.0

        if not matched_order and entities.get("tracking_code"):
            trk = str(entities.get("tracking_code")).upper().strip()
            if trk in self.orders_by_tracking:
                matched_order = self.orders_by_tracking[trk]
                matched_by = "tracking_code"
                conf = 1.0

        if not matched_order and entities.get("phone"):
            ph = re.sub(r"\D", "", str(entities.get("phone")))
            if ph in self.orders_by_phone:
                phone_orders = self.orders_by_phone[ph]
                if len(phone_orders) == 1:
                    matched_order = phone_orders[0]
                    matched_by = "phone"
                    conf = 0.98
                else:
                    matched_order = phone_orders[0]
                    matched_by = "phone_multiple"
                    conf = 0.90
                    details_extra["all_orders_for_phone"] = [o["order_id"] for o in phone_orders]

        # 2. Khớp đa tiêu chí có trọng số (Multi-Criteria Weighted Scoring)
        # Sử dụng khi không có mã đơn/SĐT hoặc tra cứu bằng mô tả tự nhiên (tên sản phẩm, tên khách, thương hiệu)
        if not matched_order:
            cname = (entities.get("customer_name") or "").lower().strip()
            pname = (entities.get("product_name") or entities.get("product_keyword") or "").lower().strip()
            brand = (entities.get("brand_or_attributes") or "").lower().strip()
            stt_hint = (entities.get("status_hint") or "").lower().strip()

            scored_candidates: List[Tuple[float, Dict[str, Any], List[str]]] = []

            for o in self.orders:
                score = 0.0
                reasons: List[str] = []

                # Tiêu chí 1: Khớp tên khách hàng (Tối đa 50 điểm)
                if cname:
                    cust = str(o.get("customer_name", "")).lower()
                    if cname == cust:
                        score += 50.0
                        reasons.append(f"exact_customer:{cust}")
                    elif cname in cust or cust in cname:
                        score += 42.0
                        reasons.append(f"partial_customer:{cust}")

                # Tiêu chí 2: Khớp tên/loại sản phẩm (Tối đa 45 điểm)
                if pname:
                    best_item_score = 0.0
                    for it in o.get("items", []):
                        iname = str(it.get("name", "")).lower()
                        if pname in iname:
                            best_item_score = max(best_item_score, 45.0)
                        else:
                            p_tokens = set(pname.split())
                            i_tokens = set(iname.split())
                            overlap = len(p_tokens & i_tokens)
                            if overlap >= 2:
                                best_item_score = max(best_item_score, 30.0 * (overlap / max(1, len(p_tokens))))
                    if best_item_score > 0:
                        score += best_item_score
                        reasons.append(f"product:{pname}")

                # Tiêu chí 3: Khớp thương hiệu / thuộc tính / dung tích (Tối đa 25 điểm)
                if brand:
                    for it in o.get("items", []):
                        iname = str(it.get("name", "")).lower()
                        if brand in iname:
                            score += 25.0
                            reasons.append(f"brand_attr:{brand}")
                            break

                # Tiêu chí 4: Khớp trạng thái đơn (Tối đa 15 điểm)
                if stt_hint:
                    ostt = str(o.get("order_status", "")).lower()
                    if stt_hint in ostt or ostt in stt_hint:
                        score += 15.0
                        reasons.append(f"status:{ostt}")

                if score > 0:
                    scored_candidates.append((score, o, reasons))

            if scored_candidates:
                scored_candidates.sort(key=lambda x: x[0], reverse=True)
                top_score = scored_candidates[0][0]
                top_tied = [c for c in scored_candidates if c[0] == top_score]

                matched_order = scored_candidates[0][1]
                details_extra["reasons"] = scored_candidates[0][2]
                details_extra["top_score"] = top_score

                if len(top_tied) > 1 and not cname:
                    # Nhiều đơn cùng điểm (ví dụ chỉ tìm "bình giữ nhiệt" mà không có tên khách)
                    matched_by = "product_name_multiple"
                    conf = 0.75
                    details_extra["is_ambiguous"] = True
                    details_extra["tied_count"] = len(top_tied)
                    details_extra["candidate_order_ids"] = [c[1]["order_id"] for c in top_tied[:5]]
                else:
                    # Có tiêu chí tên khách hoặc thuộc tính phân biệt rõ ràng
                    matched_by = "multi_criteria_attributes"
                    conf = min(0.99, round(top_score / 100.0, 2))

        latency_ms = (time.perf_counter() - start) * 1000
        return MatchResult(
            order=matched_order,
            method=self.name,
            confidence=conf,
            latency_ms=round(latency_ms, 2),
            matched_by=matched_by,
            details=details_extra
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
