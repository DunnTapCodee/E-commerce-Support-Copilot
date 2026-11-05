"""Async client for Intent Classification Service."""
from __future__ import annotations

import httpx
from contracts.schemas import IntentPredictionResponse
from services.conversation_service.src.config import INTENT_SERVICE_URL


class IntentServiceClient:
    def __init__(self, base_url: str = INTENT_SERVICE_URL):
        self.base_url = base_url.rstrip("/")

    async def predict_intent(self, query: str) -> IntentPredictionResponse:
        async with httpx.AsyncClient(timeout=4.0) as client:
            resp = await client.post(
                f"{self.base_url}/predict",
                json={"query": query},
            )
            resp.raise_for_status()
            return IntentPredictionResponse(**resp.json())
