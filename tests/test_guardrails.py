"""End-to-end integration test verifying Gateway with live mock services or running components."""
import unittest
import asyncio
from contracts.schemas import (
    IntentPredictionResponse,
    RetrievedDocument,
    QueryRequest,
    GuardrailResult,
)
from services.gateway.src.guardrails import (
    evaluate_intent_guard,
    evaluate_financial_guard,
    evaluate_policy_guard,
)


class TestGatewayGuardrails(unittest.TestCase):
    def test_low_confidence_abstains(self):
        """Intent with confidence < 0.60 must trigger ESCALATE_HUMAN."""
        intent = IntentPredictionResponse(
            intent="track_order",
            confidence=0.45,
            is_in_scope=True,
            all_probabilities={"track_order": 0.45},
        )
        res = evaluate_intent_guard(intent)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")

    def test_out_of_scope_abstains(self):
        """Intent not in operational scope must trigger ESCALATE_HUMAN."""
        intent = IntentPredictionResponse(
            intent="unknown_query",
            confidence=0.95,
            is_in_scope=False,
            all_probabilities={"unknown_query": 0.95},
        )
        res = evaluate_intent_guard(intent)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")

    def test_human_agent_intent_escalates(self):
        """Explicit human agent request must escalate without LLM."""
        intent = IntentPredictionResponse(
            intent="human_agent",
            confidence=0.98,
            is_in_scope=True,
            all_probabilities={"human_agent": 0.98},
        )
        res = evaluate_intent_guard(intent)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")

    def test_financial_guard_intercepts_refund(self):
        """Refund intent must trigger DIRECT_REFUND_FORM."""
        res = evaluate_financial_guard("request_refund")
        self.assertIsNotNone(res)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "DIRECT_REFUND_FORM")

    def test_policy_guard_blocks_expired_documents(self):
        """If citations contain expired document, policy guard blocks draft generation."""
        citations = [
            RetrievedDocument(
                doc_id="POL-WARRANTY-OLD",
                title="Bảo hành cũ",
                content="Chính sách bảo hành cũ",
                version="0.1",
                is_active=False,
            )
        ]
        res = evaluate_policy_guard(citations)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")

    def test_policy_guard_allows_active_documents(self):
        """Active documents allow LLM draft generation."""
        citations = [
            RetrievedDocument(
                doc_id="POL-RET-002",
                title="Chính sách đổi trả",
                content="Đổi trả trong vòng 30 ngày",
                version="2.0",
                is_active=True,
            )
        ]
        res = evaluate_policy_guard(citations)
        self.assertTrue(res.allow_llm)
        self.assertEqual(res.action_type, "PROCEED_TO_LLM")


if __name__ == "__main__":
    unittest.main()
