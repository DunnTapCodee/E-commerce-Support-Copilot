"""Offline unit & integration tests for Dot 2:
- Task 4: In-Chat Order Action Proposals & HITL Quick Approval (SQLite + LRU Cache + 422 guards)
- Task 5: Normalized mock_orders delivery dates, Idempotent Proactive Delay Agent (>3 days, 30k voucher),
          and Widespread Incident Clustering Dashboard.
"""
from datetime import datetime, timezone
import gc
import json
from pathlib import Path
import tempfile
import unittest

from contracts.order_actions import (
    evaluate_order_action_eligibility,
    extract_order_action_proposal,
)
from contracts.schemas import (
    AuditLogCreate,
    IncidentBroadcastRequest,
    OrderActionDecisionRequest,
)
from services.telemetry_service.src.database import init_db, migrate_mock_orders
from services.telemetry_service.src.repository import TelemetryRepository

ROOT_DIR = Path(__file__).resolve().parent.parent
MOCK_ORDERS_PATH = ROOT_DIR / "data" / "mock_orders.json"


class TestOrderActionsAndProactiveDelay(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.tmp_dir.name) / "test_dot2_telemetry.sqlite3"
        init_db(self.db_path, MOCK_ORDERS_PATH)
        migrate_mock_orders(self.db_path, MOCK_ORDERS_PATH, force=False)
        self.repo = TelemetryRepository(self.db_path, MOCK_ORDERS_PATH)

    def tearDown(self):
        self.repo = None
        gc.collect()
        self.tmp_dir.cleanup()

    def test_in_chat_proposal_never_mutates_db_and_respects_ownership(self):
        """Chat extraction creates PENDING proposal only for owned orders without modifying orders."""
        proc_order = self.repo.get_order("ORD-1026")
        self.assertIsNotNone(proc_order)
        owner = proc_order["customer_id"]

        # IDOR protection: foreign customer cannot propose change
        foreign_prop = extract_order_action_proposal(
            customer_query="Đổi địa chỉ giao hàng sang 99 Hai Bà Trưng, Quận 1, TP.HCM",
            intent="delivery_issue",
            order_data=proc_order,
            customer_id="CUST-9999",
        )
        self.assertIsNone(foreign_prop)

        # Valid owner address change on Processing order -> PENDING proposal, DB unchanged
        prop = extract_order_action_proposal(
            customer_query="Đổi địa chỉ giao hàng thành 99 Hai Bà Trưng, Quận 1, TP.HCM",
            intent="delivery_issue",
            order_data=proc_order,
            customer_id=owner,
            session_id="sess_addr",
            interaction_id="int_addr",
        )
        self.assertIsNotNone(prop)
        self.assertEqual(prop.action_type, "update_address")
        self.assertEqual(prop.status, "PENDING")
        self.assertTrue(prop.eligible)
        self.assertEqual(prop.proposed_values["shipping_address"], "99 Hai Bà Trưng, Quận 1, TP.HCM")

        # DB row still has original address before Staff approves
        before_db = self.repo.get_order("ORD-1026")
        self.assertNotEqual(before_db.get("shipping_address"), "99 Hai Bà Trưng, Quận 1, TP.HCM")

    def test_order_action_eligibility_matrix_and_atomic_hitl_decision(self):
        """APPROVE updates SQLite & invalidates cache; REJECT requires non-empty reason; Delivered blocks address change."""
        delivered = {"order_id": "ORD-TEST-DELIV", "order_status": "Delivered", "can_cancel": False}
        elig_addr, reason_addr = evaluate_order_action_eligibility("update_address", delivered)
        self.assertFalse(elig_addr)
        self.assertIn("Processing", reason_addr)
        elig_ret, _ = evaluate_order_action_eligibility("return_product", delivered)
        self.assertTrue(elig_ret)

        proc_order = self.repo.get_order("ORD-1026")
        prop = extract_order_action_proposal(
            customer_query="Đổi địa chỉ giao hàng sang 50 Nguyễn Thị Minh Khai, TP.HCM",
            intent="delivery_issue",
            order_data=proc_order,
            customer_id=proc_order["customer_id"],
            session_id="sess_decide",
            interaction_id="int_decide",
        )
        self.assertIsNotNone(prop)
        self.repo.propose_order_action(prop)

        # Missing reason on REJECT must raise ValueError (mapped to HTTP 422)
        with self.assertRaises(ValueError):
            self.repo.decide_order_action(
                prop.action_id,
                OrderActionDecisionRequest(decision="REJECT", reason="   ", performed_by="Staff A"),
            )

        # APPROVE updates orders table and refreshes LRU cache
        res = self.repo.decide_order_action(
            prop.action_id,
            OrderActionDecisionRequest(
                decision="APPROVE",
                reason="Đã xác minh khách đổi địa chỉ trước khi xuất kho",
                performed_by="Nguyễn Minh Anh",
            ),
        )
        self.assertEqual(res["status"], "APPROVED")
        self.assertEqual(res["order"]["shipping_address"], "50 Nguyễn Thị Minh Khai, TP.HCM")
        fresh = self.repo.get_order("ORD-1026")
        self.assertEqual(fresh["shipping_address"], "50 Nguyễn Thị Minh Khai, TP.HCM")

        # Rejecting a second action leaves order unchanged
        prop2 = extract_order_action_proposal(
            customer_query="Tôi muốn hủy đơn ORD-1026",
            intent="cancel_order",
            order_data=fresh,
            customer_id=fresh["customer_id"],
        )
        self.assertIsNotNone(prop2)
        self.repo.propose_order_action(prop2)
        rej = self.repo.decide_order_action(
            prop2.action_id,
            OrderActionDecisionRequest(decision="REJECT", reason="Khách yêu cầu giữ lại đơn", performed_by="Staff B"),
        )
        self.assertEqual(rej["status"], "REJECTED")
        self.assertEqual(self.repo.get_order("ORD-1026")["order_status"], "Processing")

    def test_mock_orders_dates_and_idempotent_proactive_delay_agent(self):
        """Exactly 3 Shipping orders are >3 days overdue on 2026-11-23 and repeat scan is idempotent."""
        raw_orders = json.loads(MOCK_ORDERS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(len(raw_orders), 100)
        self.assertTrue(all(o.get("promised_delivery_date") and o.get("shipping_address") for o in raw_orders))

        scan1 = self.repo.scan_overdue_shipping_orders(reference_date="2026-11-23", min_overdue_days=3)
        self.assertEqual(scan1["total_overdue_matching"], 3)
        self.assertEqual(scan1["newly_created_count"], 3)
        overdue_ids = {n["order_id"] for n in scan1["newly_created"]}
        self.assertEqual(overdue_ids, {"ORD-1009", "ORD-1011", "ORD-1012"})
        self.assertTrue(all(n["voucher_amount"] == 30000 for n in scan1["newly_created"]))

        # Second scan with same reference date must NOT issue duplicate vouchers
        scan2 = self.repo.scan_overdue_shipping_orders(reference_date="2026-11-23", min_overdue_days=3)
        self.assertEqual(scan2["newly_created_count"], 0)
        self.assertEqual(len(scan2["notifications"]), 3)

        # Bulk dispatch updates status PENDING_SEND -> SENT
        disp = self.repo.dispatch_delay_notifications(performed_by="Staff Ops")
        self.assertEqual(disp["dispatched_count"], 3)
        sent_rows = self.repo.list_delay_notifications(status="SENT")
        self.assertEqual(len(sent_rows), 3)

    def test_widespread_incident_clustering_and_broadcast(self):
        """Repeated storm delivery queries within 24h form one widespread incident cluster."""
        queries = [
            "Đơn của tôi bị kẹt do bão lũ chưa thấy giao",
            "Hàng giao chậm vì trời mưa bão phải không shop",
            "Khi nào hết ngập lụt ở miền Trung mới giao tiếp đơn ORD-1009",
            "Bão làm trễ đơn hàng nhiều ngày rồi",
        ]
        for idx, q in enumerate(queries):
            self.repo.insert_audit_log(
                AuditLogCreate(
                    interaction_id=f"int_storm_{idx}",
                    customer_query=q,
                    predicted_intent="delivery_issue",
                    intent_confidence=0.92,
                    guardrail_action="PROCEED_TO_LLM",
                    retrieved_doc_ids="POL-SHIP-001",
                    raw_draft_text="Dạ em xin lỗi vì thời tiết xấu...",
                    latency_ms=120,
                )
            )

        res = self.repo.get_incident_clusters(window_hours=24, min_cluster_size=3)
        self.assertGreaterEqual(res["widespread_count"], 1)
        top = res["clusters"][0]
        self.assertTrue(top["is_widespread"])
        self.assertEqual(top["count"], 4)
        self.assertTrue(
            "bão" in top["issue_topic"].lower() or "giao" in top["issue_topic"].lower(),
            f"Expected dynamic cluster terms in issue_topic, got: {top['issue_topic']}",
        )

        bcast = self.repo.record_incident_broadcast(
            IncidentBroadcastRequest(
                cluster_id=top["cluster_id"],
                issue_topic=top["issue_topic"],
                message_text=top["suggested_broadcast"],
                performed_by="Staff Manager",
            )
        )
        self.assertEqual(bcast["status"], "broadcast_recorded")

    def test_unseen_incident_topic_clusters_dynamically_without_hardcoded_keywords(self):
        """Regression test: Unseen incident topic (app crash on checkout) clusters dynamically via intent + token overlap."""
        unseen_queries = [
            "Ứng dụng bị văng màn hình trắng khi bấm vào giỏ hàng thanh toán",
            "Bấm thanh toán giỏ hàng trên app bị văng màn hình trắng liên tục",
            "App bị crash màn hình trắng ngay bước xác nhận giỏ hàng",
        ]
        for idx, q in enumerate(unseen_queries):
            self.repo.insert_audit_log(
                AuditLogCreate(
                    interaction_id=f"int_crash_{idx}",
                    customer_query=q,
                    predicted_intent="payment_issue",
                    intent_confidence=0.90,
                    guardrail_action="DIRECT_REFUND_FORM",
                    retrieved_doc_ids="POL-PAY-001",
                    raw_draft_text="...",
                    latency_ms=100,
                )
            )

        res = self.repo.get_incident_clusters(window_hours=24, min_cluster_size=3)
        crash_cluster = next((c for c in res["clusters"] if c["predicted_intent"] == "payment_issue"), None)
        self.assertIsNotNone(crash_cluster)
        self.assertEqual(crash_cluster["count"], 3)
        self.assertTrue(crash_cluster["is_widespread"])
        self.assertIn("trắng", crash_cluster["issue_topic"].lower())


if __name__ == "__main__":
    unittest.main()
