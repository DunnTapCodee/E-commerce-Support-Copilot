"""Layer 2: Concurrency & WAL Stress Tests on PersistentStateStore & TelemetryRepository."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import gc
from pathlib import Path
import tempfile
import time
from typing import List
import unittest

from contracts.schemas import AuditLogCreate, HumanActionUpdate
from services.conversation_service.src.dialogue_state.sqlite_state_store import (
    PersistentStateStore,
    init_conversation_db,
)
from services.telemetry_service.src.database import init_db
from services.telemetry_service.src.repository import TelemetryRepository

ROOT_DIR = Path(__file__).resolve().parent.parent
MOCK_ORDERS_PATH = ROOT_DIR / "data" / "mock_orders.json"


class TestLoadAndConcurrency(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.conv_db_path = Path(self.tmp_dir.name) / "load_conversations.sqlite3"
        self.tel_db_path = Path(self.tmp_dir.name) / "load_telemetry.sqlite3"

        init_conversation_db(self.conv_db_path)
        init_db(self.tel_db_path, MOCK_ORDERS_PATH)

        self.conv_store = PersistentStateStore(self.conv_db_path)
        self.tel_repo = TelemetryRepository(self.tel_db_path, MOCK_ORDERS_PATH)

    def tearDown(self):
        self.conv_store = None
        self.tel_repo = None
        gc.collect()
        self.tmp_dir.cleanup()

    def test_concurrent_30_sessions_chat_and_telemetry_writes(self):
        """30 concurrent worker tasks reading/writing SQLite WAL databases must succeed without locking errors."""
        num_workers = 30
        latencies_ms: List[float] = []
        errors: List[str] = []

        def worker_task(worker_id: int) -> float:
            t0 = time.perf_counter()
            sess_id = f"sess_load_{worker_id}"
            cust_id = f"CUST-{1001 + (worker_id % 4)}"
            int_id = f"int_load_{worker_id}"

            self.conv_store.get_or_create(sess_id, cust_id)
            self.conv_store.add_turn_record(
                sess_id,
                role="customer",
                content=f"Kiểm tra đơn hàng ORD-1001 từ worker {worker_id}",
                is_acknowledgement=False,
            )

            draft = f"Dạ đơn hàng ORD-1001 đang xử lý theo [POL-ORD-001] (worker {worker_id})."
            self.conv_store.set_copilot_draft(sess_id, draft, {"draft_text": draft})

            all_sess = self.conv_store.list_sessions()
            assert len(all_sess) >= 1

            self.tel_repo.insert_audit_log(
                AuditLogCreate(
                    interaction_id=int_id,
                    customer_query=f"Kiểm tra đơn hàng worker {worker_id}",
                    predicted_intent="track_order",
                    intent_confidence=0.92,
                    guardrail_action="PROCEED_TO_LLM",
                    retrieved_doc_ids="POL-ORD-001",
                    raw_draft_text=draft,
                    latency_ms=15,
                )
            )
            self.tel_repo.update_human_action(
                HumanActionUpdate(
                    interaction_id=int_id,
                    action="APPROVE",
                    final_text=draft,
                    handling_time_ms=3500,
                )
            )

            self.conv_store.add_turn_record(sess_id, role="agent", content=draft, is_acknowledgement=False)
            details = self.conv_store.get_full_session_details(sess_id)
            assert details is not None and len(details["messages"]) == 2

            return (time.perf_counter() - t0) * 1000.0

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(worker_task, i) for i in range(num_workers)]
            for fut in as_completed(futures):
                try:
                    latencies_ms.append(fut.result())
                except Exception as exc:
                    errors.append(str(exc))

        self.assertEqual(len(errors), 0, f"Concurrent SQLite WAL load test had errors: {errors}")
        self.assertEqual(len(latencies_ms), num_workers)

        sorted_lat = sorted(latencies_ms)
        p95_ms = sorted_lat[int(0.95 * len(sorted_lat)) - 1]
        self.assertLess(p95_ms, 2000.0, f"P95 concurrency latency too high: {p95_ms:.1f}ms")


if __name__ == "__main__":
    unittest.main()
