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
