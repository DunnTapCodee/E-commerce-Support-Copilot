"""Asynchronous HTTP clients communicating with downstream microservices via httpx."""
from typing import Any, Dict, List, Optional
import httpx

from contracts.schemas import (
    AuditLogCreate,
    HumanActionUpdate,
    IntentPredictionRequest,
    IntentPredictionResponse,
    RAGGenerateRequest,
    RAGGenerateResponse,
    RAGRetrieveRequest,
    RetrievedDocument,
)
from services.gateway.src.config import (
    INTENT_SERVICE_URL,
    RAG_SERVICE_URL,
    TELEMETRY_SERVICE_URL,
)


class MicroserviceClients:
    """HTTP Client pool connecting API Gateway to worker services."""

    def __init__(self):
        self.timeout = httpx.Timeout(10.0, connect=3.0)

    async def predict_intent(self, query: str) -> IntentPredictionResponse:
        """Call intent_service:8001/predict."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{INTENT_SERVICE_URL}/predict",
                json=IntentPredictionRequest(query=query).model_dump(),
            )
            resp.raise_for_status()
            return IntentPredictionResponse(**resp.json())

    async def retrieve_policies(
        self, query: str, intent: Optional[str] = None, top_k: int = 3
    ) -> List[RetrievedDocument]:
        """Call rag_service:8002/retrieve."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            req_data = RAGRetrieveRequest(
                query=query, intent=intent, top_k=top_k, filter_active_only=False
            )
            resp = await client.post(
                f"{RAG_SERVICE_URL}/retrieve",
                json=req_data.model_dump(),
            )
            resp.raise_for_status()
            return [RetrievedDocument(**item) for item in resp.json()]

    async def generate_draft(
        self, query: str, citations: List[RetrievedDocument]
    ) -> RAGGenerateResponse:
        """Call rag_service:8002/generate."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            req_data = RAGGenerateRequest(
                query=query,
                citations=citations,
            )
            resp = await client.post(
                f"{RAG_SERVICE_URL}/generate",
                json=req_data.model_dump(),
            )
            resp.raise_for_status()
            return RAGGenerateResponse(**resp.json())

    async def lookup_order(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Call telemetry_service:8003/orders/{customer_id}."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(f"{TELEMETRY_SERVICE_URL}/orders/{customer_id}")
                if resp.status_code == 200:
                    return resp.json()
                return None
            except httpx.HTTPError:
                return None

    async def log_telemetry(self, log_record: AuditLogCreate) -> None:
        """Fire-and-forget asynchronous audit log call to telemetry_service:8003/audit/log."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                await client.post(
                    f"{TELEMETRY_SERVICE_URL}/audit/log",
                    json=log_record.model_dump(),
                )
            except Exception as e:
                print(f"[Gateway] Warning: Failed to send telemetry audit log: {e}")

    async def record_human_action(self, action_record: HumanActionUpdate) -> Dict[str, Any]:
        """Forward human review action to telemetry_service:8003/audit/action."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{TELEMETRY_SERVICE_URL}/audit/action",
                json=action_record.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()

    async def get_audit_stats(self) -> Dict[str, Any]:
        """Fetch audit metrics and stats from telemetry_service."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{TELEMETRY_SERVICE_URL}/audit/stats")
            resp.raise_for_status()
            return resp.json()
