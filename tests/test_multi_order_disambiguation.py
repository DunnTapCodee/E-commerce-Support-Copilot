"""Tests for multi-order customer disambiguation, data normalization, and fallback drafts."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import unittest
from unittest.mock import AsyncMock, patch

from services.conversation_service.src.dialogue_state.state import ConversationState
from services.conversation_service.src.input_pipeline.fact_extractor import extract_all_order_ids
from services.conversation_service.src.input_pipeline.order_matcher import HybridOrderMatcher
from services.conversation_service.src.main import _resolve_scoped_order_and_guard
from services.conversation_service.src.policies.copilot_draft_engine import CopilotDraftEngine

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestMultiOrderDisambiguation(unittest.TestCase):
    def setUp(self):
        self.orders = json.loads((ROOT_DIR / "data" / "mock_orders.json").read_text(encoding="utf-8"))
        self.demo_orders = [o for o in self.orders if o.get("customer_id") == "demo-customer"]

    def test_demo_customer_orders_normalized_to_bui_thi_an(self):
        self.assertGreater(len(self.demo_orders), 1)
        for order in self.demo_orders:
            self.assertEqual(order.get("customer_name"), "Bùi Thị An")
        ord_1001 = next(o for o in self.demo_orders if o.get("order_id") == "ORD-1001")
        self.assertEqual(ord_1001.get("phone"), "0938.242.854")

    def test_extract_all_order_ids_variants(self):
        self.assertEqual(
            extract_all_order_ids("Kiểm tra giúp tôi ORD-1001 và đơn số 1026"),
            ["ORD-1001", "ORD-1026"],
        )
        self.assertEqual(extract_all_order_ids("Tôi muốn xem đơn của mình"), [])
        self.assertEqual(extract_all_order_ids("#1005"), ["ORD-1005"])

    def test_hybrid_matcher_match_all_finds_multiple_item_matches(self):
        matcher = HybridOrderMatcher(self.orders)
        matches = matcher.match_all("Giày thể thao Biti's Hunter", customer_id="demo-customer", limit=10)
        matched_ids = {m["order_id"] for m in matches}
        self.assertGreaterEqual(len(matched_ids), 2)
        self.assertTrue({"ORD-1005", "ORD-1015", "ORD-1051"}.issubset(matched_ids))

    def test_resolve_status_filter_and_paraphrases(self):
        async def _run():
            for query in ("Tôi có những đơn hàng nào đang bị giao trễ?", "Xem giúp các đơn bị trễ hẹn của mình"):
                state = ConversationState(session_id="s-filter", customer_id="demo-customer")
                with patch(
                    "services.conversation_service.src.main._load_customer_orders_scoped",
                    new=AsyncMock(return_value=self.demo_orders),
                ):
                    order_data, unauth, multi = await _resolve_scoped_order_and_guard(
                        query, state, "demo-customer"
                    )
                self.assertIsNone(unauth)
                self.assertIsNone(order_data)
                self.assertIsNotNone(multi)
                self.assertEqual(multi["reason"], "status_filter")
                self.assertTrue(all(o["order_status"] == "Delivery_Delayed" for o in multi["candidates"]))

        asyncio.run(_run())

    def test_resolve_ambiguous_cancel_filters_to_eligible_processing_orders(self):
        async def _run():
            for query in ("Tôi muốn hủy đơn hàng", "Không mua nữa, hủy đơn giúp mình"):
                state = ConversationState(session_id="s-cancel", customer_id="demo-customer")
                with patch(
                    "services.conversation_service.src.main._load_customer_orders_scoped",
                    new=AsyncMock(return_value=self.demo_orders),
                ):
                    order_data, unauth, multi = await _resolve_scoped_order_and_guard(
                        query, state, "demo-customer"
                    )
                self.assertIsNone(unauth)
                self.assertIsNone(order_data)
                self.assertIsNotNone(multi)
                self.assertEqual(multi["reason"], "ambiguous_cancel_order")
                statuses = {o["order_status"] for o in multi["candidates"]}
                self.assertNotIn("Delivered", statuses)
                self.assertTrue(statuses.issubset({"Processing", "Payment_Failed"}))

        asyncio.run(_run())

    def test_single_order_customer_resolves_directly_without_disambiguation(self):
        single_order = [
            {
                "order_id": "ORD-9001",
                "customer_id": "CUST-SINGLE",
                "customer_name": "Nguyễn Văn A",
                "order_status": "Processing",
                "items": [{"name": "Bàn phím cơ", "quantity": 1}],
            }
        ]

        async def _run():
            state = ConversationState(session_id="s-single", customer_id="CUST-SINGLE")
            with (
                patch(
                    "services.conversation_service.src.main._load_customer_orders_scoped",
                    new=AsyncMock(return_value=single_order),
                ),
                patch(
                    "services.conversation_service.src.main.telemetry_client.lookup_order",
                    new=AsyncMock(return_value=single_order[0]),
                ),
            ):
                order_data, unauth, multi = await _resolve_scoped_order_and_guard(
                    "Kiểm tra đơn hàng của tôi", state, "CUST-SINGLE"
                )
            self.assertIsNone(unauth)
            self.assertIsNone(multi)
            self.assertIsNotNone(order_data)
            self.assertEqual(order_data["order_id"], "ORD-9001")

        asyncio.run(_run())

    def test_fallback_draft_never_prints_none_and_handles_delivered_status(self):
        delivered = {
            "order_id": "ORD-1095",
            "order_status": "Delivered",
            "items": [{"name": "Tai nghe Bluetooth", "quantity": 1}],
        }
        draft = CopilotDraftEngine._build_semantic_fallback_draft(
            user_query="Kiểm tra đơn ORD-1095",
            intent="track_order",
            facts={"order_id": "ORD-1095"},
            order_data=delivered,
            citations=[],
        )
        self.assertNotIn("None", draft)
        self.assertIn("Delivered", draft)
        self.assertNotIn("bưu tá", draft)

    def test_payment_method_filter_and_portfolio_aggregation(self):
        async def _run():
            # 1. Payment method filter (ZaloPay)
            state1 = ConversationState(session_id="s-zalo", customer_id="demo-customer")
            with patch(
                "services.conversation_service.src.main._load_customer_orders_scoped",
                new=AsyncMock(return_value=self.demo_orders),
            ):
                order_data, unauth, multi = await _resolve_scoped_order_and_guard(
                    "các đơn hàng nào thanh toán bằng zalo pay", state1, "demo-customer"
                )
            self.assertIsNone(unauth)
            self.assertIsNone(order_data)
            self.assertEqual(multi["reason"], "status_filter")
            zalo_ids = {o["order_id"] for o in multi["candidates"]}
            self.assertEqual(zalo_ids, {"ORD-1015", "ORD-1030", "ORD-1051", "ORD-1060", "ORD-1076"})

            # 2. Portfolio context attaches factual computed_summary for LLM & grounding
            state2 = ConversationState(session_id="s-sum", customer_id="demo-customer")
            with patch(
                "services.conversation_service.src.main._load_customer_orders_scoped",
                new=AsyncMock(return_value=self.demo_orders),
            ):
                order_data, unauth, multi = await _resolve_scoped_order_and_guard(
                    "tổng mình đã thanh toán bao nhiêu tiền rồi", state2, "demo-customer"
                )
            self.assertIsNone(unauth)
            self.assertIsNone(order_data)
            self.assertEqual(multi["reason"], "multiple_customer_orders")
            self.assertEqual(len(multi["candidates"]), len(self.demo_orders))
            self.assertGreater(multi["computed_summary"]["total_paid_amount"], 0)
            self.assertGreater(multi["computed_summary"]["paid_order_count"], 0)

        asyncio.run(_run())

    def test_multi_order_grounding_allows_vn_statuses_and_blocks_fake_numbers(self):
        from contracts.safety import evaluate_runtime_safety_envelope
        from contracts.schemas import RetrievedDocument

        cites = [
            RetrievedDocument(
                doc_id="POL-ORD-001",
                title="Quy định kiểm tra đơn hàng",
                content="Khách hàng có thể kiểm tra trạng thái đơn hàng và phương thức thanh toán trên hệ thống.",
                score=0.9,
                is_active=True,
            )
        ]
        zalo_orders = [o for o in self.demo_orders if "zalopay" in str(o.get("payment_method", "")).lower()]
        grounded = {"candidates": zalo_orders, "computed_summary": {"total_orders": len(zalo_orders)}}

        valid_draft = (
            "Dạ em chào anh/chị, hiện tài khoản của mình có 5 đơn hàng thanh toán qua Ví ZaloPay: "
            "#ORD-1076 (thanh toán thất bại), #ORD-1060 (đã hủy), #ORD-1051 (đã trả hàng), "
            "#ORD-1030 (đang xử lý), #ORD-1015 (giao hàng trễ, dự kiến 21/11/2026)."
        )
        ok_res = evaluate_runtime_safety_envelope(
            customer_query="các đơn hàng nào thanh toán bằng zalo pay",
            draft_text=valid_draft,
            order_data=grounded,
            citations=cites,
            faithfulness_threshold=0.70,
        )
        self.assertTrue(ok_res.allow_llm, ok_res.reason)

        bad_draft = "Dạ tài khoản mình có 99 đơn hàng và được hoàn 888,000 VNĐ ngay."
        bad_res = evaluate_runtime_safety_envelope(
            customer_query="các đơn hàng nào thanh toán bằng zalo pay",
            draft_text=bad_draft,
            order_data=grounded,
            citations=cites,
            faithfulness_threshold=0.70,
        )
        self.assertFalse(bad_res.allow_llm)

    def test_multi_order_customer_non_order_queries_do_not_attach_portfolio_or_pin_order(self):
        """Regression test (Task 1): Multi-order customer asking policy/account/OOS questions gets (None, None, None)."""
        non_order_queries = (
            "Thời tiết hôm nay ở Hà Nội mưa hay nắng?",
            "Giải giúp mình phương trình 2x + 5 = 15",
            "Gói TikiPRO là gì và có quyền lợi như thế nào?",
            "Tôi quên mật khẩu đăng nhập tài khoản phải làm sao?",
            "Chính sách bảo hành cũ trước năm 2024 thế nào?",
        )

        async def _run():
            for query in non_order_queries:
                state = ConversationState(session_id="s-non-order", customer_id="demo-customer")
                with (
                    patch(
                        "services.conversation_service.src.main._load_customer_orders_scoped",
                        new=AsyncMock(return_value=self.demo_orders),
                    ),
                    patch(
                        "services.conversation_service.src.main.telemetry_client.lookup_order",
                        new=AsyncMock(return_value=self.demo_orders[0]),
                    ),
                ):
                    order_data, unauth, multi = await _resolve_scoped_order_and_guard(
                        query, state, "demo-customer"
                    )
                self.assertIsNone(unauth, f"Unexpected unauth on: {query}")
                self.assertIsNone(order_data, f"Should not pin arbitrary single order on: {query}")
                self.assertIsNone(multi, f"Should not attach multi_order_context on: {query}")
                self.assertIsNone(state.active_order_id, f"Should not mutate active_order_id on: {query}")

            # Unseen personal order paraphrases MUST still trigger multi_order_context
            personal_order_queries = (
                "Đơn hàng mình vừa đặt hiện đang ở đâu rồi shop?",
                "Tra cứu đơn hàng của tôi xem bao giờ nhận được",
            )
            for query in personal_order_queries:
                state = ConversationState(session_id="s-personal-order", customer_id="demo-customer")
                with patch(
                    "services.conversation_service.src.main._load_customer_orders_scoped",
                    new=AsyncMock(return_value=self.demo_orders),
                ):
                    order_data, unauth, multi = await _resolve_scoped_order_and_guard(
                        query, state, "demo-customer"
                    )
                self.assertIsNone(unauth)
                self.assertIsNone(order_data)
                self.assertIsNotNone(multi, f"Expected multi_order_context on personal inquiry: {query}")
                self.assertEqual(multi["reason"], "multiple_customer_orders")

        asyncio.run(_run())


if __name__ == "__main__":
    unittest.main()
