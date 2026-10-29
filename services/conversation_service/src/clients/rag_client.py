"""Async client for RAG Knowledge & Generation Service."""
from __future__ import annotations

from typing import List, Optional
import httpx
from contracts.schemas import RAGGenerateResponse, RetrievedDocument
from services.conversation_service.src.config import RAG_SERVICE_URL


class RAGServiceClient:
    def __init__(self, base_url: str = RAG_SERVICE_URL):
        self.base_url = base_url.rstrip("/")

    async def retrieve_policies(
        self, query: str, intent: Optional[str] = None, top_k: int = 3
    ) -> List[RetrievedDocument]:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.post(
                f"{self.base_url}/retrieve",
                json={"query": query, "intent": intent, "top_k": top_k},
            )
            resp.raise_for_status()
            return [RetrievedDocument(**doc) for doc in resp.json()]

    async def generate_draft(
        self, query: str, citations: List[RetrievedDocument]
    ) -> RAGGenerateResponse:
        async with httpx.AsyncClient(timeout=9.0) as client:
            resp = await client.post(
                f"{self.base_url}/generate",
                json={
                    "query": query,
                    "citations": [doc.model_dump() for doc in citations],
                },
            )
            resp.raise_for_status()
            return RAGGenerateResponse(**resp.json())
