"""Async client for Intent Classification Service with connection pooling and retries."""
from __future__ import annotations

import logging
from typing import Optional
import httpx
from contracts.schemas import IntentPredictionResponse
from services.conversation_service.src.config import INTENT_SERVICE_URL

logger = logging.getLogger("intent_client")


class IntentServiceClient:
    """High-performance Intent Service Client with persistent connection pooling."""

    _client: Optional[httpx.AsyncClient] = None

    def __init__(self, base_url: str = INTENT_SERVICE_URL):
        self.base_url = base_url.rstrip("/")

    @classmethod
    def get_client(cls) -> httpx.AsyncClient:
        """Reuse singleton async client to avoid TCP handshake overhead on every turn."""
        if cls._client is None or cls._client.is_closed:
            limits = httpx.Limits(max_keepalive_connections=20, max_connections=50, keepalive_expiry=30.0)
            cls._client = httpx.AsyncClient(timeout=18.0, limits=limits)
        return cls._client

    async def predict_intent(self, query: str) -> IntentPredictionResponse:
        """Call intent prediction with automatic retry on transient connection failures."""
        client = self.get_client()
        last_exc: Optional[Exception] = None

        for attempt in range(2):
            try:
                resp = await client.post(
                    f"{self.base_url}/predict",
                    json={"query": query},
                )
                resp.raise_for_status()
                return IntentPredictionResponse(**resp.json())
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                logger.warning("[IntentClient] Connection error on attempt %d: %s. Retrying...", attempt + 1, exc)
                # Reopen client if broken
                if IntentServiceClient._client and not IntentServiceClient._client.is_closed:
                    await IntentServiceClient._client.aclose()
                IntentServiceClient._client = None
                client = self.get_client()

        if last_exc:
            raise last_exc
        raise RuntimeError("Intent service unreachable after retries")
