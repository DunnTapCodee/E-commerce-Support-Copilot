"""HTTP client wrappers for asynchronous inter-service communication."""
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
    RawPolicyFilterRequest,
    PolicyCreateRequest,
    PolicyUpdateRequest,
    PolicyRollbackRequest,
)
from services.gateway.src.config import (
    INTENT_SERVICE_URL,
    RAG_SERVICE_URL,
    TELEMETRY_SERVICE_URL,
    CONVERSATION_SERVICE_URL,
    DOCUMENT_SERVICE_URL,
)


class MicroserviceClients:
    """Manages connections to downstream services."""

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
        self, query: str, intent: Optional[str] = None, top_k: int = 3, filter_active_only: bool = False
    ) -> List[RetrievedDocument]:
        """Call rag_service:8002/retrieve."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            req_data = RAGRetrieveRequest(
                query=query, intent=intent, top_k=top_k, filter_active_only=filter_active_only
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
        """Call telemetry_service:8003/orders/phone/{phone}."""
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
        """Call telemetry_service:8003/orders/{identifier}."""
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
            except httpx.HTTPError as exc:
                print(f"[Gateway] Failed to record audit log: {exc}")

    async def record_human_action(self, action_payload: HumanActionUpdate) -> bool:
        """Send CS Agent review action to telemetry_service:8003/audit/action."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                resp = await client.post(
                    f"{TELEMETRY_SERVICE_URL}/audit/action",
                    json=action_payload.model_dump(),
                )
                return resp.status_code == 200
            except httpx.HTTPError as exc:
                print(f"[Gateway] Failed to record human action: {exc}")
                return False

    async def get_audit_stats(self) -> Dict[str, Any]:
        """Fetch dashboard telemetry KPIs from telemetry_service:8003/audit/stats."""
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

    # =====================================================================
    # Document Service Client Calls (Port 8004)
    # =====================================================================
    async def filter_policy(self, request: RawPolicyFilterRequest) -> Dict[str, Any]:
        """Call document_service:8004/api/v1/documents/filter-preview."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(35.0, connect=3.0)) as client:
            resp = await client.post(
                f"{DOCUMENT_SERVICE_URL}/api/v1/documents/filter-preview",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()

    async def create_policy(self, request: PolicyCreateRequest) -> Dict[str, Any]:
        """Call document_service:8004/api/v1/documents/policies."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0)) as client:
            resp = await client.post(
                f"{DOCUMENT_SERVICE_URL}/api/v1/documents/policies",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()

    async def list_policies(self) -> List[Dict[str, Any]]:
        """Call document_service:8004/api/v1/documents/policies."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0)) as client:
            resp = await client.get(f"{DOCUMENT_SERVICE_URL}/api/v1/documents/policies")
            resp.raise_for_status()
            return resp.json()

    async def get_policy(self, doc_id: str) -> Dict[str, Any]:
        """Call document_service:8004/api/v1/documents/policies/{doc_id}."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0)) as client:
            resp = await client.get(f"{DOCUMENT_SERVICE_URL}/api/v1/documents/policies/{doc_id}")
            resp.raise_for_status()
            return resp.json()

    async def update_policy(self, doc_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Call document_service:8004/api/v1/documents/policies/{doc_id}."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0)) as client:
            resp = await client.put(
                f"{DOCUMENT_SERVICE_URL}/api/v1/documents/policies/{doc_id}",
                json=updates,
            )
            resp.raise_for_status()
            return resp.json()

    async def delete_policy(self, doc_id: str, performed_by: str = "Admin", reason: Optional[str] = None) -> Dict[str, Any]:
        """Call document_service:8004/api/v1/documents/policies/{doc_id}."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0)) as client:
            resp = await client.delete(
                f"{DOCUMENT_SERVICE_URL}/api/v1/documents/policies/{doc_id}",
                params={"performed_by": performed_by, "reason": reason or ""},
            )
            resp.raise_for_status()
            return resp.json()

    async def list_policy_audit_logs(self) -> List[Dict[str, Any]]:
        """Call document_service:8004/api/v1/documents/policies/audit-logs."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0)) as client:
            resp = await client.get(f"{DOCUMENT_SERVICE_URL}/api/v1/documents/policies/audit-logs")
            resp.raise_for_status()
            return resp.json()

    async def rollback_policy(self, request: PolicyRollbackRequest) -> Dict[str, Any]:
        """Call document_service:8004/api/v1/documents/policies/rollback."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=3.0)) as client:
            resp = await client.post(
                f"{DOCUMENT_SERVICE_URL}/api/v1/documents/policies/rollback",
                json=request.model_dump(),
            )
            resp.raise_for_status()
            return resp.json()

    async def sync_active_status(self) -> Dict[str, Any]:
        """Call document_service:8004/api/v1/documents/policies/sync-active-status."""
        async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=3.0)) as client:
            resp = await client.post(f"{DOCUMENT_SERVICE_URL}/api/v1/documents/policies/sync-active-status")
            resp.raise_for_status()
            return resp.json()
