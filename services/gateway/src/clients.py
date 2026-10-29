"""Asynchronous HTTP clients communicating with downstream microservices via httpx."""
from typing import Any, Dict, List, Optional
import httpx

from contracts.schemas import (
    AuditLogCreate,
    HumanActionUpdate,
    IntentPredictionRequest,
    IntentPredictionResponse,
    OrderCancelRequest,
    OrderCancelResponse,
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
        self.llm_timeout = httpx.Timeout(35.0, connect=5.0)

    async def predict_intent(self, query: str) -> IntentPredictionResponse:
        """Call intent_service:8005/predict."""
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
        async with httpx.AsyncClient(timeout=self.llm_timeout) as client:
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

    async def lookup_orders_by_phone(self, phone: str) -> List[Dict[str, Any]]:
        """Call telemetry_service:8003/orders/phone/{phone} to retrieve all orders for a phone number."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                digits = "".join(c for c in phone if c.isdigit())
                phone_param = digits if len(digits) >= 9 else phone.strip()
                resp = await client.get(f"{TELEMETRY_SERVICE_URL}/orders/phone/{phone_param}")
                if resp.status_code == 200:
                    return resp.json().get("orders", [])
                single = await self.lookup_order(phone)
                return [single] if single else []
            except Exception:
                return []

    async def lookup_order(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Call telemetry_service:8003/orders/{identifier} (order_id, phone, tracking, or customer_id)."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(f"{TELEMETRY_SERVICE_URL}/orders/{identifier}")
                if resp.status_code == 200:
                    return resp.json()
                return None
            except httpx.HTTPError:
                return None

    async def cancel_order(self, order_id: str, reason: str = "Khách hàng yêu cầu hủy đơn") -> Dict[str, Any]:
        """Call telemetry_service:8003/orders/{order_id}/cancel."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                req_data = OrderCancelRequest(reason=reason)
                resp = await client.post(
                    f"{TELEMETRY_SERVICE_URL}/orders/{order_id}/cancel",
                    json=req_data.model_dump(),
                )
                if resp.status_code == 200:
                    return resp.json()
                return {"success": False, "order_id": order_id, "message": resp.text}
            except Exception as e:
                return {"success": False, "order_id": order_id, "message": str(e)}

    async def get_customer_orders(self, customer_id: str) -> List[Dict[str, Any]]:
        """Call telemetry_service:8003/orders/customer/{customer_id}."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.get(f"{TELEMETRY_SERVICE_URL}/orders/customer/{customer_id}")
                if resp.status_code == 200:
                    return resp.json().get("orders", [])
                return []
            except httpx.HTTPError:
                return []

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

    async def handover_session(self, session_id: str, is_live_chat: bool, agent_id: str = "agent_01") -> Dict[str, Any]:
        """Forward live chat handover toggle to conversation service."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/handover",
                json={"session_id": session_id, "is_live_chat": is_live_chat, "agent_id": agent_id},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_session_state(self, session_id: str) -> Dict[str, Any]:
        """Fetch conversation session state from conversation service."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(f"{CONVERSATION_SERVICE_URL}/api/v1/conversation/session/{session_id}")
            resp.raise_for_status()
            return resp.json()
