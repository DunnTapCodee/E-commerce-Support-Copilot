"""Unit tests for Step 1: Staff & Customer DB Schema, Seeding, and Backend APIs."""
import gc
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from contracts.schemas import PolicyCreateRequest, PolicyUpdateRequest, RetrievedDocument
from services.telemetry_service.src.database import get_db_connection, init_db
from services.telemetry_service.src.repository import TelemetryRepository
from services.telemetry_service.src.main import app as telemetry_app
from services.gateway.src.main import app as gateway_app


class TestRbacDatabaseAndApi(unittest.TestCase):
    """Verify Staff & Customer schema, auto-seeding, and Gateway/Telemetry endpoints."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.tmp_dir.name) / "test_rbac.sqlite3"
        self.mock_orders_path = Path(__file__).resolve().parents[1] / "data" / "mock_orders.json"
        init_db(self.db_path, self.mock_orders_path)
        self.repo = TelemetryRepository(self.db_path, self.mock_orders_path)

    def tearDown(self):
        self.repo = None
        gc.collect()
        self.tmp_dir.cleanup()

    def test_staff_and_customers_seeded(self):
        staff = self.repo.list_staff()
        self.assertGreaterEqual(len(staff), 3)
        staff_ids = {s["staff_id"] for s in staff}
        self.assertIn("staff-01", staff_ids)

        customers = self.repo.list_customers()
        self.assertGreater(len(customers), 0)
        cust_ids = {c["customer_id"] for c in customers}
        self.assertIn("CUST-1100", cust_ids)

    def test_filter_customers_by_assigned_staff(self):
        staff1_customers = self.repo.list_customers(assigned_staff_id="staff-01")
        self.assertGreater(len(staff1_customers), 0)
        for c in staff1_customers:
            self.assertEqual(c["assigned_staff_id"], "staff-01")
            self.assertEqual(c["assigned_staff_name"], "Nguyễn Minh Anh")

    def test_telemetry_service_staff_and_customer_endpoints(self):
        with patch("services.telemetry_service.src.main.repo_instance", self.repo):
            client = TestClient(telemetry_app)
            resp_staff = client.get("/staff")
            self.assertEqual(resp_staff.status_code, 200)
            self.assertGreaterEqual(resp_staff.json()["total"], 3)

            resp_cust = client.get("/customers", params={"assigned_staff_id": "staff-01"})
            self.assertEqual(resp_cust.status_code, 200)
            for item in resp_cust.json()["customers"]:
                self.assertEqual(item["assigned_staff_id"], "staff-01")

            resp_one = client.get("/customers/CUST-1100")
            self.assertEqual(resp_one.status_code, 200)
            self.assertEqual(resp_one.json()["customer_id"], "CUST-1100")

            resp_missing = client.get("/customers/NOT-EXIST")
            self.assertEqual(resp_missing.status_code, 404)

    def test_gateway_customer_overview_aggregates_cleanly(self):
        async def fake_get_json(url: str, params=None):
            if url.endswith("/customers/CUST-1100"):
                return {"customer_id": "CUST-1100", "name": "Lê Văn Sơn", "assigned_staff_id": "staff-01"}
            if "/orders/customer/CUST-1100" in url:
                return {"customer_id": "CUST-1100", "total_orders": 1, "orders": [{"order_id": "ORD-1100"}]}
            if "/api/v1/conversation/sessions" in url:
                return [{"sessionId": "sess_1", "customerId": "CUST-1100", "title": "Hội thoại 1"}]
            return {}

        with patch("services.gateway.src.routers.rbac_router._get_json", side_effect=fake_get_json):
            client = TestClient(gateway_app)
            resp = client.get("/api/v1/copilot/customers/CUST-1100/overview")
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertEqual(body["customer"]["customer_id"], "CUST-1100")
            self.assertEqual(body["total_orders"], 1)
            self.assertEqual(len(body["chat_sessions"]), 1)

    def test_policy_schemas_accept_updated_by_staff_id(self):
        doc = RetrievedDocument(
            doc_id="POL-TEST-1",
            title="Test",
            content="Test content",
            category="returns",
        )
        req = PolicyCreateRequest(policy=doc, updated_by_staff_id="staff-02")
        self.assertEqual(req.updated_by_staff_id, "staff-02")

        upd = PolicyUpdateRequest(updates={"title": "New"}, updated_by_staff_id="staff-02")
        self.assertEqual(upd.updated_by_staff_id, "staff-02")

    def test_customer_staff_sqlite_copilot_sync(self):
        from services.conversation_service.src.dialogue_state.sqlite_state_store import PersistentStateStore

        conv_db = Path(self.tmp_dir.name) / "test_conv.sqlite3"
        store = PersistentStateStore(conv_db)
        store.get_or_create("sess_sync_1", "CUST-1100")

        # 1. Customer sends message on /customer -> auto-updates default session title & adds turn
        store.add_turn_record("sess_sync_1", role="customer", content="Kiểm tra đơn ORD-1100 giúp mình")
        store.add_turn_record(
            "sess_sync_1",
            role="acknowledgement",
            content="Dạ Tiki đã nhận được yêu cầu, nhân viên đang kiểm tra ạ.",
            is_acknowledgement=True,
        )

        # 2. Copilot generates draft and saves metadata to SQLite
        store.set_copilot_draft(
            "sess_sync_1",
            "Dạ đơn hàng #ORD-1100 của anh Sơn đã giao thành công theo [POL-RETURN-01].",
            {"interaction_id": "int-123", "draft_text": "Dạ đơn hàng #ORD-1100..."},
        )

        # 3. Staff on /staff fetches session details -> sees customer message, ack, and pending Copilot draft!
        details = store.get_full_session_details("sess_sync_1")
        self.assertIsNotNone(details)
        self.assertEqual(len(details["messages"]), 2)
        self.assertIn("ORD-1100", details["copilotDraft"])
        self.assertEqual(details["copilotResponse"]["interaction_id"], "int-123")

        # 4. Staff clicks "Duyệt & Gửi Khách Hàng" -> adds approved agent message & clears pending draft
        store.add_turn_record(
            "sess_sync_1",
            role="agent",
            content="Dạ đơn hàng #ORD-1100 của anh Sơn đã giao thành công theo [POL-RETURN-01].",
            is_acknowledgement=False,
        )

        details_after = store.get_full_session_details("sess_sync_1")
        self.assertEqual(len(details_after["messages"]), 3)
        self.assertEqual(details_after["copilotDraft"], "")
        self.assertIsNone(details_after["copilotResponse"])


if __name__ == "__main__":
    unittest.main()
