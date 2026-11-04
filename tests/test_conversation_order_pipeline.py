"""Unit tests for Refactored Conversation Service Order Pipeline & Policy Responses."""
import unittest

from services.conversation_service.src.input_pipeline.order_matcher import (
    RuleOrderMatcher,
    HybridOrderMatcher,
    extract_entities_from_text,
    get_order_matcher,
)
from services.conversation_service.src.input_pipeline.fact_extractor import extract_facts
from services.conversation_service.src.tools.order_tools import OrderTools
from services.conversation_service.src.policies.acknowledgement import CustomerAcknowledgementEngine
from services.conversation_service.src.policies.copilot_draft_engine import CopilotDraftEngine


class TestConversationOrderPipeline(unittest.TestCase):
    def setUp(self):
        self.order_tools = OrderTools()
        self.order_matcher = get_order_matcher(mode="rule")

    def test_extract_order_id_regex_formats(self):
        """Test extraction across multiple Vietnamese and standard order ID formats."""
        cases = [
            ("Cho mình hỏi đơn #ORD-1002 giao chưa", "ORD-1002"),
            ("Tra cứu mã đơn ORD-5541 giúp tôi", "ORD-5541"),
            ("Kiểm tra đơn hàng số 1003", "ORD-1003"),
            ("mã đơn #9921", "ORD-9921"),
        ]
        for query, expected_id in cases:
            entities = extract_entities_from_text(query)
            self.assertEqual(entities.get("order_id"), expected_id, f"Failed on: {query}")

    def test_fact_extractor_integration(self):
        """Verify fact_extractor correctly captures order_id into facts dict."""
        query = "Em ơi kiểm tra đơn #ORD-1001 giúp anh với SĐT 0988123456"
        facts = extract_facts(query)
        self.assertEqual(facts.get("order_id"), "ORD-1001")
        self.assertEqual(facts.get("phone"), "0988123456")

    def test_order_tools_lookup(self):
        """Verify order_tools retrieves order and formats Vietnamese summary."""
        order = self.order_tools.get_order_by_id("ORD-1001")
        self.assertIsNotNone(order)
        self.assertEqual(order.get("order_id"), "ORD-1001")

        summary = self.order_tools.format_order_summary(order)
        self.assertIn("ORD-1001", summary)
        self.assertIn("trạng thái", summary.lower())

    def test_acknowledgement_when_order_id_missing(self):
        """Verify user request: When user inquires about order without ID, prompt for order ID or order info."""
        ack = CustomerAcknowledgementEngine.generate(
            intent="track_order",
            facts={},
            user_query="Đơn hàng của tôi khi nào giao tới nơi",
        )
        self.assertIn("Bạn vui lòng cho shop xin mã đơn hàng hoặc thông tin đơn hàng nhé", ack)

    def test_draft_engine_fallback_when_order_id_missing(self):
        """Verify fallback draft engine also prompts for order ID or order info when order_data is missing."""
        draft = CopilotDraftEngine._build_semantic_fallback_draft(
            user_query="Bao giờ hàng tới nơi shop ơi",
            intent="track_order",
            facts={},
            order_data=None,
            citations=[],
        )
        self.assertIn("Bạn vui lòng cho shop xin mã đơn hàng hoặc thông tin đơn hàng nhé", draft)

    def test_acknowledgement_when_order_id_present(self):
        """Verify acknowledgement includes order_id when present in facts."""
        ack = CustomerAcknowledgementEngine.generate(
            intent="track_order",
            facts={"order_id": "ORD-1001"},
            user_query="Kiểm tra đơn ORD-1001 giúp mình",
        )
        self.assertIn("ORD-1001", ack)
        self.assertIn("kết nối hệ thống bưu tá", ack)


if __name__ == "__main__":
    unittest.main()

