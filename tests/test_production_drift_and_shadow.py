"""Layer 1: Testing in Production — Data/Concept Drift Detection & Shadow Deployment Evaluation.
Aligns with CMU MLIP Chapters 16 (Data Quality / Drift) & 19 (Testing and Experimenting in Production):
1. Verifies healthy production telemetry produces 0 false-positive drift alerts.
2. Verifies Data Drift alert when Out-of-Scope (`out_of_scope`) queries spike (e.g., new seasonal campaign).
3. Verifies Concept Drift alert when average staff edit distance (`NED`) spikes above baseline.
4. Verifies Automation Bias Drift alert when staff rubber-stamping rate (< 1.5s approvals) exceeds threshold.
5. Verifies Shadow Deployment Evaluator (`/audit/shadow/evaluate` & `evaluate_shadow_comparison`) accurately
   compares candidate model drafts against primary production drafts without impacting customers.
"""
from pathlib import Path
import tempfile
import unittest
from fastapi.testclient import TestClient

from services.telemetry_service.src.main import app as telemetry_app
from services.telemetry_service.src.metrics import (
    detect_telemetry_drift,
    evaluate_shadow_comparison,
)


class TestProductionDriftAndShadow(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(telemetry_app)

    def test_healthy_telemetry_no_drift(self):
        """Normal in-scope traffic with low staff edit distance and careful review should trigger 0 alerts."""
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
        """Spikes in OOS queries, heavy staff rewrites (NED), and <1.5s rubber-stamping must trigger alerts."""
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

    def test_shadow_deployment_comparison_and_api(self):
        """Shadow mode evaluator must promote safe, well-cited candidate drafts and reject broken ones."""
        primary = "Dạ đơn hàng ORD-1100 của anh/chị đang được giao theo quy định [POL-SHIP-001] ạ."
        shadow_good = (
            "Dạ chào anh/chị, đơn hàng ORD-1100 đang trên đường vận chuyển và sẽ giao theo chuẩn [POL-SHIP-001] nhé ạ."
        )
        shadow_bad = "Dạ đơn hàng đang giao ạ."  # Missing ORD-1100 and missing [POL-SHIP-001]

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

        # Test HTTP endpoint on telemetry_service
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

        drift_http = self.client.get("/audit/drift")
        self.assertEqual(drift_http.status_code, 200)
        self.assertIn("drift_detected", drift_http.json())


if __name__ == "__main__":
    unittest.main()
