"""Retriever service for top-k matching with metadata-driven expired policy detection and intent routing."""
from __future__ import annotations

from datetime import date
import re
from typing import List, Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from contracts.schemas import RetrievedDocument, get_vn_today
from services.rag_service.src.indexer import PolicyVectorIndexer

ORDER_ID_RE = re.compile(r"\bORD-[\w-]+\b", re.IGNORECASE)
YEAR_TOKEN_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")
BEFORE_YEAR_RE = re.compile(r"(?:trước\s+năm|truoc\s+nam|before)\s+(19\d{2}|20\d{2})\b", re.IGNORECASE)
WORD_TOKEN_RE = re.compile(r"(?u)\b[a-zA-ZÀ-ỹ]{3,}\b")

CURRENT_POLICY_CUES = (
    "hiện tại",
    "hiện hành",
    "hiện nay",
    "mới nhất",
    "đang áp dụng",
    "bây giờ",
    "current",
    "latest",
    "newest",
)

HISTORICAL_POLICY_CUES = (
    "chính sách cũ",
    "chinh sach cu",
    "bảo hành cũ",
    "bao hanh cu",
    "quy định cũ",
    "quy dinh cu",
    "quy chế cũ",
    "quy che cu",
    "phiên bản cũ",
    "phien ban cu",
    "phiên bản năm",
    "phien ban nam",
    "hết hạn",
    "het han",
    "hết hiệu lực",
    "het hieu luc",
    "bãi bỏ",
    "bai bo",
    "trước đây",
    "truoc day",
    "old policy",
    "expired",
    "superseded",
)


def is_document_temporally_active(doc: RetrievedDocument, today: Optional[date] = None) -> bool:
    """Evaluate document active validity strictly from schema metadata and Vietnam calendar date."""
    ref_today = today or get_vn_today()
    if not doc.is_active:
        return False
    if getattr(doc, "policy_type", "permanent") == "superseded":
        return False
    eff_raw = getattr(doc, "effective_date", None)
    if eff_raw:
        try:
            if date.fromisoformat(str(eff_raw)[:10]) > ref_today:
                return False
        except ValueError:
            pass
    exp_raw = getattr(doc, "expiration_date", None)
    if exp_raw:
        try:
            if date.fromisoformat(str(exp_raw)[:10]) < ref_today:
                return False
        except ValueError:
            pass
    return True


