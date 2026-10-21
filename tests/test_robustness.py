"""Robustness tests: typo queries, ambiguous input, expired policy traps, and out-of-scope intent handling."""
from pathlib import Path
import sys
import unittest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.gateway.src.config import FINANCIAL_INTENTS
from services.gateway.src.guardrails import (
    evaluate_financial_guard,
    evaluate_intent_guard,
    evaluate_policy_guard,
)
from services.intent_service.src.predictor import IntentPredictor
from services.rag_service.src.indexer import PolicyVectorIndexer
from services.rag_service.src.retriever import PolicyRetriever


class TestRobustness(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        model_path = ROOT_DIR / "artifacts" / "models" / "intent_model.pkl"
        cls.predictor = IntentPredictor(model_path)

        index_path = ROOT_DIR / "artifacts" / "vector_store" / "policy_index.pkl"
        cls.indexer = PolicyVectorIndexer()
        cls.indexer.load(index_path)
        cls.retriever = PolicyRetriever(cls.indexer)

    def test_out_of_scope_query_abstains(self):
        """Query outside supported e-commerce scope should abstain with ESCALATE_HUMAN."""
        query = "Thời tiết hôm nay ở Hà Nội thế nào?"
        pred = self.predictor.predict(query)
        res = evaluate_intent_guard(pred)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")

    def test_human_agent_explicit_escalation(self):
        """Query explicitly asking for human support escalates without calling LLM."""
        query = "I want to speak with a human agent"
        pred = self.predictor.predict(query)
        self.assertEqual(pred.intent, "human_agent")
        res = evaluate_intent_guard(pred)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")

    def test_financial_intents_intercepted(self):
        """Financial operations (refund/payment issue) must trigger DIRECT_REFUND_FORM."""
        for intent in FINANCIAL_INTENTS:
            res = evaluate_financial_guard(intent)
            self.assertIsNotNone(res)
            self.assertFalse(res.allow_llm)
            self.assertEqual(res.action_type, "DIRECT_REFUND_FORM")

    def test_expired_warranty_policy_trap_blocked(self):
        """Retrieval of expired policy (e.g. POL-WARRANTY-OLD) must block LLM draft generation."""
        query = "Chính sách bảo hành cũ trước năm 2024 như thế nào"
        docs = self.retriever.retrieve(query, top_k=2, filter_active_only=False)
        self.assertTrue(len(docs) > 0)
        has_inactive = any(not d.is_active for d in docs)
        self.assertTrue(has_inactive, "Retrieved docs should contain expired policy trap")

        res = evaluate_policy_guard(docs)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")

    def test_ambiguous_low_confidence_abstains(self):
        """Ambiguous or unaccented queries with confidence < 0.60 must trigger ESCALATE_HUMAN."""
        query = "doi tra hang trong bao lau"
        pred = self.predictor.predict(query)
        self.assertLess(pred.confidence, 0.60)
        res = evaluate_intent_guard(pred)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")

    def test_in_scope_phrased_query(self):
        """Standard phrased customer inquiry within operational scope."""
        query = "I want to track my order status"
        pred = self.predictor.predict(query)
        self.assertTrue(pred.is_in_scope)
        self.assertEqual(pred.intent, "track_order")
        self.assertGreaterEqual(pred.confidence, 0.60)


if __name__ == "__main__":
    unittest.main()
