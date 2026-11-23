"""Layer 1: Testing in Production — Data/Concept Drift Detection & Shadow Deployment Evaluation.

Isolated against tempfile.TemporaryDirectory() SQLite database so root copilot_telemetry.sqlite3
is never read or mutated. Also verifies HTTP GET /audit/drift reads repository `recent_records` properly.
"""
import gc
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from contracts.schemas import AuditLogCreate, HumanActionUpdate
from services.telemetry_service.src.database import init_db
import services.telemetry_service.src.main as telemetry_main
from services.telemetry_service.src.metrics import (
    detect_telemetry_drift,
    evaluate_shadow_comparison,
)
from services.telemetry_service.src.repository import TelemetryRepository

ROOT_DIR = Path(__file__).resolve().parent.parent
MOCK_ORDERS_PATH = ROOT_DIR / "data" / "mock_orders.json"


class TestProductionDriftAndShadow(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db_path = Path(self.tmp_dir.name) / "test_drift_telemetry.sqlite3"
        init_db(self.db_path, MOCK_ORDERS_PATH)
        self.tmp_repo = TelemetryRepository(self.db_path, MOCK_ORDERS_PATH)
        self.repo_patch = patch.object(telemetry_main, "repo_instance", self.tmp_repo)
        self.db_patch = patch.object(telemetry_main, "DB_PATH", self.db_path)
        self.repo_patch.start()
        self.db_patch.start()
        self.client = TestClient(telemetry_main.app)

    def tearDown(self):
        self.client.close()
        self.repo_patch.stop()
        self.db_patch.stop()
        self.tmp_repo = None
        gc.collect()
        self.tmp_dir.cleanup()

    def test_healthy_telemetry_no_drift(self):
        """Normal in-scope traffic with low staff edit distance and careful review triggers 0 alerts."""
        healthy_logs = [
            {
                "predicted_intent": "track_order",
                "intent_confidence": 0.94,
                "human_action": "APPROVE",
                "edit_distance": 0.0,
                "is_rubber_stamping": 0,
            },
            {
                "predicted_intent": "return_policy",
                "intent_confidence": 0.89,
                "human_action": "EDIT",
                "edit_distance": 0.18,
                "is_rubber_stamping": 0,
            },
            {
                "predicted_intent": "delivery_time",
                "intent_confidence": 0.91,
                "human_action": "APPROVE",
                "edit_distance": 0.05,
                "is_rubber_stamping": 0,
            },
        ]
        report = detect_telemetry_drift(healthy_logs)
        self.assertFalse(report["drift_detected"])
        self.assertEqual(len(report["alerts"]), 0)

    def test_detects_data_drift_concept_drift_and_automation_bias(self):
        """Spikes in OOS queries, heavy staff rewrites (NED), and <1.5s rubber-stamping trigger alerts."""
        drifted_logs = [
            {
                "predicted_intent": "out_of_scope",
                "intent_confidence": 0.40,
                "human_action": "EDIT",
                "edit_distance": 0.75,
                "is_rubber_stamping": 0,
            },
            {
                "predicted_intent": "out_of_scope",
                "intent_confidence": 0.35,
                "human_action": "EDIT",
                "edit_distance": 0.82,
                "is_rubber_stamping": 0,
            },
            {
                "predicted_intent": "track_order",
                "intent_confidence": 0.55,
                "human_action": "APPROVE",
                "edit_distance": 0.0,
                "is_rubber_stamping": 1,
            },
        ]
        report = detect_telemetry_drift(drifted_logs)
        self.assertTrue(report["drift_detected"])
        alert_text = " | ".join(report["alerts"])
        self.assertIn("DATA_DRIFT", alert_text)
        self.assertIn("COVARIATE_SHIFT", alert_text)
        self.assertIn("CONCEPT_DRIFT", alert_text)
        self.assertIn("AUTOMATION_BIAS_DRIFT", alert_text)

    def test_audit_drift_endpoint_reads_recent_records_from_isolated_db(self):
        """GET /audit/drift must read TelemetryRepository `recent_records` (non-empty) rather than missing key."""
        self.tmp_repo.insert_audit_log(
            AuditLogCreate(
                interaction_id="drift-1",
                customer_query="thời tiết hôm nay sao",
                predicted_intent="out_of_scope",
                intent_confidence=0.35,
                guardrail_action="ESCALATE_HUMAN",
                retrieved_doc_ids="",
                raw_draft_text="Dạ câu hỏi ngoài phạm vi hỗ trợ.",
                latency_ms=20,
            )
        )
        self.tmp_repo.update_human_action(
            HumanActionUpdate(
                interaction_id="drift-1",
                action="EDIT",
                final_text="Dạ em xin phép chuyển chuyên viên tư vấn giải đáp chi tiết cho anh/chị nhé.",
                handling_time_ms=5000,
            )
        )
        drift_http = self.client.get("/audit/drift")
        self.assertEqual(drift_http.status_code, 200)
        payload = drift_http.json()
        self.assertEqual(payload["sample_size"], 1)
        self.assertTrue(payload["drift_detected"])
        self.assertIn("DATA_DRIFT", " | ".join(payload["alerts"]))

    def test_shadow_deployment_comparison_and_api(self):
        """Shadow mode evaluator must promote safe, well-cited candidates and reject incomplete ones."""
        primary = "Dạ đơn hàng ORD-1100 của anh/chị đang được giao theo quy định [POL-SHIP-001] ạ."
        shadow_good = (
            "Dạ chào anh/chị, đơn hàng ORD-1100 đang trên đường vận chuyển và sẽ giao theo chuẩn [POL-SHIP-001] nhé ạ."
        )
        shadow_bad = "Dạ đơn hàng đang giao ạ."

        res_good = evaluate_shadow_comparison(
            primary_draft=primary,
            shadow_draft=shadow_good,
            expected_entities={"order_id": "ORD-1100"},
            primary_latency_ms=420.0,
            shadow_latency_ms=310.0,
        )
        self.assertTrue(res_good["shadow_passed_safety"])
        self.assertTrue(res_good["citation_match"])
        self.assertTrue(res_good["promotion_ready"])
        self.assertEqual(res_good["latency_delta_ms"], -110.0)

        res_bad = evaluate_shadow_comparison(
            primary_draft=primary,
            shadow_draft=shadow_bad,
            expected_entities={"order_id": "ORD-1100"},
        )
        self.assertFalse(res_bad["shadow_passed_safety"])
        self.assertFalse(res_bad["promotion_ready"])
        self.assertIn("order_id:ORD-1100", res_bad["shadow_missing_entities"])

        http_res = self.client.post(
            "/audit/shadow/evaluate",
            json={
                "interaction_id": "int_shadow_01",
                "primary_draft": primary,
                "shadow_draft": shadow_good,
                "expected_entities": {"order_id": "ORD-1100"},
                "primary_latency_ms": 400.0,
                "shadow_latency_ms": 280.0,
            },
        )
        self.assertEqual(http_res.status_code, 200)
        self.assertTrue(http_res.json()["promotion_ready"])


if __name__ == "__main__":
    unittest.main()
