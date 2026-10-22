"""End-to-end integration test verifying Gateway with live mock services or running components."""
import unittest
import asyncio
from datetime import date
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
    evaluate_response_faithfulness,
    check_temporal_validity,
    SpecializedGuardrailAdapter,
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

    def test_financial_guard_intercepts_payment_issue(self):
        """Payment issue intent must trigger DIRECT_REFUND_FORM."""
        res = evaluate_financial_guard("payment_issue")
        self.assertIsNotNone(res)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "DIRECT_REFUND_FORM")

    def test_policy_guard_blocks_expired_documents_by_flag(self):
        """If citations contain inactive document (is_active=False), policy guard blocks draft generation."""
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

    def test_temporal_policy_guard_blocks_expired_date(self):
        """Even if is_active is erroneously True, expired expiration_date must be blocked."""
        ref_today = date(2026, 10, 22)
        citations = [
            RetrievedDocument(
                doc_id="POL-PROMO-OLD",
                title="Chương trình hoàn xu Tết 2023",
                content="Hoàn xu 50% cho dịp Tết 2023.",
                version="0.5",
                is_active=True,  # Test trap: marked True but expired temporally!
                effective_date="2023-01-01",
                expiration_date="2023-01-31",
            )
        ]
        res = evaluate_policy_guard(citations, reference_date=ref_today)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")
        self.assertEqual(res.temporal_status, "EXPIRED")
        self.assertIn("Temporal Policy Guard", res.reason)

    def test_temporal_policy_guard_blocks_future_effective_date(self):
        """Policies with effective_date in the future must not be applied yet."""
        ref_today = date(2026, 10, 22)
        citations = [
            RetrievedDocument(
                doc_id="POL-FUTURE-2030",
                title="Chính sách dự kiến 2030",
                content="Chính sách mới chưa ban hành.",
                version="3.0",
                is_active=True,
                effective_date="2030-01-01",
                expiration_date="2035-12-31",
            )
        ]
        res = evaluate_policy_guard(citations, reference_date=ref_today)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")
        self.assertEqual(res.temporal_status, "NOT_YET_EFFECTIVE")

    def test_policy_guard_allows_active_and_temporally_valid_documents(self):
        """Active documents within valid temporal window allow LLM draft generation."""
        ref_today = date(2026, 10, 22)
        citations = [
            RetrievedDocument(
                doc_id="POL-RET-001",
                title="Chính sách đổi trả tiêu chuẩn",
                content="Đổi trả trong vòng 30 ngày cho Tiki Trading và 7 ngày cho sàn đối tác.",
                version="2.0",
                is_active=True,
                effective_date="2024-01-01",
                expiration_date="2030-12-31",
            )
        ]
        res = evaluate_policy_guard(citations, reference_date=ref_today)
        self.assertTrue(res.allow_llm)
        self.assertEqual(res.action_type, "PROCEED_TO_LLM")
        self.assertEqual(res.temporal_status, "ACTIVE")

    def test_response_faithfulness_passes_grounded_draft(self):
        """LLM draft faithfully supported by retrieved policy must pass."""
        citations = [
            RetrievedDocument(
                doc_id="POL-RET-001",
                title="Chính sách đổi trả tiêu chuẩn",
                content="Khách hàng có thể đổi trả trong vòng 30 ngày đối với Tiki Trading hoặc 7 ngày đối với nhà bán đối tác.",
                version="2.0",
                is_active=True,
                effective_date="2024-01-01",
                expiration_date="2030-12-31",
            )
        ]
        draft_text = (
            "Chào bạn, theo chính sách [POL-RET-001], bạn có thể yêu cầu đổi trả "
            "trong vòng 30 ngày đối với sản phẩm Tiki Trading hoặc 7 ngày đối với nhà bán đối tác."
        )
        res = evaluate_response_faithfulness(draft_text, citations)
        self.assertTrue(res.allow_llm)
        self.assertEqual(res.action_type, "PROCEED_TO_LLM")
        self.assertFalse(res.hallucination_detected)
        self.assertGreaterEqual(res.faithfulness_score, 0.70)

    def test_response_faithfulness_blocks_hallucinated_draft(self):
        """LLM draft containing fabricated numbers/promises must be blocked."""
        citations = [
            RetrievedDocument(
                doc_id="POL-RET-001",
                title="Chính sách đổi trả tiêu chuẩn",
                content="Khách hàng có thể đổi trả trong vòng 30 ngày đối với Tiki Trading hoặc 7 ngày đối với nhà bán đối tác.",
                version="2.0",
                is_active=True,
                effective_date="2024-01-01",
                expiration_date="2030-12-31",
            )
        ]
        # Hallucinated draft: claims 90 days and 200% refund (not in policy!)
        hallucinated_draft = (
            "Chào bạn, Tiki hỗ trợ đổi trả sản phẩm thoải mái trong vòng 90 ngày "
            "và cam kết hoàn tiền 200% cho mọi trường hợp khách hàng không thích."
        )
        res = evaluate_response_faithfulness(hallucinated_draft, citations)
        self.assertFalse(res.allow_llm)
        self.assertEqual(res.action_type, "ESCALATE_HUMAN")
        self.assertTrue(res.hallucination_detected)
        self.assertIn("ảo giác", res.reason)

    def test_specialized_guardrail_adapter(self):
        """Test SpecializedGuardrailAdapter applies input, retrieval, and output rails."""
        adapter = SpecializedGuardrailAdapter(engine_type="native_nli")
        intent = IntentPredictionResponse(
            intent="track_order",
            confidence=0.92,
            is_in_scope=True,
            all_probabilities={"track_order": 0.92},
        )
        res_input = adapter.apply_input_rails("Theo dõi đơn", intent)
        self.assertTrue(res_input.allow_llm)

        citations = [
            RetrievedDocument(
                doc_id="POL-ORD-001",
                title="Tra cứu đơn hàng",
                content="Khách hàng tra cứu trạng thái đơn hàng trong mục Đơn hàng của tôi.",
                version="1.0",
                is_active=True,
                effective_date="2024-01-01",
                expiration_date="2030-12-31",
            )
        ]
        res_ret = adapter.apply_retrieval_rails(citations)
        self.assertTrue(res_ret.allow_llm)

        draft = "Bạn có thể vào mục Đơn hàng của tôi để tra cứu tình trạng đơn [POL-ORD-001]."
        res_out = adapter.apply_output_rails(draft, citations)
        self.assertTrue(res_out.allow_llm)


if __name__ == "__main__":
    unittest.main()

