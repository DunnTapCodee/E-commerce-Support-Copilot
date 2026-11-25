"""Unit tests for Conversation Service modules."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path

_TMP_CONV_DIR = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
os.environ["CONVERSATIONS_DB_PATH"] = str(Path(_TMP_CONV_DIR.name) / "test_copilot_conversations.sqlite3")

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

    def test_long_fact_supplement_not_misclassified_as_new_question(self):
        """Task 2 Regression: Multi-word declarative entity replies (>4 words) must be fact_supplement, not new_question."""
        cases = [
            "Mã đơn của mình là ORD-1003 nhé",
            "Số điện thoại nhận hàng là 0912345678 ạ",
        ]
        for text in cases:
            facts = extract_facts(text)
            category = self.classifier.classify_fast_tier(text, facts, active_intent="track_order")
            self.assertEqual(category, "fact_supplement", f"Expected fact_supplement for: {text}")

        # Short declarative attribute reply during active intent resolves to fact_supplement in offline fallback
        self.assertEqual(
            self.classifier.classify_fast_tier("Màu đen size L nhé shop", {}, active_intent="return_product"),
            "fact_supplement",
        )

        # Greeting + question must still be new_question
        q_text = "Chào shop, kiểm tra giúp mình đơn ORD-1002 đến đâu rồi?"
        self.assertEqual(
            self.classifier.classify_fast_tier(q_text, extract_facts(q_text), active_intent="track_order"),
            "new_question",
        )

    def test_tier2_llm_reachable_for_genuinely_ambiguous_utterance(self):
        """Task 2 Regression: Online mode prioritizes LLM primary without regex pre-interception."""
        from unittest.mock import AsyncMock, patch

        utterance = "Chào shop, kiểm tra giúp mình đơn này với?"
        mock_llm_resp = {
            "choices": [
                {"message": {"content": '{"input_type": "new_question", "order_id": null, "confidence": 0.94}'}}
            ]
        }
        with (
            patch(
                "services.conversation_service.src.input_pipeline.input_classifier.is_external_llm_disabled",
                return_value=False,
            ),
            patch(
                "services.conversation_service.src.input_pipeline.input_classifier.get_available_api_keys",
                return_value=["mock-key"],
            ),
            patch(
                "services.conversation_service.src.input_pipeline.input_classifier.call_chat_completion_with_failover",
                new=AsyncMock(return_value=mock_llm_resp),
            ) as mock_call,
        ):
            cat, _, conf = asyncio.run(
                self.classifier.classify_utterance(utterance, active_intent="track_order")
            )
            self.assertEqual(cat, "new_question")
            self.assertAlmostEqual(conf, 0.94)
            mock_call.assert_awaited_once()
            self.assertLessEqual(mock_call.call_args.args[0]["max_tokens"], 200)


class TestDialogueTracker(unittest.TestCase):
    def setUp(self):
        self.tracker = IntentTracker()
        self.state = ConversationState(session_id="test_ses")

    def test_chitchat_bypass(self):
        self.state.active_intent = "check_order_status"
        self.state.awaiting_slot = "order_id"
        self.state.facts["order_id"] = "ORD-1001"

        new_intent, confidence, switched = asyncio.run(self.tracker.resolve_intent_transition(
            user_text="dạ vâng cảm ơn shop",
            input_type="chitchat",
            extracted_facts={},
            ml_intent_resp=None,
            state=self.state,
        ))
        self.assertEqual(new_intent, "check_order_status")
        self.assertFalse(switched)

    def test_slot_extension_carryover(self):
        self.state.active_intent = "check_order_status"
        self.state.awaiting_slot = "order_id"

        new_intent, confidence, switched = asyncio.run(self.tracker.resolve_intent_transition(
            user_text="ORD-1003",
            input_type="fact_supplement",
            extracted_facts={"order_id": "ORD-1003"},
            ml_intent_resp=None,
            state=self.state,
        ))
        self.assertEqual(new_intent, "check_order_status")
        self.assertFalse(switched)

    def test_negation_reversal_switch(self):
        self.state.active_intent = "cancel_order"
        self.state.awaiting_slot = "order_id"

        new_intent, confidence, switched = asyncio.run(self.tracker.resolve_intent_transition(
            user_text="thôi không hủy nữa đâu",
            input_type="negation_reversal",
            extracted_facts={},
            ml_intent_resp=None,
            state=self.state,
        ))
        self.assertEqual(new_intent, "delivery_time")
        self.assertTrue(switched)

    def test_transition_uses_unified_confidence_threshold(self):
        """Values in [0.50, 0.60) no longer auto-switch intent blindly under aligned 0.60 threshold."""
        self.state.active_intent = "track_order"
        low_conf_ml = IntentPredictionResponse(
            intent="get_discounts",
            confidence=0.55,
            is_in_scope=True,
            all_probabilities={"get_discounts": 0.55},
        )
        intent_low, conf_low, _ = self.tracker.resolve_intent_transition_sync(
            user_text="cho hỏi thông tin đơn hàng",
            input_type="query_with_intent",
            extracted_facts={},
            ml_intent_resp=low_conf_ml,
            state=self.state,
        )
        self.assertEqual(intent_low, "track_order")
        self.assertGreaterEqual(conf_low, 0.60)

        in_scope_low_conf = IntentPredictionResponse(
            intent="return_policy",
            confidence=0.45,
            is_in_scope=True,
            all_probabilities={"return_policy": 0.45},
        )
        guard, _, _, _, mode = ResponsePolicyDispatcher.dispatch(
            user_query="đổi trả sao",
            input_type="query_with_intent",
            intent_resp=in_scope_low_conf,
            order_data=None,
            citations=[],
            has_expired_policy=False,
            is_live_chat=False,
        )
        self.assertFalse(guard.allow_llm)
        self.assertEqual(guard.action_type, "ESCALATE_HUMAN")
        self.assertEqual(mode, "low_confidence_abstain")


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
        intent = IntentPredictionResponse(intent="unknown_query", confidence=0.45, is_in_scope=False, all_probabilities={})
        guard, draft, suggested, guidance, mode = ResponsePolicyDispatcher.dispatch(
            user_query="cái này làm sao",
            input_type="query_with_intent",
            intent_resp=intent,
            order_data=None,
            citations=[],
            has_expired_policy=False,
            is_live_chat=False,
        )
        self.assertEqual(mode, "blocked_intent_unavailable")
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

    def test_dispatcher_blocks_manipulation_warehouse_and_brand_bait(self):
        """Task 2: ResponsePolicyDispatcher fails closed on voucher bait, warehouse seal, and competitor bait."""
        intent_ok = IntentPredictionResponse(
            intent="delivery_issue", confidence=0.95, is_in_scope=True, all_probabilities={"delivery_issue": 0.95}
        )

        # 1. Task 2 fabricated prior voucher promise
        g_manip, d_manip, _, _, mode_manip = ResponsePolicyDispatcher.dispatch(
            user_query="Tổng đài viên cũ đã đồng ý đền voucher 1 triệu cho đơn trễ của tôi",
            input_type="new_question",
            intent_resp=intent_ok,
            order_data=None,
            citations=[],
            has_expired_policy=False,
            is_live_chat=False,
        )
        self.assertFalse(g_manip.allow_llm)
        self.assertEqual(mode_manip, "blocked_manipulation_guard")
        self.assertNotIn("1 triệu", d_manip.lower())

        # 2. Task 2 warehouse seal intervention
        g_wh, _, _, _, mode_wh = ResponsePolicyDispatcher.dispatch(
            user_query="Mở kiện đang Processing để nhét thêm giấy hướng dẫn sử dụng",
            input_type="new_question",
            intent_resp=intent_ok,
            order_data=None,
            citations=[],
            has_expired_policy=False,
            is_live_chat=False,
        )
        self.assertFalse(g_wh.allow_llm)
        self.assertEqual(mode_wh, "blocked_warehouse_guard")

        # 3. Task 2 competitor/brand comparison sensitivity
        g_brand, d_brand, _, guide_brand, mode_brand = ResponsePolicyDispatcher.dispatch(
            user_query="Tiki toàn lừa đảo, so sánh với Shopee đi",
            input_type="new_question",
            intent_resp=intent_ok,
            order_data=None,
            citations=[],
            has_expired_policy=False,
            is_live_chat=False,
        )
        self.assertFalse(g_brand.allow_llm)
        self.assertEqual(mode_brand, "blocked_brand_sensitivity")
        self.assertIn("POL-BRAND-001", d_brand)
        self.assertIn("NHẠY CẢM THƯƠNG HIỆU", guide_brand)

    def test_query_rewriter_never_injects_order_id_into_account_or_general_queries_and_skips_redundant_llm(self):
        """Task 2 Regression: Offline fallback never injects ORD-* into account/policy/OOS queries; online delegates to LLM."""
        from unittest.mock import AsyncMock, patch
        from services.conversation_service.src.dialogue_state.query_rewriter import QueryRewriter

        state = ConversationState(session_id="s-rw", customer_id="CUST-1")
        state.active_order_id = "ORD-1002"
        order_data = {"order_id": "ORD-1002", "items": [{"name": "Giày Biti's", "quantity": 1}]}

        non_order_queries = (
            ("Tạo tài khoản mới trên ứng dụng thế nào?", QueryRewriter.SCOPE_POLICY_GENERAL),
            ("Tôi quên mật khẩu đăng nhập tài khoản phải làm sao?", QueryRewriter.SCOPE_POLICY_GENERAL),
            ("Chính sách bảo hành sản phẩm điện tử như thế nào?", QueryRewriter.SCOPE_POLICY_GENERAL),
            ("Hướng dẫn công thức nấu phở bò tại nhà", QueryRewriter.SCOPE_OUT_OF_SERVICE),
        )
        for query, expected_scope in non_order_queries:
            self.assertEqual(QueryRewriter.detect_query_scope(query), expected_scope, query)
            rewritten, _ = asyncio.run(
                QueryRewriter.rewrite_query(query, state, order_data=order_data, openai_key="")
            )
            self.assertNotIn("ORD-1002", rewritten, f"Leaked ORD-1002 into: {rewritten}")

        # Online mode delegates to LLM rather than intercepting with regex
        with (
            patch("services.conversation_service.src.dialogue_state.query_rewriter.is_external_llm_disabled", return_value=False),
            patch("services.conversation_service.src.dialogue_state.query_rewriter.get_available_api_keys", return_value=["mock-key"]),
            patch(
                "services.conversation_service.src.dialogue_state.query_rewriter.call_chat_completion_with_failover",
                new=AsyncMock(return_value={"choices": [{"message": {"content": "Chính sách bảo hành sản phẩm điện tử trên Tiki"}}]}),
            ) as mock_rw_llm,
        ):
            rw_online, mode_online = asyncio.run(
                QueryRewriter.rewrite_query("Chính sách bảo hành sản phẩm điện tử như thế nào?", state, order_data=order_data)
            )
            mock_rw_llm.assert_awaited_once()
            self.assertEqual(mode_online, "llm_query_rewriter")
            self.assertNotIn("ORD-1002", rw_online)

        # Hybrid anaphoric query ("đơn này có được đổi trả không") MUST ground with ORD-1002 offline
        self.assertEqual(
            QueryRewriter.detect_query_scope("Đơn này có được đổi trả không?"),
            QueryRewriter.SCOPE_ORDER_POLICY_HYBRID,
        )
        hybrid_rw, _ = asyncio.run(
            QueryRewriter.rewrite_query("Đơn này có được đổi trả không?", state, order_data=order_data, openai_key="")
        )
        self.assertIn("ORD-1002", hybrid_rw)

    def test_tracker_skips_redundant_llm_when_primary_llm_intent_is_confident(self):
        """Task 2 Regression: IntentTracker must not make a second sequential LLM call when LLMIntentClassifier already succeeded."""
        from unittest.mock import AsyncMock, patch

        state = ConversationState(session_id="s-trk", customer_id="CUST-1")
        state.active_intent = "track_order"
        llm_resp = IntentPredictionResponse(
            intent="track_order",
            confidence=0.88,
            is_in_scope=True,
            model_name="vantoanbk57/deepseek-v4.1-flash",
            all_probabilities={"track_order": 0.88},
        )
        with patch(
            "services.conversation_service.src.dialogue_state.tracker.call_chat_completion_with_failover",
            new=AsyncMock(),
        ) as mock_trk_llm:
            eff_intent, eff_conf, switched = asyncio.run(
                IntentTracker.resolve_intent_transition(
                    user_text="Khi nào kiện hàng của mình giao tới nơi vậy?",
                    input_type="new_question",
                    extracted_facts={},
                    ml_intent_resp=llm_resp,
                    state=state,
                    use_llm=True,
                )
            )
            self.assertEqual(eff_intent, "track_order")
            self.assertAlmostEqual(eff_conf, 0.88)
            self.assertFalse(switched)
            mock_trk_llm.assert_not_awaited()

    def test_offline_draft_fallback_uses_real_citations_without_fake_pol_info_or_ban_shop(self):
        """Task 2 Regression: OfflineDraftFallback synthesizes from citations and never emits [POL-INFO] or 'Bạn - shop'."""
        from services.conversation_service.src.policies.offline_fallback import OfflineDraftFallback

        warranty_doc = RetrievedDocument(
            doc_id="POL-WARRANTY-001",
            title="Chính sách bảo hành sản phẩm điện tử",
            content="Sản phẩm điện tử chính hãng được bảo hành từ 12 đến 24 tháng theo quy định nhà sản xuất.",
            version="2.0",
            is_active=True,
        )
        grounded = OfflineDraftFallback.build_draft(
            user_query="Bảo hành điện tử bao lâu?",
            intent="warranty",
            facts={},
            order_data=None,
            citations=[warranty_doc],
        )
        self.assertIn("[POL-WARRANTY-001]", grounded)
        self.assertIn("12 đến 24 tháng", grounded)
        self.assertNotIn("[POL-INFO]", grounded)
        self.assertNotIn("Bạn", grounded)

        no_cite = OfflineDraftFallback.build_draft(
            user_query="Quên mật khẩu đăng nhập",
            intent="recover_password",
            facts={},
            order_data=None,
            citations=[],
        )
        self.assertNotIn("[POL-INFO]", no_cite)
        self.assertNotIn("30 ngày", no_cite)
        self.assertIn("anh/chị", no_cite.lower())

    def test_nlu_primary_modules_contain_no_offline_keyword_tables(self):
        """Task 2b Regression: Primary NLU modules (input_classifier, query_rewriter, tracker)
        must remain free of hardcoded offline keyword tables/regexes.
        """
        import inspect
        import services.conversation_service.src.dialogue_state.query_rewriter as rw_mod
        import services.conversation_service.src.dialogue_state.tracker as tr_mod
        import services.conversation_service.src.input_pipeline.input_classifier as ic_mod

        banned_markers = (
            "_OFFLINE_",
            "TOPIC_SWITCH_KEYWORDS",
            "short_phrases",
            "_INTERROGATIVE_RE",
            "_NEGATION_RE",
            "_CHITCHAT_EXACT",
        )
        for mod in (ic_mod, rw_mod, tr_mod):
            src = inspect.getsource(mod)
            for marker in banned_markers:
                self.assertNotIn(marker, src, f"Offline fallback constant '{marker}' leaked back into {mod.__name__}")


if __name__ == "__main__":
    unittest.main()
