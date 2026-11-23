"""Async client for RAG Knowledge & Generation Service with connection pooling and retries."""
from __future__ import annotations

import logging
from typing import List, Optional
import httpx
from contracts.schemas import RAGGenerateResponse, RetrievedDocument
from services.conversation_service.src.config import RAG_SERVICE_URL

logger = logging.getLogger("rag_client")


class RAGServiceClient:
    """High-performance RAG Knowledge Service Client with persistent connection pooling."""

    _client: Optional[httpx.AsyncClient] = None

    def __init__(self, base_url: str = RAG_SERVICE_URL):
        self.base_url = base_url.rstrip("/")

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        """Reuse singleton async client to avoid TCP handshake overhead on every turn."""
        if cls._client is None or cls._client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0)
            cls._client = httpx.AsyncClient(timeout=20.0, limits=limits)
        return cls._client

    async def retrieve_policies(
        self, query: str, intent: Optional[str] = None, top_k: int = 3
    ) -> List[RetrievedDocument]:
        client = self.get_client()
        last_exc: Optional[Exception] = None

        for attempt in range(2):
            try:
                resp = await client.post(
                    f"{self.base_url}/retrieve",
                    json={"query": query, "intent": intent, "top_k": top_k},
                )
                resp.raise_for_status()
                return [RetrievedDocument(**doc) for doc in resp.json()]
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning("[RAGClient] Retrieve error on attempt %d: %s. Retrying...", attempt + 1, exc)
                if RAGServiceClient._client and not RAGServiceClient._client.is_closed:
                    await RAGServiceClient._client.aclose()
                RAGServiceClient._client = None
                client = self.get_client()

        if last_exc:
            raise last_exc
        return []

    async def generate_draft(
        self, query: str, citations: List[RetrievedDocument]
    ) -> RAGGenerateResponse:
        client = self.get_client()
        last_exc: Optional[Exception] = None

        for attempt in range(2):
            try:
                resp = await client.post(
                    f"{self.base_url}/generate",
                    json={
                        "query": query,
                        "citations": [doc.model_dump() for doc in citations],
                    },
                )
                resp.raise_for_status()
                return RAGGenerateResponse(**resp.json())
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning("[RAGClient] Generate error on attempt %d: %s. Retrying...", attempt + 1, exc)
                if RAGServiceClient._client and not RAGServiceClient._client.is_closed:
                    await RAGServiceClient._client.aclose()
                RAGServiceClient._client = None
                client = self.get_client()

        if last_exc:
            raise last_exc
        raise RuntimeError("RAG generate unreachable after retries")
