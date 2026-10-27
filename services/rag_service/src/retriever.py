"""Retriever service for top-k matching with expired policy detection and intent routing."""
import re
from pathlib import Path
from typing import List, Optional

from contracts.schemas import RetrievedDocument
from services.rag_service.src.indexer import PolicyVectorIndexer


class PolicyRetriever:
    """Knowledge retriever with cosine similarity search and expired document filtering."""

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
                    is_active=doc.is_active,
                    tags=tuple(getattr(doc, "tags", ()) or ()),
                )
                for doc in indexer.documents
                if doc.is_active
            ]
            if self.method == "bm25":
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

    def _search(self, query: str, top_k: int) -> List[RetrievedDocument]:
        if self.method == "tfidf":
            scored_docs = self.indexer.search(query, top_k=top_k)
            return [doc.model_copy(update={"score": round(score, 4)}) for doc, score in scored_docs]

        hits = self.searcher.search(query, top_k=top_k)
        documents_by_id = {doc.doc_id: doc for doc in self.indexer.documents}
        return [
            documents_by_id[hit.document.doc_id].model_copy(update={"score": round(hit.score, 6)})
            for hit in hits
            if hit.document.doc_id in documents_by_id
        ]

    def retrieve(
        self,
        query: str,
        intent: Optional[str] = None,
        top_k: int = 3,
        filter_active_only: bool = False,
    ) -> List[RetrievedDocument]:
        """Retrieve candidate policy documents based on query text and intent."""
        q_lower = query.lower()

        # Check if customer is asking about historical/expired/old policies (Safety Trap)
        is_asking_expired = any(
            term in q_lower
            for term in (
                "bảo hành cũ",
                "bao hanh cu",
                "chính sách cũ",
                "chinh sach cu",
                "hết hạn",
                "het han",
                "trước năm 2024",
                "truoc nam 2024",
                "năm 2023",
                "năm 2022",
                "2023",
                "2022",
                "quý mão",
                "phiên bản năm",
            )
        )

        if is_asking_expired:
            matched_old = []
            for doc in self.indexer.documents:
                if "OLD" in doc.doc_id:
                    if "promo" in doc.doc_id.lower() and any(k in q_lower for k in ("khuyến mãi", "hoàn xu", "tết", "quý mão", "2023")):
                        matched_old.insert(0, doc)
                    elif "return" in doc.doc_id.lower() and any(k in q_lower for k in ("đổi trả", "trả hàng", "phiên bản", "2022")):
                        matched_old.insert(0, doc)
                    elif "warranty" in doc.doc_id.lower() and any(k in q_lower for k in ("bảo hành", "2024")):
                        matched_old.insert(0, doc)
                    else:
                        matched_old.append(doc)
            if matched_old:
                if filter_active_only:
                    return [doc for doc in matched_old if doc.is_active]
                return matched_old[:top_k]

        # Strip order numbers (e.g. ORD-2024-001) so numeric tokens like '2024' don't falsely match old policy titles
        clean_query = re.sub(r"ORD-[\w-]+", "", query, flags=re.IGNORECASE).strip()
        search_query = clean_query if len(clean_query) > 3 else query

        # Historical-policy requests use the legacy full corpus so the existing
        # expired-policy safety path remains available. Normal requests use the
        # configured retrieval method over active policies.
        if is_asking_expired:
            scored_docs = self.indexer.search(search_query, top_k=top_k)
            candidates = [
                doc for doc, score in scored_docs
                if score > 0.05 and not doc.is_active
            ]
        else:
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
            matched = [doc for doc in self.indexer.documents if doc.doc_id == target_id and doc.is_active]
            if matched:
                if not candidates or all(c.doc_id != target_id for c in candidates):
                    candidates = matched + candidates

        if filter_active_only or not is_asking_expired:
            candidates = [doc for doc in candidates if doc.is_active]

        # In-scope general fallback if search yielded no active documents
        if not candidates and not is_asking_expired:
            fallback_docs = [doc for doc in self.indexer.documents if doc.doc_id in ("POL-CS-001", "POL-ORD-001") and doc.is_active]
            if fallback_docs:
                candidates = fallback_docs

        return candidates[:top_k]

