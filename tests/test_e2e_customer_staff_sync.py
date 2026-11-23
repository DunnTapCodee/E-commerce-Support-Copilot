"""Layer 3: End-to-End Lifecycle Test for Customer <-> SQLite State Store <-> Staff Sync."""
import gc
from pathlib import Path
import tempfile
import time
import unittest

from services.conversation_service.src.dialogue_state.sqlite_state_store import (
    PersistentStateStore,
    init_conversation_db,
)


class TestE2ECustomerStaffSynchronization(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.tmp_dir.name) / "test_e2e_conversations.sqlite3"
        init_conversation_db(self.db_path)
        self.store = PersistentStateStore(self.db_path)

    def tearDown(self):
        self.store = None
        gc.collect()
        self.tmp_dir.cleanup()

    def test_full_customer_to_staff_copilot_lifecycle(self):
        self.store.get_or_create("sess_old_1100", "CUST-1100")
        self.store.add_turn_record("sess_old_1100", role="customer", content="Đổi trả trong mấy ngày?")
        self.store.add_turn_record(
            "sess_old_1100",
            role="agent",
            content="Dạ đổi trả trong 30 ngày theo [POL-RET-001] ạ.",
            is_acknowledgement=False,
        )

        time.sleep(0.02)

        sess_new = "sess_new_1002"
        customer_question = "Đơn hàng ORD-1002 của tôi bao giờ giao tới nơi vậy?"
        self.store.get_or_create(sess_new, "CUST-1002")
        self.store.add_turn_record(sess_new, role="customer", content=customer_question)

        ack_text = "Dạ em đã ghi nhận câu hỏi về tiến độ giao hàng của anh/chị. Em đang kiểm tra ngay đây ạ!"
        self.store.add_turn_record(sess_new, role="acknowledgement", content=ack_text, is_acknowledgement=True)

        draft_text = (
            "Dạ chào anh Phan Văn An, đơn hàng **ORD-1002** đang trên đường vận chuyển, "
            "dự kiến giao trong 1-2 ngày tới theo quy định [POL-SHIP-001] ạ."
        )
        copilot_meta = {
            "interaction_id": "int_e2e_1002",
            "intent": {"intent": "delivery_time", "confidence": 0.96},
            "guardrail": {"allow_llm": True, "action_type": "PROCEED_TO_LLM", "reason": "Safe"},
            "citations": [
                {
                    "doc_id": "POL-SHIP-001",
                    "title": "Chính sách thời gian giao hàng tiêu chuẩn",
                    "content": "Thời gian giao hàng tiêu chuẩn từ 1-3 ngày làm việc.",
                    "is_active": True,
                }
            ],
            "draft_text": draft_text,
        }
        self.store.set_copilot_draft(sess_new, draft_text, copilot_meta)

        all_sessions = self.store.list_sessions_by_customer()
        self.assertGreaterEqual(len(all_sessions), 2)
        newest_sess = next(s for s in all_sessions if s["sessionId"] == sess_new)
        self.assertEqual(newest_sess["customerId"], "CUST-1002")
        self.assertEqual(newest_sess["copilotDraft"], draft_text)

        customer_ids = ["CUST-1100", "CUST-1002"]
        activity_map = {s["customerId"]: s for s in all_sessions}
        sorted_customers = sorted(
            customer_ids,
            key=lambda cid: (
                1 if (activity_map.get(cid, {}).get("copilotDraft") or "").strip() else 0,
                activity_map.get(cid, {}).get("updatedAt", ""),
            ),
            reverse=True,
        )
        self.assertEqual(sorted_customers[0], "CUST-1002")

        self.store.add_turn_record(sess_new, role="agent", content=draft_text, is_acknowledgement=False)

        details = self.store.get_full_session_details(sess_new)
        self.assertIsNotNone(details)
        self.assertEqual(details["copilotDraft"], "")
        self.assertIsNone(details["copilotResponse"])

        msgs = details["messages"]
        self.assertEqual(len(msgs), 3)
        self.assertEqual([m["role"] for m in msgs], ["customer", "acknowledgement", "agent"])
        self.assertIn("[POL-SHIP-001]", msgs[2]["content"])

        replied_question = next(
            (msgs[i] for i in range(1, -1, -1) if msgs[i]["role"] == "customer"),
            None,
        )
        self.assertIsNotNone(replied_question)
        self.assertEqual(replied_question["content"], customer_question)

    def test_fifo_draft_queue_prevents_overwrite_race_condition(self):
        """Task 3: Rapid Q1 + Q2 must keep Draft 1 at FIFO head and advance cleanly to Draft 2 on approval."""
        sess = "sess_race_fifo"
        self.store.get_or_create(sess, "CUST-1001")

        self.store.add_turn_record(sess, role="customer", content="Câu hỏi 1: Đơn ORD-1001 khi nào giao?")
        self.store.set_copilot_draft(
            sess,
            "Bản nháp 1 cho ORD-1001",
            {"interaction_id": "int_q1", "draft_text": "Bản nháp 1 cho ORD-1001"},
            interaction_id="int_q1",
            customer_question="Câu hỏi 1: Đơn ORD-1001 khi nào giao?",
        )

        # Q2 arrives before Staff approves Draft 1
        self.store.add_turn_record(sess, role="customer", content="Câu hỏi 2: Chính sách đổi trả mấy ngày?")
        self.store.set_copilot_draft(
            sess,
            "Bản nháp 2 đổi trả 30 ngày",
            {"interaction_id": "int_q2", "draft_text": "Bản nháp 2 đổi trả 30 ngày"},
            interaction_id="int_q2",
            customer_question="Câu hỏi 2: Chính sách đổi trả mấy ngày?",
        )

        details_mid = self.store.get_full_session_details(sess)
        self.assertEqual(details_mid["copilotDraft"], "Bản nháp 1 cho ORD-1001")
        self.assertEqual(len(details_mid["pendingDrafts"]), 2)
        self.assertEqual([d["interactionId"] for d in details_mid["pendingDrafts"]], ["int_q1", "int_q2"])

        # Staff approves Draft 1 -> Draft 2 must advance automatically to head
        self.store.add_turn_record(
            sess,
            role="agent",
            content="Bản nháp 1 cho ORD-1001",
            is_acknowledgement=False,
            interaction_id="int_q1",
        )
        details_after_q1 = self.store.get_full_session_details(sess)
        self.assertEqual(len(details_after_q1["pendingDrafts"]), 1)
        self.assertEqual(details_after_q1["pendingDrafts"][0]["interactionId"], "int_q2")
        self.assertEqual(details_after_q1["copilotDraft"], "Bản nháp 2 đổi trả 30 ngày")

        # Staff dismisses Draft 2 -> Queue empties cleanly
        self.store.clear_copilot_draft(sess, interaction_id="int_q2")
        details_end = self.store.get_full_session_details(sess)
        self.assertEqual(details_end["pendingDrafts"], [])
        self.assertEqual(details_end["copilotDraft"], "")


if __name__ == "__main__":
    unittest.main()
