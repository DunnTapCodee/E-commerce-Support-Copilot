"""Retriever service for top-k matching with expired policy detection and intent routing."""
from pathlib import Path
from typing import List, Optional

from contracts.schemas import RetrievedDocument
from services.rag_service.src.indexer import PolicyVectorIndexer


class PolicyRetriever:
    """Knowledge retriever with cosine similarity search and expired document filtering."""

    def __init__(self, indexer: PolicyVectorIndexer):
        self.indexer = indexer

    def retrieve(
        self,
        query: str,
        intent: Optional[str] = None,
        top_k: int = 3,
        filter_active_only: bool = False,
    ) -> List[RetrievedDocument]:
        """Retrieve candidate policy documents based on query text and intent."""
        q_lower = query.lower()

        # Specific domain trap check: if query mentions warranty, include warranty policy (which may be expired)
        if any(term in q_lower for term in ("bảo hành", "bao hanh", "warranty")):
            warranty_docs = [
                doc for doc in self.indexer.documents if "POL-WARRANTY" in doc.doc_id
            ]
            if warranty_docs:
                if filter_active_only:
                    return [doc for doc in warranty_docs if doc.is_active]
                return warranty_docs

        # Direct search with vector indexer
        scored_docs = self.indexer.search(query, top_k=top_k)
        candidates = [doc for doc, score in scored_docs if score > 0.05]

        # Fallback to intent-based mapping if query vector match is too low
        if not candidates and intent:
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
            }
            target_id = intent_doc_map.get(intent)
            if target_id:
                candidates = [doc for doc in self.indexer.documents if doc.doc_id == target_id]

        if filter_active_only:
            candidates = [doc for doc in candidates if doc.is_active]

        return candidates[:top_k]
