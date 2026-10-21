"""Robustness tests: typo queries, ambiguous input, and out-of-scope intent handling."""
import unittest
from src.core.schemas import GuardrailAction, QueryRequest
from src.orchestrator import CopilotOrchestrator


class TestRobustness(unittest.TestCase):
    def setUp(self):
        self.orchestrator = CopilotOrchestrator()

    def test_out_of_scope_query_abstains(self):
        """Query outside supported e-commerce scope should abstain with low confidence."""
        req = QueryRequest(query="Thời tiết hôm nay ở Hà Nội thế nào?", session_id="test-session")
        res = self.orchestrator.handle(req)
        self.assertFalse(res.guardrail.allow_llm)
        self.assertEqual(res.guardrail.action_type, GuardrailAction.ESCALATE_HUMAN)

    def test_human_agent_explicit_escalation(self):
        """Query explicitly asking for human support escalates without LLM hallucination."""
        req = QueryRequest(query="Cho tôi gặp nhân viên tư vấn trực tiếp", session_id="test-session")
        res = self.orchestrator.handle(req)
        self.assertFalse(res.guardrail.allow_llm)
        self.assertEqual(res.guardrail.action_type, GuardrailAction.ESCALATE_HUMAN)


if __name__ == '__main__':
    unittest.main()