class PolicyRetriever:
    """Knowledge retriever with active-corpus ranking and generalized inactive/expired policy detection."""

    METHODS = {"tfidf", "bm25", "dense", "hybrid", "reranked"}

    def __init__(
        self,
        indexer: PolicyVectorIndexer,
        method: str = "tfidf",
        dense_model: str = "keepitreal/vietnamese-sbert",
        reranker_model: str = "BAAI/bge-reranker-base",
        device: str = "cpu",
    ):
        self.indexer = indexer
        self.method = method.strip().lower()
        if self.method not in self.METHODS:
            raise ValueError(
                f"Unknown RETRIEVAL_METHOD '{method}'. Choose one of: {', '.join(sorted(self.METHODS))}."
            )
        self.searcher = None
        if self.method != "tfidf":
            from services.rag_service.src.search_experiments import (
                BM25Searcher,
                DenseSearcher,
                HybridSearcher,
                PolicyDocument,
                RerankedHybridSearcher,
            )

            active_documents = [
                PolicyDocument(
                    doc_id=doc.doc_id,
                    category=getattr(doc, "category", ""),
                    title=doc.title,
                    content=doc.content,
                    version=doc.version,
                    is_active=is_document_temporally_active(doc),
                    tags=tuple(getattr(doc, "tags", ()) or ()),
                )
                for doc in indexer.documents
                if is_document_temporally_active(doc)
            ]
            if not active_documents:
                self.searcher = None
            elif self.method == "bm25":
                self.searcher = BM25Searcher(active_documents, include_tags=True)
            elif self.method == "dense":
                self.searcher = DenseSearcher(active_documents, model_name=dense_model, device=device)
            else:
                hybrid = HybridSearcher(
                    BM25Searcher(active_documents, include_tags=True),
                    DenseSearcher(active_documents, model_name=dense_model, device=device),
                )
                self.searcher = (
                    RerankedHybridSearcher(hybrid, model_name=reranker_model, device=device)
                    if self.method == "reranked"
                    else hybrid
                )

        # Build a lightweight unified lexical index over all documents (active + inactive)
        # so expired/superseded policies with ANY doc_id or year can be surfaced when
        # filter_active_only=False without hardcoded IDs or years.
        self._corpus_vectorizer: Optional[TfidfVectorizer] = None
        self._corpus_matrix = None
        self._doc_word_sets: list[set[str]] = []
        self._active_vocab_words: set[str] = set()
        if self.indexer.documents:
            corpus_texts: list[str] = []
            for doc in self.indexer.documents:
                meta_dates = f"{getattr(doc, 'effective_date', '') or ''} {getattr(doc, 'expiration_date', '') or ''}"
                tags_str = " ".join(getattr(doc, "tags", ()) or ())
                full_text = f"{doc.title} {tags_str} {doc.content} {meta_dates}".strip()
                corpus_texts.append(full_text)
                words = {w.lower() for w in WORD_TOKEN_RE.findall(full_text)}
                self._doc_word_sets.append(words)
                if is_document_temporally_active(doc):
                    self._active_vocab_words.update(words)

            self._corpus_vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True)
            self._corpus_matrix = self._corpus_vectorizer.fit_transform(corpus_texts)

    def _has_historical_temporal_signal(self, clean_query: str, today: date) -> bool:
        """Detect general historical/past-year cues dynamically relative to Vietnam's current year."""
        q_lower = " ".join(clean_query.lower().split())
        if any(cue in q_lower for cue in HISTORICAL_POLICY_CUES):
            return True

        for match in BEFORE_YEAR_RE.finditer(q_lower):
            if int(match.group(1)) <= today.year:
                return True

        for match in YEAR_TOKEN_RE.finditer(q_lower):
            if int(match.group(1)) < today.year:
                return True

        return False

    def _match_inactive_policies(self, clean_query: str, top_k: int) -> List[RetrievedDocument]:
        """Surface inactive/expired/superseded policies only when query specifically targets them."""
        if (
            self._corpus_vectorizer is None
            or self._corpus_matrix is None
            or not self.indexer.documents
        ):
            return []

        today = get_vn_today()
        has_historical_cue = self._has_historical_temporal_signal(clean_query, today)
        q_lower = " ".join(clean_query.lower().split())

        if not has_historical_cue and any(cue in q_lower for cue in CURRENT_POLICY_CUES):
            return []

        q_vec = self._corpus_vectorizer.transform([clean_query])
        scores = cosine_similarity(q_vec, self._corpus_matrix)[0]

        active_indices = [
            idx for idx, doc in enumerate(self.indexer.documents) if is_document_temporally_active(doc, today)
        ]
        inactive_indices = [
            idx for idx, doc in enumerate(self.indexer.documents) if not is_document_temporally_active(doc, today)
        ]
        if not inactive_indices:
            return []

        best_active_score = max((float(scores[idx]) for idx in active_indices), default=0.0)
        query_words = {w.lower() for w in WORD_TOKEN_RE.findall(clean_query)}

        matched_inactive: list[tuple[float, RetrievedDocument]] = []
        for idx in inactive_indices:
            score = float(scores[idx])
            doc = self.indexer.documents[idx]
            if has_historical_cue:
                if score >= 0.08:
                    matched_inactive.append((score, doc.model_copy(update={"score": round(score, 4)})))
            else:
                distinctive_words = (query_words & self._doc_word_sets[idx]) - self._active_vocab_words
                if distinctive_words and score >= 0.14 and score > max(best_active_score * 1.25, 0.12):
                    matched_inactive.append((score, doc.model_copy(update={"score": round(score, 4)})))

        matched_inactive.sort(key=lambda item: item[0], reverse=True)
        return [doc for _, doc in matched_inactive[:top_k]]

    def _search(self, query: str, top_k: int) -> List[RetrievedDocument]:
        if self.method == "tfidf":
            scored_docs = self.indexer.search(query, top_k=max(top_k * 2, 6))
            return [
                doc.model_copy(update={"score": round(score, 4)})
                for doc, score in scored_docs
                if is_document_temporally_active(doc)
            ][:top_k]

        if not self.searcher:
            return []

        hits = self.searcher.search(query, top_k=top_k)
        documents_by_id = {doc.doc_id: doc for doc in self.indexer.documents}
        return [
            documents_by_id[hit.document.doc_id].model_copy(update={"score": round(hit.score, 6)})
            for hit in hits
            if hit.document.doc_id in documents_by_id and is_document_temporally_active(documents_by_id[hit.document.doc_id])
        ]

    def retrieve(
        self,
        query: str,
        intent: Optional[str] = None,
        top_k: int = 3,
        filter_active_only: bool = False,
    ) -> List[RetrievedDocument]:
        """Retrieve candidate policy documents based on query text, metadata validity, and intent."""
        # Strip order numbers (e.g. ORD-2024-001) so numeric tokens inside order IDs don't trigger year cues
        clean_query = ORDER_ID_RE.sub(" ", query or "").strip()
        search_query = clean_query if len(clean_query) > 3 else (query or "").strip()

        if not filter_active_only:
            inactive_hits = self._match_inactive_policies(search_query, top_k=top_k)
            if inactive_hits:
                return inactive_hits[:top_k]

        candidates = self._search(search_query, top_k)
        if self.method == "tfidf":
            candidates = [doc for doc in candidates if (doc.score or 0.0) > 0.05]

        # Intent-based fallback mapping if query text vector match is low
        intent_doc_map = {
            "track_order": "POL-ORD-001",
            "cancel_order": "POL-ORD-002",
            "delivery_time": "POL-SHIP-001",
            "shipping_costs": "POL-SHIP-002",
            "delivery_issue": "POL-SHIP-004",
            "return_policy": "POL-RET-001",
            "return_product": "POL-RET-002",
            "refund_policy": "POL-REFUND-001",
            "refund_status": "POL-REFUND-002",
            "request_refund": "POL-REFUND-001",
            "payment_issue": "POL-PAY-001",
            "human_agent": "POL-CS-001",
            "warranty": "POL-WARRANTY-001",
            "create_account": "POL-CS-002",
            "recover_password": "POL-CS-003",
            "get_discounts": "POL-CS-005",
        }
        if intent and intent in intent_doc_map:
            target_id = intent_doc_map[intent]
            matched = [
                doc
                for doc in self.indexer.documents
                if doc.doc_id == target_id and is_document_temporally_active(doc)
            ]
            if matched:
                if not candidates or all(c.doc_id != target_id for c in candidates):
                    candidates = matched + candidates

        candidates = [doc for doc in candidates if is_document_temporally_active(doc)]

        # In-scope general fallback if search yielded no active documents
        if not candidates:
            fallback_docs = [
                doc
                for doc in self.indexer.documents
                if doc.doc_id in ("POL-CS-001", "POL-ORD-001") and is_document_temporally_active(doc)
            ]
            if fallback_docs:
                candidates = fallback_docs

        return candidates[:top_k]

