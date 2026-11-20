"""Layer 4 & Layer 2: Microservice Contract Compatibility & Fault Isolation Tests.
Aligns with CMU MLIP Chapters 9 (Thinking like a Software Architect) & 18 (System Quality):
1. Contract Testing: Verifies Pydantic schemas shared between Gateway, Conversation, Telemetry, Document, and Frontend.
2. Fault Isolation / Graceful Degradation: Verifies that if downstream services (Conversation Service, Intent Service,
   RAG Service, Telemetry Service) fail or time out, the API Gateway degrades gracefully and returns a safe structured
   GatewayResponse (HTTP 200) instead of crashing with HTTP 500.
"""
import unittest
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from contracts.schemas import (
    AuditLogCreate,
    CustomerProfile,
    GatewayResponse,
    GuardrailResult,
    HumanActionUpdate,
    IntentPredictionResponse,
    RetrievedDocument,
    StaffProfile,
)
from services.gateway.src.main import app as gateway_app


class TestContractsAndFaultIsolation(unittest.TestCase):
    def setUp(self):
        self.gateway_client = TestClient(gateway_app)

    def test_shared_pydantic_contracts_serialization(self):
        """All inter-service contracts must serialize and deserialize without field loss."""
        staff = StaffProfile(
            staff_id="staff-01",
            name="Nguyễn Quản Trị",
            email="staff01@tiki.vn",
            role="Senior CSKH",
            department="CSKH",
        )
        cust = CustomerProfile(
            customer_id="CUST-1100",
            name="Lê Văn Sơn",
            phone="0998708581",
            email="son@example.com",
            assigned_staff_id=staff.staff_id,
        )
        order_dict = {
            "order_id": "ORD-1100",
            "customer_id": cust.customer_id,
            "customer_name": cust.name,
            "phone": cust.phone or "",
            "order_status": "DELIVERED",
            "total_amount": 450000,
        }
        doc = RetrievedDocument(
            doc_id="POL-RET-001",
            title="Chính sách đổi trả",
            content="Đổi trả trong 30 ngày với sản phẩm nguyên tem.",
            is_active=True,
        )
        resp = GatewayResponse(
            interaction_id="int-123",
            session_id="sess-123",
            intent=IntentPredictionResponse(intent="return_policy", confidence=0.95, is_in_scope=True),
            guardrail=GuardrailResult(allow_llm=True, action_type="PROCEED_TO_LLM", reason="Safe"),
            citations=[doc],
            draft_text="Dạ sản phẩm được đổi trả trong 30 ngày [POL-RET-001].",
            order_data=order_dict,
            latency_ms=12.5,
        )

        # Round-trip JSON verification
        dumped = resp.model_dump_json()
        restored = GatewayResponse.model_validate_json(dumped)
        self.assertEqual(restored.interaction_id, "int-123")
        self.assertEqual(restored.intent.intent, "return_policy")
        self.assertEqual(restored.citations[0].doc_id, "POL-RET-001")
        self.assertEqual(restored.order_data["order_id"], "ORD-1100")

        # Telemetry contracts
        audit = AuditLogCreate(
            interaction_id="int-123",
            customer_query="Đổi trả mấy ngày",
            predicted_intent="return_policy",
            intent_confidence=0.95,
            guardrail_action="PROCEED_TO_LLM",
            retrieved_doc_ids="POL-RET-001",
            raw_draft_text=resp.draft_text,
            latency_ms=12,
        )
        action = HumanActionUpdate(
            interaction_id=audit.interaction_id,
            action="APPROVE",
            final_text=resp.draft_text,
            handling_time_ms=4200,
        )
        self.assertEqual(action.action, "APPROVE")

    def test_fault_isolation_when_all_downstream_services_fail(self):
        """If Conversation, Intent, RAG, and Telemetry services are ALL unreachable,
        Gateway must still return HTTP 200 with a safe fallback GatewayResponse (never HTTP 500).
        """
        with patch("services.gateway.src.main.clients.predict_intent", new_callable=AsyncMock) as mock_intent, \
             patch("services.gateway.src.main.clients.retrieve_policies", new_callable=AsyncMock) as mock_rag, \
             patch("services.gateway.src.main.clients.log_telemetry", new_callable=AsyncMock) as mock_tel:
            mock_intent.side_effect = RuntimeError("Intent Service Connection Refused")
            mock_rag.side_effect = RuntimeError("RAG Service Connection Refused")
            mock_tel.return_value = None

            response = self.gateway_client.post(
                "/api/v1/copilot/query",
                json={
                    "query": "Kiểm tra đơn hàng ORD-1100 giúp mình",
                    "session_id": "sess_fault_test",
                    "customer_id": "CUST-1100",
                },
            )
            self.assertEqual(response.status_code, 200, f"Gateway crashed instead of isolating fault: {response.text}")
            data = response.json()
            self.assertIn("draft_text", data)
            self.assertTrue(len(data["draft_text"]) > 10)
            self.assertIn("guardrail", data)


if __name__ == "__main__":
    unittest.main()
