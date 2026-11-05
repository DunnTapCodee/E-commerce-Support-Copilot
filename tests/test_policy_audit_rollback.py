"""Unit & integration tests for Policy Audit Logging and Rollback mechanism."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

from services.rag_service.src import main as rag_main


class TestPolicyAuditAndRollback(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for testing policies & audit logs
        self.test_dir = tempfile.mkdtemp()
        self.test_policies_path = Path(self.test_dir) / "test_policies.json"
        self.test_audit_path = Path(self.test_dir) / "test_audit_logs.json"
        self.test_index_path = Path(self.test_dir) / "test_index.pkl"

        # Initial dummy policy
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

        # Patch module paths
        self.orig_policies_path = rag_main.POLICIES_PATH
        self.orig_audit_path = rag_main.AUDIT_LOGS_PATH
        self.orig_index_path = rag_main.INDEX_PATH
        rag_main.POLICIES_PATH = self.test_policies_path
        rag_main.AUDIT_LOGS_PATH = self.test_audit_path
        rag_main.INDEX_PATH = self.test_index_path

        self.client = TestClient(rag_main.app)

    def tearDown(self):
        rag_main.POLICIES_PATH = self.orig_policies_path
        rag_main.AUDIT_LOGS_PATH = self.orig_audit_path
        rag_main.INDEX_PATH = self.orig_index_path
        rag_main.init_knowledge_base()
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_create_policy_records_audit_log(self):
        payload = {
            "policy": {
                "doc_id": "POL-NEW-01",
                "category": "return_refund",
                "title": "Chính sách đổi trả Tết 2026",
                "content": "Hỗ trợ đổi hàng trong 30 ngày dịp Tết.",
                "version": "1.0",
                "is_active": True,
                "policy_type": "temporary",
                "effective_date": "2026-01-15",
                "expiration_date": "2026-02-15",
                "tags": ["đổi trả", "tết"],
                "score": None,
            },
            "performed_by": "NV_Test_A",
            "reason": "Áp dụng khuyến mãi đổi trả",
        }
        res = self.client.post("/policy/create", json=payload)
        self.assertEqual(res.status_code, 200)

        # Verify audit log
        logs_res = self.client.get("/policies/audit-logs")
        self.assertEqual(logs_res.status_code, 200)
        logs = logs_res.json()
        self.assertGreaterEqual(len(logs), 1)

        create_log = logs[0]
        self.assertEqual(create_log["action"], "CREATE")
        self.assertEqual(create_log["doc_id"], "POL-NEW-01")
        self.assertEqual(create_log["performed_by"], "NV_Test_A")
        self.assertIsNone(create_log["before_snapshot"])
        self.assertIsNotNone(create_log["after_snapshot"])
        self.assertEqual(create_log["after_snapshot"]["title"], "Chính sách đổi trả Tết 2026")

    def test_supersede_policy_and_rollback(self):
        # 1. Supersede an existing policy
        patch_payload = {
            "updates": {"policy_type": "superseded", "is_active": False},
            "performed_by": "NV_Manager",
            "reason": "Bị thay thế bởi chính sách mới",
        }
        res = self.client.patch("/policies/POL-EXISTING", json=patch_payload)
        self.assertEqual(res.status_code, 200)

        # Verify policy is superseded
        policies_res = self.client.get("/policies")
        p = next(x for x in policies_res.json() if x["doc_id"] == "POL-EXISTING")
        self.assertEqual(p["policy_type"], "superseded")
        self.assertFalse(p["is_active"])

        # Check audit log for SUPERSEDE
        logs = self.client.get("/policies/audit-logs").json()
        self.assertEqual(logs[0]["action"], "SUPERSEDE")
        self.assertEqual(logs[0]["performed_by"], "NV_Manager")
        supersede_log_id = logs[0]["log_id"]

        # 2. Rollback the SUPERSEDE operation
        rb_payload = {
            "log_id": supersede_log_id,
            "performed_by": "NV_Auditor",
            "reason": "Nhầm lẫn, khôi phục chính sách cũ",
        }
        rb_res = self.client.post("/policies/rollback", json=rb_payload)
        self.assertEqual(rb_res.status_code, 200)

        # Verify policy has been restored to active and permanent!
        restored_policies = self.client.get("/policies").json()
        restored_p = next(x for x in restored_policies if x["doc_id"] == "POL-EXISTING")
        self.assertEqual(restored_p["policy_type"], "permanent")
        self.assertTrue(restored_p["is_active"])

        # Check new audit log for ROLLBACK
        updated_logs = self.client.get("/policies/audit-logs").json()
        self.assertEqual(updated_logs[0]["action"], "ROLLBACK")
        self.assertEqual(updated_logs[0]["performed_by"], "NV_Auditor")

    def test_create_and_rollback_creation(self):
        # 1. Create a policy by mistake
        payload = {
            "policy": {
                "doc_id": "POL-MISTAKE",
                "category": "warranty",
                "title": "Chính sách bảo hành tạo nhầm",
                "content": "Nội dung nhập sai.",
                "version": "1.0",
                "is_active": True,
                "policy_type": "permanent",
                "effective_date": "2026-01-01",
                "expiration_date": None,
                "tags": ["bảo hành"],
            },
            "performed_by": "NV_Newbie",
            "reason": "Tạo nhầm",
        }
        self.client.post("/policy/create", json=payload)

        logs = self.client.get("/policies/audit-logs").json()
        create_log_id = logs[0]["log_id"]

        # 2. Rollback the creation
        rb_payload = {
            "log_id": create_log_id,
            "performed_by": "NV_Senior",
            "reason": "Hủy chính sách tạo nhầm",
        }
        rb_res = self.client.post("/policies/rollback", json=rb_payload)
        self.assertEqual(rb_res.status_code, 200)

        # Policy POL-MISTAKE should now be removed from policies
        policies = self.client.get("/policies").json()
        self.assertFalse(any(p["doc_id"] == "POL-MISTAKE" for p in policies))


if __name__ == "__main__":
    unittest.main()
