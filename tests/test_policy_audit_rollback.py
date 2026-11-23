"""Unit & integration tests for Document Service, Automated is_active Calculation, Audit Logging and Rollback."""
import json
import shutil
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from contracts.schemas import RetrievedDocument, get_vn_today
from services.document_service.src import main as doc_main
from services.document_service.src.policy_manager import (
    PolicyManager,
    calculate_active_status,
)
from services.document_service.src.routers import document_router


class TestPolicyAuditAndRollback(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.test_dir, ignore_errors=True)
        self.test_policies_path = Path(self.test_dir) / "test_policies.json"
        self.test_audit_path = Path(self.test_dir) / "test_audit_logs.json"

        # Initial mock policies
        self.initial_policies = [
            {
                "doc_id": "POL-EXISTING",
                "category": "shipping",
                "title": "Chính sách giao hàng tiêu chuẩn",
                "content": "Giao hàng toàn quốc từ 2 đến 4 ngày làm việc.",
                "version": "1.0",
                "is_active": True,
                "policy_type": "permanent",
                "effective_date": "2026-01-01",
                "expiration_date": None,
                "tags": ["vận chuyển", "giao hàng"],
                "score": None,
            }
        ]
        with open(self.test_policies_path, "w", encoding="utf-8") as f:
            json.dump(self.initial_policies, f, ensure_ascii=False)

        # Create isolated PolicyManager instance for testing
        self.manager = PolicyManager(
            policies_path=str(self.test_policies_path),
            audit_logs_path=str(self.test_audit_path),
        )

        # Patch singletons in router and main so endpoints/lifespan remain isolated in temp dir
        router_patcher = patch.object(document_router, "policy_manager", self.manager)
        main_patcher = patch.object(doc_main, "policy_manager", self.manager)
        router_patcher.start()
        main_patcher.start()
        self.addCleanup(main_patcher.stop)
        self.addCleanup(router_patcher.stop)

        # Mock RAG sync and guard against any outbound httpx.AsyncClient calls during offline tests
        httpx_post_patcher = patch.object(httpx.AsyncClient, "post", new_callable=AsyncMock)
        self.mock_httpx_post = httpx_post_patcher.start()
        self.addCleanup(httpx_post_patcher.stop)

        httpx_request_patcher = patch.object(httpx.AsyncClient, "request", new_callable=AsyncMock)
        self.mock_httpx_request = httpx_request_patcher.start()
        self.addCleanup(httpx_request_patcher.stop)

        sync_patcher = patch.object(PolicyManager, "trigger_rag_sync", new_callable=AsyncMock)
        self.mock_trigger_rag_sync = sync_patcher.start()
        self.addCleanup(sync_patcher.stop)

        self.client = TestClient(doc_main.app)

    def tearDown(self):
        self.mock_httpx_post.assert_not_called()
        self.mock_httpx_request.assert_not_called()

    # -------------------------------------------------------------------------
    # 1. Tests for Dynamic is_active Calculation
    # -------------------------------------------------------------------------
    def test_dynamic_is_active_permanent_policy(self):
        """Permanent policy with valid or no dates is active."""
        doc = {
            "doc_id": "POL-PERM",
            "policy_type": "permanent",
            "effective_date": "2026-01-01",
            "expiration_date": None,
        }
        ref_date = date(2026, 6, 1)
        is_active, reason = calculate_active_status(doc, ref_date)
        self.assertTrue(is_active)
        self.assertIn("đang có hiệu lực", reason.lower())

    def test_dynamic_is_active_future_effective_date(self):
        """Policy with future effective date is inactive (NOT_YET_EFFECTIVE)."""
        doc = {
            "doc_id": "POL-FUTURE",
            "policy_type": "permanent",
            "effective_date": "2026-12-01",
            "expiration_date": None,
        }
        ref_date = date(2026, 6, 1)
        is_active, reason = calculate_active_status(doc, ref_date)
        self.assertFalse(is_active)
        self.assertIn("chưa đến ngày hiệu lực", reason.lower())

    def test_dynamic_is_active_expired_policy(self):
        """Policy whose expiration date has passed is inactive (EXPIRED)."""
        doc = {
            "doc_id": "POL-EXPIRED",
            "policy_type": "temporary",
            "effective_date": "2026-01-01",
            "expiration_date": "2026-05-01",
        }
        ref_date = date(2026, 6, 1)
        is_active, reason = calculate_active_status(doc, ref_date)
        self.assertFalse(is_active)
        self.assertIn("đã hết hạn", reason.lower())

    def test_dynamic_is_active_superseded_policy(self):
        """Superseded policies are always inactive regardless of dates."""
        doc = {
            "doc_id": "POL-SUPERSEDED",
            "policy_type": "superseded",
            "effective_date": "2026-01-01",
            "expiration_date": "2026-12-31",
        }
        ref_date = date(2026, 6, 1)
        is_active, reason = calculate_active_status(doc, ref_date)
        self.assertFalse(is_active)
        self.assertIn("superseded", reason.lower())

    # -------------------------------------------------------------------------
    # 2. Integration Tests via Document Service Endpoints
    # -------------------------------------------------------------------------
    def test_create_policy_auto_computes_active_and_records_audit(self):
        """Creating a policy automatically evaluates is_active and logs CREATE audit event."""
        payload = {
            "policy": {
                "doc_id": "POL-NEW-01",
                "category": "warranty",
                "title": "Chính sách bảo hành 2026",
                "content": "Bảo hành 12 tháng tại các trung tâm ủy quyền.",
                "version": "1.0",
                "is_active": False,  # Client tries to pass False, but valid dates will auto-compute
                "policy_type": "permanent",
                "effective_date": "2026-01-01",
                "expiration_date": None,
                "tags": ["bảo hành"],
            },
            "performed_by": "Staff_A",
            "reason": "Thêm mới chính sách bảo hành",
        }
        resp = self.client.post("/api/v1/documents/policies", json=payload)
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["doc_id"], "POL-NEW-01")
        self.assertTrue(data["is_active"])  # Auto-recalculated to True!

        # Check Audit Log
        logs_resp = self.client.get("/api/v1/documents/policies/audit-logs")
        self.assertEqual(logs_resp.status_code, 200)
        logs = logs_resp.json()
        self.assertTrue(len(logs) >= 1)
        create_log = next(l for l in logs if l["doc_id"] == "POL-NEW-01")
        self.assertEqual(create_log["action"], "CREATE")
        self.assertEqual(create_log["performed_by"], "Staff_A")
        self.assertIsNotNone(create_log["after_snapshot"])
        self.assertIsNone(create_log["before_snapshot"])
        self.mock_trigger_rag_sync.assert_awaited_once()
        self.mock_httpx_post.assert_not_called()

    def test_update_policy_date_automatically_recalculates_is_active(self):
        """Updating expiration date to the past automatically flips is_active to False and records audit."""
        # 1. Update POL-EXISTING with an expired date relative to Vietnam calendar date
        past_date = (get_vn_today() - timedelta(days=10)).strftime("%Y-%m-%d")
        upd_payload = {
            "expiration_date": past_date,
            "policy_type": "temporary",
            "performed_by": "Staff_B",
            "reason": "Rút ngắn thời gian chính sách",
        }
        resp = self.client.put("/api/v1/documents/policies/POL-EXISTING", json=upd_payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["is_active"])  # Automatically flipped to False!
        self.assertEqual(data["expiration_date"], past_date)

        # 2. Verify Audit Log recorded UPDATE with before and after snapshots
        logs = self.client.get("/api/v1/documents/policies/audit-logs").json()
        upd_log = next(l for l in logs if l["doc_id"] == "POL-EXISTING" and l["action"] == "UPDATE")
        self.assertEqual(upd_log["performed_by"], "Staff_B")
        self.assertTrue(upd_log["before_snapshot"]["is_active"])
        self.assertFalse(upd_log["after_snapshot"]["is_active"])
        self.mock_trigger_rag_sync.assert_awaited_once()
        self.mock_httpx_post.assert_not_called()

    def test_rollback_policy_restores_state_and_recomputes_active(self):
        """Rollback restores policy to prior snapshot and recalculates active status."""
        # 1. Update POL-EXISTING title and content
        upd_payload = {
            "title": "Tiêu đề đã sửa nhầm",
            "content": "Nội dung không chính xác",
            "performed_by": "Staff_Mistake",
        }
        upd_resp = self.client.put("/api/v1/documents/policies/POL-EXISTING", json=upd_payload)
        self.assertEqual(upd_resp.status_code, 200)

        # 2. Fetch audit log for that update
        logs = self.client.get("/api/v1/documents/policies/audit-logs").json()
        mistake_log = next(l for l in logs if l["doc_id"] == "POL-EXISTING" and l["performed_by"] == "Staff_Mistake")

        # 3. Trigger rollback
        rb_payload = {
            "log_id": mistake_log["log_id"],
            "performed_by": "Manager_Admin",
            "reason": "Hoàn tác sai sót của nhân viên",
        }
        rb_resp = self.client.post("/api/v1/documents/policies/rollback", json=rb_payload)
        self.assertEqual(rb_resp.status_code, 200)
        restored = rb_resp.json()
        self.assertEqual(restored["title"], "Chính sách giao hàng tiêu chuẩn")
        self.assertTrue(restored["is_active"])

        # 4. Verify ROLLBACK audit log and sync calls (1 for update + 1 for rollback)
        logs_after = self.client.get("/api/v1/documents/policies/audit-logs").json()
        rb_log = logs_after[0]
        self.assertEqual(rb_log["action"], "ROLLBACK")
        self.assertEqual(rb_log["performed_by"], "Manager_Admin")
        self.assertEqual(self.mock_trigger_rag_sync.await_count, 2)
        self.mock_httpx_post.assert_not_called()

    def test_delete_policy_records_audit_and_triggers_mocked_rag_sync(self):
        """Deleting a policy removes it, records DELETE audit snapshot, and triggers mocked RAG sync."""
        del_resp = self.client.delete(
            "/api/v1/documents/policies/POL-EXISTING",
            params={"performed_by": "Staff_Del", "reason": "Ngừng áp dụng chính sách"},
        )
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.json(), {"status": "deleted", "doc_id": "POL-EXISTING"})
        self.assertIsNone(self.manager.get_policy("POL-EXISTING"))

        logs = self.client.get("/api/v1/documents/policies/audit-logs").json()
        del_log = next(l for l in logs if l["doc_id"] == "POL-EXISTING" and l["action"] == "DELETE")
        self.assertEqual(del_log["performed_by"], "Staff_Del")
        self.assertIsNotNone(del_log["before_snapshot"])
        self.assertIsNone(del_log["after_snapshot"])
        self.mock_trigger_rag_sync.assert_awaited_once()
        self.mock_httpx_post.assert_not_called()

    def test_batch_sync_active_status_detects_expired_and_logs_auto_expire(self):
        """Batch recompute detects policies that expired over time and logs AUTO_EXPIRE."""
        # Add a policy that expired yesterday (Vietnam calendar date) without user manually editing it
        yesterday = (get_vn_today() - timedelta(days=1)).strftime("%Y-%m-%d")
        docs = self.manager.load_policies()
        docs.append(RetrievedDocument(
            doc_id="POL-OVERNIGHT-EXP",
            category="promotions",
            title="Khuyến mãi Flash Sale đêm qua",
            content="Giảm giá 50% chỉ trong ngày hôm qua.",
            version="1.0",
            is_active=True,  # Was active yesterday
            policy_type="temporary",
            effective_date="2026-01-01",
            expiration_date=yesterday,
            tags=["sale"],
        ))
        self.manager.save_policies(docs)

        # Run Batch Sync
        sync_resp = self.client.post("/api/v1/documents/policies/sync-active-status")
        self.assertEqual(sync_resp.status_code, 200)
        res_data = sync_resp.json()["result"]
        self.assertTrue(res_data["updated_count"] >= 1)

        # Check that POL-OVERNIGHT-EXP was transitioned to Inactive
        updated_doc = self.manager.get_policy("POL-OVERNIGHT-EXP")
        self.assertFalse(updated_doc.is_active)

        # Check Audit Log for AUTO_EXPIRE event
        logs = self.manager.load_audit_logs()
        auto_log = next(l for l in logs if l.doc_id == "POL-OVERNIGHT-EXP" and l.action == "AUTO_EXPIRE")
        self.assertEqual(auto_log.performed_by, "System (Auto-Scheduler)")
        self.assertIn("Hệ thống tự động chuyển trạng thái", auto_log.reason)
        self.mock_trigger_rag_sync.assert_awaited_once()
        self.mock_httpx_post.assert_not_called()

    def test_batch_sync_active_status_skips_rag_sync_when_no_changes(self):
        """Batch recompute skips RAG sync when no policy status changes."""
        sync_resp = self.client.post("/api/v1/documents/policies/sync-active-status")
        self.assertEqual(sync_resp.status_code, 200)
        res_data = sync_resp.json()["result"]
        self.assertEqual(res_data["updated_count"], 0)
        self.mock_trigger_rag_sync.assert_not_awaited()
        self.mock_httpx_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
