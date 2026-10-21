"""Retriever service for top-k matching with expired policy detection and intent routing."""
import re
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
            )
        )

        if is_asking_expired:
            warranty_docs = [
                doc for doc in self.indexer.documents if "POL-WARRANTY-OLD" in doc.doc_id or "OLD" in doc.doc_id
            ]
            if warranty_docs:
                if filter_active_only:
                    return [doc for doc in warranty_docs if doc.is_active]
                return warranty_docs[:top_k]

        # Strip order numbers (e.g. ORD-2024-001) so numeric tokens like '2024' don't falsely match old policy titles
        clean_query = re.sub(r"ORD-[\w-]+", "", query, flags=re.IGNORECASE).strip()
        search_query = clean_query if len(clean_query) > 3 else query

        # Direct search with vector indexer
        scored_docs = self.indexer.search(search_query, top_k=top_k)
        candidates = [
            doc for doc, score in scored_docs
            if score > 0.05 and (doc.is_active or is_asking_expired)
        ]

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
        }
        if intent and intent in intent_doc_map:
            target_id = intent_doc_map[intent]
            matched = [doc for doc in self.indexer.documents if doc.doc_id == target_id and doc.is_active]
            if matched:
                if not candidates or all(c.doc_id != target_id for c in candidates):
                    candidates = matched + candidates

        if filter_active_only or not is_asking_expired:
            candidates = [doc for doc in candidates if doc.is_active]

        return candidates[:top_k]

