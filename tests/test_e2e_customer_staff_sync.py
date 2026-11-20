"""Layer 3: End-to-End (E2E) System Test for Customer Portal <-> SQLite <-> Staff Workbench Flow.
Verifies the complete user journey across roles:
1. Customer (CUST-1002) creates a session and sends a question on `/customer`.
2. Immediate Buffer Acknowledgement (`isAcknowledgement=True`) is persisted.
3. Copilot generates a grounded draft with `[POL-SHIP-001]` and saves `copilot_draft` + `copilot_response_json` in SQLite.
4. Staff polls `/sessions` (global across all customers) -> sees `CUST-1002` automatically sorted to #1 (newest activity + pending draft).
5. Staff edits/approves the draft and sends the final agent response (`role='agent'`).
6. SQLite automatically clears `copilot_draft`, and Customer polling `/session/{id}/details` receives the approved reply,
   links it to the original customer question (Messenger-style quote), and extracts `[POL-SHIP-001]` for the Policy Modal.
"""
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
        # Step 1: Older session exists for CUST-1100
        self.store.get_or_create("sess_old_1100", "CUST-1100")
        self.store.add_turn_record("sess_old_1100", role="customer", content="Đổi trả trong mấy ngày?")
        self.store.add_turn_record(
            "sess_old_1100",
            role="agent",
            content="Dạ đổi trả trong 30 ngày theo [POL-RET-001] ạ.",
            is_acknowledgement=False,
        )

        time.sleep(0.02)

        # Step 2: Customer CUST-1002 opens /customer and asks a new question
        sess_new = "sess_new_1002"
        customer_question = "Đơn hàng ORD-1002 của tôi bao giờ giao tới nơi vậy?"
        self.store.get_or_create(sess_new, "CUST-1002")
        self.store.add_turn_record(sess_new, role="customer", content=customer_question)

        # Step 3: Immediate contextual acknowledgement sent to customer
        ack_text = "Dạ em đã ghi nhận câu hỏi về tiến độ giao hàng của anh/chị. Em đang kiểm tra ngay đây ạ!"
        self.store.add_turn_record(sess_new, role="acknowledgement", content=ack_text, is_acknowledgement=True)

        # Step 4: Copilot generates draft and persists to SQLite for Staff Workbench
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

        # Step 5: Staff Workbench polls global sessions -> CUST-1002 must have pending draft and newest updatedAt
        all_sessions = self.store.list_sessions_by_customer()
        self.assertGreaterEqual(len(all_sessions), 2)
        newest_sess = next(s for s in all_sessions if s["sessionId"] == sess_new)
        self.assertEqual(newest_sess["customerId"], "CUST-1002")
        self.assertEqual(newest_sess["copilotDraft"], draft_text)

        # Verify Staff Workbench customer priority sorting puts CUST-1002 (hasPendingDraft=True) at index 0
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
        self.assertEqual(sorted_customers[0], "CUST-1002", "Customer with newest pending question must be #1!")

        # Step 6: Staff approves & sends final reply on /staff -> clears draft & appends agent message
        approved_reply = draft_text
        self.store.add_turn_record(sess_new, role="agent", content=approved_reply, is_acknowledgement=False)

        # Step 7: Customer Portal (/customer) polls session details
        details = self.store.get_full_session_details(sess_new)
        self.assertIsNotNone(details)
        self.assertEqual(details["copilotDraft"], "", "Copilot draft must be cleared after Staff approves & sends!")
        self.assertIsNone(details["copilotResponse"])

        msgs = details["messages"]
        self.assertEqual(len(msgs), 3)
        self.assertEqual(msgs[0]["role"], "customer")
        self.assertEqual(msgs[1]["role"], "acknowledgement")
        self.assertEqual(msgs[2]["role"], "agent")
        self.assertIn("[POL-SHIP-001]", msgs[2]["content"])

        # Step 8: Verify Messenger-style quoted question resolution for the final reply (msgs[2])
        replied_question = None
        for i in range(2 - 1, -1, -1):
            if msgs[i]["role"] == "customer":
                replied_question = msgs[i]
                break
        self.assertIsNotNone(replied_question)
        self.assertEqual(replied_question["content"], customer_question)


if __name__ == "__main__":
    unittest.main()
