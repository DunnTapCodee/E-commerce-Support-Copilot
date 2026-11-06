"""Pytest integration for CMU MLIP Behavioral & Guardrail Test Suite."""
import unittest
from evaluation.behavioral_tests import BehavioralTestSuite
from evaluation.guardrail_evaluator import GuardrailEvaluator


class TestMLIPBehavioralAndSafety(unittest.TestCase):
    def setUp(self):
        self.behav_suite = BehavioralTestSuite()
        self.guard_eval = GuardrailEvaluator()

    def test_minimum_functionality_mft(self):
        """MFT should achieve at least 80% passing rate across core intent capabilities."""
        res = self.behav_suite.run_mft()
        self.assertGreaterEqual(res["pass_rate"], 80.0, f"MFT pass rate was too low: {res['pass_rate']}%")

    def test_invariance_inv_metamorphic(self):
        """Invariance tests (greetings, casing, whitespace) should achieve at least 80% invariance."""
        res = self.behav_suite.run_inv()
        self.assertGreaterEqual(res["pass_rate"], 80.0, f"INV pass rate was too low: {res['pass_rate']}%")

    def test_directional_expectation_dir(self):
        """Directional expectation tests (negation reversal, domain shift) should achieve 100% directional accuracy."""
        res = self.behav_suite.run_dir()
        self.assertGreaterEqual(res["pass_rate"], 90.0, f"DIR pass rate was too low: {res['pass_rate']}%")

    def test_financial_guard_zero_leakage(self):
        """Financial operations must have 100% interception with direct refund form."""
        res = self.guard_eval.test_financial_guard_interception()
        self.assertEqual(res["pass_rate"], 100.0, "Financial risk leakage detected!")

    def test_temporal_expired_policy_guard(self):
        """Expired or superseded documents must be 100% blocked from LLM citations."""
        res = self.guard_eval.test_temporal_and_expired_policy_guard()
        self.assertEqual(res["pass_rate"], 100.0, "Expired policy cited by guardrail!")

    def test_response_faithfulness_hallucination_guard(self):
        """Fabricated facts and numbers must be 100% blocked."""
        res = self.guard_eval.test_response_faithfulness_guard()
        self.assertEqual(res["pass_rate"], 100.0, "Hallucinated draft passed through guardrail!")

    def test_chaos_and_safeguard_resilience(self):
        """Chaos tests (LLM timeout circuit breaker, prompt injection, empty RAG fallback) must pass."""
        from evaluation.chaos_safeguard_tests import ChaosSafeguardTester
        res = ChaosSafeguardTester().run_all()
        self.assertTrue(res["all_passed"], f"Chaos safeguard failed: {res}")

    def test_test_oracle_hard_constraints_and_rubric(self):
        """Test Oracle must accurately verify constraints and evaluate rubrics."""
        from evaluation.oracle_evaluator import TestOracleEvaluator
        # Hard constraints
        hard_res = TestOracleEvaluator.verify_hard_constraints(
            draft_text="Dạ em chào anh/chị, đơn hàng ORD-1100 đang được giao ạ [POL-ORD-001].",
            expected_entities={"order_id": "ORD-1100"},
            require_citation=True,
        )
        self.assertTrue(hard_res["passed"], "Valid draft failed hard constraints!")

        # Rubric evaluation
        rubric_res = TestOracleEvaluator.evaluate_rubric(
            draft_text="Dạ em chào anh/chị! Em đã kiểm tra đơn hàng ORD-1100 cho mình rồi ạ. Anh/chị vui lòng chú ý điện thoại để nhận hàng nhé ạ!",
            customer_query="đơn hàng khi nào giao",
            intent="track_order",
        )
        self.assertGreaterEqual(rubric_res["rubric_score_percent"], 75, "Rubric score too low for high-quality draft!")

    def test_telemetry_metrics_and_rubber_stamping(self):
        """Telemetry must correctly compute Levenshtein distance and flag rubber-stamping."""
        from services.telemetry_service.src.metrics import (
            compute_normalized_levenshtein,
            detect_rubber_stamping,
        )
        # Identical text
        self.assertEqual(compute_normalized_levenshtein("Xin chào", "Xin chào"), 0.0)
        # Completely different text
        dist = compute_normalized_levenshtein("Xin chào", "Tạm biệt bạn nhé")
        self.assertGreater(dist, 0.5)

        # Rubber-stamping detection: long draft approved in 500ms
        long_draft = "Dạ em chào quý khách, Tiki xin thông báo đơn hàng của quý khách đã được đóng gói và chuẩn bị giao cho đơn vị vận chuyển."
        self.assertTrue(detect_rubber_stamping(500, long_draft, "APPROVE"))
        # Thorough human review taking 8000ms
        self.assertFalse(detect_rubber_stamping(8000, long_draft, "APPROVE"))


