"""Comprehensive Benchmark & Evaluation Test Suite for LLM Intent Classifier.
Evaluates 130 test cases across all 12 canonical TARGET_INTENTS + out_of_scope (10 cases/intent).
Validates multi-turn context tags, Vietnamese colloquialisms, and English inquiries.
"""
from __future__ import annotations

import unittest
from typing import Dict, List, Tuple
from services.intent_service.src.llm_classifier import LLMIntentClassifier
from services.intent_service.src.pipeline.dataset import TARGET_INTENTS, OOS_LABEL


# 130 Comprehensive Test Cases (10 cases per intent)
BENCHMARK_DATA: List[Tuple[str, str]] = [
    # 1. track_order (10 cases)
    ("Kiểm tra tiến độ đơn hàng ORD-1003 giúp tôi", "track_order"),
    ("Đơn hàng của tôi đang ở đâu rồi shop ơi", "track_order"),
    ("Where is my parcel right now?", "track_order"),
    ("I want to track order ORD-9921", "track_order"),
    ("Xem tình trạng giao hàng đơn ORD-8812", "track_order"),
    ("cho mình xin định vị bưu kiện của đơn vừa đặt", "track_order"),
    ("[PREV_INTENT:track_order] [AWAITING:order_id] ORD-1003", "track_order"),
    ("tra cứu đơn hàng ORD-5541", "track_order"),
    ("hàng của mình xuất kho chưa shop", "track_order"),
    ("track my delivery status", "track_order"),

    # 2. cancel_order (10 cases)
    ("Tôi muốn hủy đơn hàng vừa đặt", "cancel_order"),
    ("Làm thế nào để hủy đơn ORD-1002 vậy shop", "cancel_order"),
    ("cancel my order please", "cancel_order"),
    ("i want to cancel purchase immediately", "cancel_order"),
    ("hủy lệnh mua hàng giúp tôi với", "cancel_order"),
    ("không muốn mua nữa hủy đơn cho mình", "cancel_order"),
    ("dừng đơn hàng ORD-7721 lại", "cancel_order"),
    ("hủy đơn giúp em em lỡ đặt trùng", "cancel_order"),
    ("please cancel this order", "cancel_order"),
    ("Tôi đặt nhầm địa chỉ nên muốn hủy đơn", "cancel_order"),

    # 3. delivery_time (10 cases)
    ("Bao giờ tôi nhận được hàng vậy shop", "delivery_time"),
    ("Khi nào shipper giao tới", "delivery_time"),
    ("Mất bao nhiêu ngày để giao hàng tới Hà Nội", "delivery_time"),
    ("When will my order arrive?", "delivery_time"),
    ("How long does standard delivery take?", "delivery_time"),
    ("Dự kiến mấy ngày nữa có hàng", "delivery_time"),
    ("[PREV_INTENT:cancel_order] thôi không hủy nữa, xem bao giờ giao tới nơi", "delivery_time"),
    ("thời gian vận chuyển mất bao lâu", "delivery_time"),
    ("ngày mai có giao kịp không shop", "delivery_time"),
    ("what is the estimated delivery time", "delivery_time"),

    # 4. delivery_issue (10 cases)
    ("Shipper chưa giao mà hệ thống tự động báo đã giao thành công", "delivery_issue"),
    ("Đơn hàng bị giao trễ quá hạn 5 ngày rồi chưa thấy đâu", "delivery_issue"),
    ("Shipper không gọi điện mà tự ý bấm hủy giao hàng", "delivery_issue"),
    ("Giao nhầm sang địa chỉ khác rồi shop ơi", "delivery_issue"),
    ("Delivery delay issue, package not received", "delivery_issue"),
    ("Courier marked delivered but i received nothing", "delivery_issue"),
    ("Hàng bị giao chậm trễ quá mức quy định", "delivery_issue"),
    ("Tại sao shipper không liên hệ mà bảo không giao được", "delivery_issue"),
    ("Kiện hàng của tôi bị thất lạc hay sao mà lâu thế", "delivery_issue"),
    ("Delivery problem, courier was very rude and didn't deliver", "delivery_issue"),

    # 5. shipping_costs (10 cases)
    ("Phí ship về Đà Nẵng là bao nhiêu tiền", "shipping_costs"),
    ("Cước phí vận chuyển tính như thế nào", "shipping_costs"),
    ("Đơn hàng bao nhiêu tiền thì được freeship", "shipping_costs"),
    ("What are the shipping costs for this item?", "shipping_costs"),
    ("How much is the delivery fee?", "shipping_costs"),
    ("Có mã miễn phí vận chuyển không shop", "shipping_costs"),
    ("Phí giao hàng hỏa tốc là bao nhiêu", "shipping_costs"),
    ("Cước ship đắt quá có giảm được không", "shipping_costs"),
    ("Is delivery free for orders over 500k?", "shipping_costs"),
    ("Hỏi về biểu phí giao hàng tiêu chuẩn", "shipping_costs"),

    # 6. return_policy (10 cases)
    ("Chính sách đổi trả hàng của sàn quy định thế nào", "return_policy"),
    ("Tôi được đổi trả sản phẩm trong vòng bao nhiêu ngày", "return_policy"),
    ("Điều kiện để được đổi hàng là gì", "return_policy"),
    ("What is your return policy?", "return_policy"),
    ("Can I return an item and what are the conditions?", "return_policy"),
    ("Quy định về thời hạn trả hàng", "return_policy"),
    ("Sản phẩm bóc seal rồi có được đổi trả không", "return_policy"),
    ("Cho tôi xem hướng dẫn quy trình đổi trả hàng", "return_policy"),
    ("Return policy guidelines for electronics", "return_policy"),
    ("i want to know the newest return policy", "return_policy"),

    # 7. return_product (10 cases)
    ("Tôi muốn đổi cái áo này sang size L vì bị chật", "return_product"),
    ("Sản phẩm nhận được bị nứt vỡ, tôi muốn trả lại hàng", "return_product"),
    ("Tai nghe bị rè 1 bên tôi muốn đổi cái mới", "return_product"),
    ("I received a defective item and want to return it", "return_product"),
    ("Exchange this shirt for a larger size", "return_product"),
    ("Yêu cầu trả sản phẩm và gửi lại hàng cho shop", "return_product"),
    ("Hàng không đúng mô tả tôi muốn trả hàng", "return_product"),
    ("Return this damaged product", "return_product"),
    ("Đổi trả món đồ vừa nhận hôm qua bị rách", "return_product"),
    ("Đổi sang mẫu khác được không shop hàng bị lỗi", "return_product"),

    # 8. refund_policy (10 cases)
    ("Chính sách hoàn tiền của shop như thế nào", "refund_policy"),
    ("Quy định về việc hoàn lại tiền vào tài khoản", "refund_policy"),
    ("Hoàn tiền qua thẻ tín dụng mất bao lâu theo quy định", "refund_policy"),
    ("What is the refund policy?", "refund_policy"),
    ("How does the refund process work according to rules?", "refund_policy"),
    ("Thời hạn hoàn tiền theo quy định là bao nhiêu ngày", "refund_policy"),
    ("Có được hoàn tiền về ví MoMo không", "refund_policy"),
    ("Điều kiện để được xét duyệt hoàn tiền", "refund_policy"),
    ("Refund terms and conditions", "refund_policy"),
    ("Chính sách trả lại tiền khi shop hết hàng", "refund_policy"),

    # 9. request_refund (10 cases)
    ("Tôi yêu cầu hoàn tiền lại cho đơn hàng ORD-1002", "request_refund"),
    ("Hoàn tiền cho tôi ngay vì hàng không giao", "request_refund"),
    ("I want a refund for my cancelled order", "request_refund"),
    ("Please refund my money to my bank account", "request_refund"),
    ("Trả lại tiền cho tôi, tôi không nhận hàng nữa", "request_refund"),
    ("Yêu cầu hoàn trả 500k vào tài khoản", "request_refund"),
    ("Hủy đơn và hoàn tiền lại giúp mình", "request_refund"),
    ("Hoàn tiền gấp cho tôi", "request_refund"),
    ("I demand a refund immediately", "request_refund"),
    ("Cho tôi làm thủ tục lấy lại tiền đơn hàng này", "request_refund"),

    # 10. refund_status (10 cases)
    ("Tiền hoàn của đơn ORD-1002 đã về tài khoản chưa shop", "refund_status"),
    ("Kiểm tra tiến độ hoàn tiền giúp tôi", "refund_status"),
    ("Bao giờ tôi mới nhận được tiền hoàn vậy", "refund_status"),
    ("Đã có thông báo hoàn tiền nhưng kiểm tra tài khoản chưa thấy", "refund_status"),
    ("Check my refund status please", "refund_status"),
    ("When will the refund arrive in my bank?", "refund_status"),
    ("Tiền hoàn về thẻ visa đến đâu rồi", "refund_status"),
    ("Hôm qua báo hoàn tiền mà hôm nay chưa nhận được tiền hoàn", "refund_status"),
    ("Has my refund been processed yet?", "refund_status"),
    ("Tra cứu trạng thái tiền hoàn về tài khoản", "refund_status"),

    # 11. payment_issue (10 cases)
    ("Tôi bị trừ tiền 2 lần cho cùng một đơn hàng", "payment_issue"),
    ("Thanh toán qua VNPAY bị lỗi trừ tiền nhưng đơn báo chưa thanh toán", "payment_issue"),
    ("Thẻ ngân hàng của tôi bị từ chối khi thanh toán", "payment_issue"),
    ("Payment failed but money was deducted from my account", "payment_issue"),
    ("I was charged twice for order ORD-3341", "payment_issue"),
    ("Lỗi cổng thanh toán MoMo không xác nhận được", "payment_issue"),
    ("Không quét được mã QR thanh toán", "payment_issue"),
    ("Tài khoản báo giao dịch thành công mà hệ thống báo thanh toán thất bại", "payment_issue"),
    ("Credit card payment error", "payment_issue"),
    ("Sự cố trừ tiền tài khoản ngân hàng", "payment_issue"),

    # 12. human_agent (10 cases)
    ("Tôi muốn gặp trực tiếp nhân viên tư vấn", "human_agent"),
    ("Cho tôi nói chuyện với người thật, không nói với bot", "human_agent"),
    ("Kết nối với tổng đài viên giúp tôi", "human_agent"),
    ("I want to speak with a human agent", "human_agent"),
    ("Connect me to customer support representative", "human_agent"),
    ("Gặp chuyên viên CSKH trực tiếp để khiếu nại", "human_agent"),
    ("Chuyển máy cho nhân viên hỗ trợ", "human_agent"),
    ("Talk to real support staff", "human_agent"),
    ("Alo có nhân viên trực không cho tôi gặp", "human_agent"),
    ("Nhân viên tư vấn đâu rồi ra nói chuyện", "human_agent"),

    # 13. out_of_scope (10 cases)
    ("Hôm nay thời tiết ở Hà Nội thế nào", "out_of_scope"),
    ("Giải phương trình bậc 2 giúp tôi", "out_of_scope"),
    ("Bạn có biết tổng thống Mỹ là ai không", "out_of_scope"),
    ("What is the capital of France?", "out_of_scope"),
    ("Kể cho tôi một câu chuyện cười", "out_of_scope"),
    ("Tư vấn cách nấu món phở bò ngon", "out_of_scope"),
    ("Viết một bài thơ về mùa thu", "out_of_scope"),
    ("Can you write Python code to sort a list?", "out_of_scope"),
    ("Đội bóng nào vô địch World Cup 2022", "out_of_scope"),
    ("Tỷ giá USD hôm nay là bao nhiêu", "out_of_scope"),
]


