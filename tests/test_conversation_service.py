"""Unit tests for Conversation Service modules."""
import unittest

from contracts.schemas import (
    ConversationTurnItem,
    GuardrailResult,
    IntentPredictionResponse,
    RetrievedDocument,
)
from services.conversation_service.src.dialogue_state.state import ConversationState, StateStore
from services.conversation_service.src.dialogue_state.tracker import IntentTracker
from services.conversation_service.src.input_pipeline.fact_extractor import extract_facts
from services.conversation_service.src.input_pipeline.input_classifier import InputClassifier
from services.conversation_service.src.memory.context_summary import ContextSummaryManager
from services.conversation_service.src.memory.turn_buffer import TurnBuffer
from services.conversation_service.src.policies.response_dispatcher import ResponsePolicyDispatcher


class TestFactExtractor(unittest.TestCase):
    def test_extract_order_id(self):
        query = "Cho mình hỏi đơn hàng ORD-1002 đến đâu rồi ạ?"
        facts = extract_facts(query)
        self.assertEqual(facts.get("order_id"), "ORD-1002")

    def test_extract_order_id_lowercase(self):
        query = "mã đơn là ord-9988 nhé"
        facts = extract_facts(query)
        self.assertEqual(facts.get("order_id"), "ORD-9988")

    def test_extract_phone_number(self):
        query = "Số điện thoại nhận hàng là 0912345678"
        facts = extract_facts(query)
        self.assertEqual(facts.get("phone_number"), "0912345678")


class TestInputClassifier(unittest.TestCase):
    def setUp(self):
        self.classifier = InputClassifier()

    def test_tier1_chitchat(self):
        category = self.classifier.classify_fast_tier("dạ vâng cảm ơn shop", {})
        self.assertEqual(category, "chitchat")

    def test_tier1_fact_supplement(self):
        category = self.classifier.classify_fast_tier("ORD-1003", {"order_id": "ORD-1003"})
        self.assertEqual(category, "fact_supplement")

    def test_tier1_negation_reversal(self):
        category = self.classifier.classify_fast_tier("thôi không hủy nữa", {})
        self.assertEqual(category, "negation_reversal")


class TestDialogueTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = IntentTracker()
        self.state = ConversationState(session_id="test_ses")

    def test_chitchat_bypass(self):
        self.state.active_intent = "check_order_status"
        self.state.awaiting_slot = "order_id"
        self.state.facts["order_id"] = "ORD-1001"

        new_intent, confidence, switched = self.tracker.resolve_intent_transition(
            user_text="dạ vâng cảm ơn shop",
            input_type="chitchat",
            extracted_facts={},
            ml_intent_resp=None,
            state=self.state,
        )
        self.assertEqual(new_intent, "check_order_status")
        self.assertFalse(switched)

    def test_slot_extension_carryover(self):
        self.state.active_intent = "check_order_status"
        self.state.awaiting_slot = "order_id"

        new_intent, confidence, switched = self.tracker.resolve_intent_transition(
            user_text="ORD-1003",
            input_type="fact_supplement",
            extracted_facts={"order_id": "ORD-1003"},
            ml_intent_resp=None,
            state=self.state,
        )
        self.assertEqual(new_intent, "check_order_status")
        self.assertFalse(switched)

    def test_negation_reversal_switch(self):
        self.state.active_intent = "cancel_order"
        self.state.awaiting_slot = "order_id"

        new_intent, confidence, switched = self.tracker.resolve_intent_transition(
            user_text="thôi không hủy nữa đâu",
            input_type="negation_reversal",
            extracted_facts={},
            ml_intent_resp=None,
            state=self.state,
        )
        self.assertEqual(new_intent, "delivery_time")
        self.assertTrue(switched)


class TestMemoryAndSummary(unittest.TestCase):
    def test_turn_buffer_and_summary(self):
        buffer = TurnBuffer(max_turns=2)
        turns = [
            ConversationTurnItem(turn_id=1, customer_query="Tôi muốn tra đơn hàng", agent_response="Vui lòng cung cấp mã đơn"),
            ConversationTurnItem(turn_id=2, customer_query="Mã đơn ORD-1003", agent_response="Đơn đang được giao"),
            ConversationTurnItem(turn_id=3, customer_query="Dạ vâng cảm ơn shop", agent_response="Dạ không có gì ạ"),
        ]

        recent = buffer.get_recent_turns(turns)
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0].turn_id, 2)

        context_str = buffer.format_as_context(turns)
        self.assertIn("ORD-1003", context_str)

        state = ConversationState(session_id="test_ses", customer_id="KH-01")
        state.active_order_id = "ORD-1003"
        state.active_intent = "check_order_status"

        summary = ContextSummaryManager.build_summary(
            state=state,
            order_data={"order_id": "ORD-1003", "order_status": "DELIVERING", "total_amount": 250000},
        )
        self.assertIn("ORD-1003", summary)
        self.assertIn("check_order_status", summary)
        self.assertIn("DELIVERING", summary)


from services.conversation_service.src.policies.response_dispatcher import ResponsePolicyDispatcher