class TestLLMIntentBenchmark(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classifier = LLMIntentClassifier()

    def test_benchmark_all_intents(self):
        """Run all 130 test cases and report accuracy per intent class."""
        total = len(BENCHMARK_DATA)
        correct = 0

        # Stats tracking per intent
        intent_stats: Dict[str, Dict[str, int]] = {}
        all_labels = TARGET_INTENTS + [OOS_LABEL]
        for label in all_labels:
            intent_stats[label] = {"total": 0, "correct": 0}

        failures = []

        for query, expected_intent in BENCHMARK_DATA:
            pred = self.classifier.predict(query)
            predicted_intent = pred.intent

            intent_stats[expected_intent]["total"] += 1
            if predicted_intent == expected_intent:
                correct += 1
                intent_stats[expected_intent]["correct"] += 1
            else:
                failures.append(
                    f"Query: '{query}' | Expected: {expected_intent} | Predicted: {predicted_intent} (conf: {pred.confidence:.2f})"
                )

        overall_accuracy = correct / total

        # Print detailed report to stdout (ASCII-safe for Windows console)
        print("\n" + "=" * 78)
        print("=== REPORT: INTENT CLASSIFICATION EVALUATION (LLM BENCHMARK) ===")
        print("=" * 78)
        print(f"{'Intent':<20} | {'Total':<6} | {'Correct':<8} | {'Accuracy':<10} | {'Status'}")
        print("-" * 78)

        for label in all_labels:
            stats = intent_stats[label]
            tot = stats["total"]
            cor = stats["correct"]
            acc = (cor / tot * 100) if tot > 0 else 0.0
            status_tag = "[PERFECT]" if acc == 100 else ("[GOOD]" if acc >= 80 else "[NEEDS WORK]")
            print(f"{label:<20} | {tot:<6} | {cor:<8} | {acc:>6.1f}%    | {status_tag}")

        print("=" * 78)
        print(f"Total test cases: {total}")
        print(f"Correct predictions: {correct} / {total}")
        print(f"Overall Accuracy: {overall_accuracy:.1%}")
        print("=" * 78)

        if failures:
            print("\nMisclassified cases:")
            for f in failures:
                # encode safely
                safe_f = f.encode("ascii", errors="replace").decode("ascii")
                print(f" - {safe_f}")

        # Assert at least 92% overall accuracy across the 130 diverse cases
        self.assertGreaterEqual(
            overall_accuracy,
            0.92,
            f"Overall accuracy {overall_accuracy:.1%} is lower than expected 92%",
        )


if __name__ == "__main__":
    unittest.main()