class TestResponseDispatcher(unittest.TestCase):
    def test_chitchat_dispatch(self):
        intent = IntentPredictionResponse(intent="chitchat", confidence=0.95, is_in_scope=True, all_probabilities={})
        guard, draft, suggested, guidance, mode = ResponsePolicyDispatcher.dispatch(
            user_query="dạ vâng cảm ơn shop",
            input_type="chitchat",
            intent_resp=intent,
            order_data=None,
            citations=[],
            has_expired_policy=False,
            is_live_chat=False,
        )
        self.assertEqual(mode, "chitchat_instant")
        self.assertIn("Dạ không có gì ạ", suggested)
        self.assertEqual(guard.action_type, "CHITCHAT_RESPONSE")

    def test_financial_risk_dispatch(self):
        intent = IntentPredictionResponse(intent="request_refund", confidence=0.92, is_in_scope=True, all_probabilities={})
        guard, draft, suggested, guidance, mode = ResponsePolicyDispatcher.dispatch(
            user_query="Tôi muốn hoàn tiền",
            input_type="query_with_intent",
            intent_resp=intent,
            order_data={"order_id": "ORD-1002", "total_amount": 500000},
            citations=[],
            has_expired_policy=False,
            is_live_chat=False,
        )
        self.assertEqual(mode, "blocked_financial")
        self.assertEqual(guard.action_type, "DIRECT_REFUND_FORM")
        self.assertIn("ORD-1002", suggested)
        self.assertIn("đối soát", guidance.lower())

    def test_low_confidence_dispatch(self):
        intent = IntentPredictionResponse(intent="general_inquiry", confidence=0.45, is_in_scope=False, all_probabilities={})
        guard, draft, suggested, guidance, mode = ResponsePolicyDispatcher.dispatch(
            user_query="cái này làm sao",
            input_type="query_with_intent",
            intent_resp=intent,
            order_data=None,
            citations=[],
            has_expired_policy=False,
            is_live_chat=False,
        )
        self.assertEqual(mode, "low_confidence_abstain")
        self.assertEqual(guard.action_type, "ESCALATE_HUMAN")
        self.assertIn("tự gõ câu trả lời", guidance)


from services.conversation_service.src.policies.acknowledgement import CustomerAcknowledgementEngine
from services.conversation_service.src.policies.copilot_draft_engine import CopilotDraftEngine


class TestAcknowledgementAndDraftEngines(unittest.TestCase):
    def test_customer_acknowledgement_track_order(self):
        ack = CustomerAcknowledgementEngine.generate(
            intent="track_order",
            facts={"order_id": "ORD-9988"},
            user_query="Kiểm tra đơn hàng ORD-9988",
        )
        self.assertIn("ORD-9988", ack)
        self.assertIn("ghi nhận", ack)

    def test_customer_acknowledgement_return_product(self):
        ack = CustomerAcknowledgementEngine.generate(
            intent="return_product",
            facts={"product_name": "tai nghe Bluetooth", "issue": "bị rè"},
            user_query="Tai nghe bị rè có đổi được không?",
        )
        self.assertIn("tai nghe Bluetooth", ack)
        self.assertIn("rất tiếc", ack)

    def test_copilot_draft_engine_prompt_packaging(self):
        prompt = CopilotDraftEngine.build_full_context_prompt(
            user_query="Kiểm tra đơn hàng ORD-1003",
            intent="track_order",
            facts={"order_id": "ORD-1003"},
            order_data={
                "order_id": "ORD-1003",
                "customer_name": "Lê Văn C",
                "status": "Đang giao hàng",
                "total_amount": 250000,
                "payment_method": "COD",
                "shipper_name": "Nguyễn Văn Shipper",
                "shipper_phone": "0988776655",
                "estimated_delivery": "hôm nay trước 18h",
            },
            context_summary="Khách hàng hỏi đơn ORD-1003",
            recent_turns_text="Khách hàng: tra đơn giúp mình",
            citations=[RetrievedDocument(doc_id="POL-ORD-001", title="Giao hàng", content="Giao trong 24h", version="1.0", is_active=True)],
        )
        self.assertIn("ORD-1003", prompt)
        self.assertIn("Nguyễn Văn Shipper", prompt)
        self.assertIn("POL-ORD-001", prompt)
        self.assertIn("Dạ em chào anh/chị", prompt)

    def test_copilot_draft_engine_fallback_generation(self):
        # Even without Gemini API, semantic fallback produces polite agent draft
        draft = CopilotDraftEngine._build_semantic_fallback_draft(
            user_query="Kiểm tra đơn hàng ORD-1003",
            intent="track_order",
            facts={"order_id": "ORD-1003"},
            order_data={
                "order_id": "ORD-1003",
                "shipper_name": "Bưu tá A",
                "shipper_phone": "0912345678",
                "status": "đang được giao",
                "estimated_delivery": "trước 18h",
            },
            citations=[RetrievedDocument(doc_id="POL-ORD-001", title="Giao hàng", content="...", version="1.0", is_active=True)],
        )
        self.assertIn("Dạ em chào anh/chị", draft)
        self.assertIn("ORD-1003", draft)
        self.assertIn("POL-ORD-001", draft)


if __name__ == "__main__":
    unittest.main()
