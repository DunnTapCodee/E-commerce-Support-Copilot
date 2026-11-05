"""CMU MLIP Behavioral Testing Framework (CheckList / Ribeiro et al.).
Evaluates:
  1. Minimum Functionality Tests (MFT) - Basic unit capability
  2. Invariance Tests (INV) - Metamorphic perturbations that should NOT change output
  3. Directional Expectation Tests (DIR) - Semantic changes that MUST shift output
"""
import time
from typing import Any, Callable, Dict, List, Tuple
from contracts.schemas import IntentPredictionResponse
from services.intent_service.src.predictor import IntentPredictor


class BehavioralTestSuite:
    """CheckList-style behavioral test runner for intent classification & dialogue."""

    def __init__(self, predictor: IntentPredictor = None):
        self.predictor = predictor or IntentPredictor()

    def run_mft(self) -> Dict[str, Any]:
        """Minimum Functionality Tests (MFT): Clear, simple, critical queries."""
        cases = [
            ("Cho mình hỏi đơn hàng ORD-1100 đang ở đâu?", "track_order", "Order tracking inquiry"),
            ("Hủy đơn hàng này giúp tôi", "cancel_order", "Order cancellation"),
            ("Bao giờ thì hàng được giao tới?", "delivery_time", "Delivery timeframe"),
            ("Shipper không liên hệ mà bấm giao không thành công", "delivery_issue", "Shipper complaint"),
            ("Phí vận chuyển tính như thế nào?", "shipping_costs", "Shipping fee rules"),
            ("Chính sách đổi trả hàng trong mấy ngày?", "return_policy", "Return policy guidelines"),
            ("Áo giao bị rách muốn đổi cái khác", "return_product", "Exchange defective item"),
            ("Hoàn tiền lại cho tôi vào ví", "request_refund", "Refund demand"),
            ("Bao giờ tiền hoàn về tài khoản ngân hàng?", "refund_status", "Refund progress tracking"),
            ("Tài khoản bị trừ tiền 2 lần khi thanh toán", "payment_issue", "Payment deduction bug"),
            ("Cho tôi gặp nhân viên tổng đài tư vấn", "human_agent", "Human agent escalation"),
            ("Thời tiết ngày mai mưa hay nắng", "out_of_scope", "Out of domain weather"),
        ]

        passed = 0
        details = []
        for query, expected_intent, desc in cases:
            resp: IntentPredictionResponse = self.predictor.predict(query)
            is_pass = (resp.intent == expected_intent)
            if is_pass:
                passed += 1
            details.append({
                "test_name": desc,
                "query": query,
                "expected": expected_intent,
                "predicted": resp.intent,
                "confidence": resp.confidence,
                "passed": is_pass,
            })

        return {
            "type": "MFT (Minimum Functionality Tests)",
            "total": len(cases),
            "passed": passed,
            "pass_rate": round((passed / len(cases)) * 100, 2),
            "details": details,
        }

    def run_inv(self) -> Dict[str, Any]:
        """Invariance Tests (INV): Predictions MUST remain invariant under harmless perturbations."""
        base_cases = [
            ("Kiểm tra đơn hàng ORD-1100", "track_order"),
            ("Chính sách đổi trả sản phẩm thế nào", "return_policy"),
            ("Bao lâu thì giao hàng tới nơi", "delivery_time"),
            ("Phí ship về Hải Phòng là bao nhiêu", "shipping_costs"),
            ("Cho tôi gặp nhân viên tư vấn", "human_agent"),
        ]

        # Benign perturbations:
        # 1. Politeness prefix/suffix ("Dạ shop cho em hỏi... ạ")
        # 2. Letter casing ("ord-1100" vs "ORD-1100")
        # 3. Extra whitespace
        inv_pairs: List[Tuple[str, str, str, str]] = []
        for q, expected in base_cases:
            # Perturbation 1: Politeness
            p_polite = f"Dạ em chào shop ạ, shop cho em hỏi {q.lower()} với nhé em cảm ơn"
            inv_pairs.append((q, p_polite, expected, "Politeness wrapping"))

            # Perturbation 2: Whitespace / case
            p_space = f"  {q.upper()}  "
            inv_pairs.append((q, p_space, expected, "Uppercase & whitespace"))

        passed = 0
        details = []
        for orig, perturbed, expected, perturbation_name in inv_pairs:
            resp_orig = self.predictor.predict(orig)
            resp_pert = self.predictor.predict(perturbed)
            is_invariant = (resp_orig.intent == resp_pert.intent)
            if is_invariant:
                passed += 1
            details.append({
                "perturbation": perturbation_name,
                "original_query": orig,
                "perturbed_query": perturbed,
                "original_intent": resp_orig.intent,
                "perturbed_intent": resp_pert.intent,
                "invariant": is_invariant,
            })

        return {
            "type": "INV (Invariance Tests / Metamorphic)",
            "total": len(inv_pairs),
            "passed": passed,
            "pass_rate": round((passed / len(inv_pairs)) * 100, 2),
            "details": details,
        }

    def run_dir(self) -> Dict[str, Any]:
        """Directional Expectation Tests (DIR): Predictions MUST change in specified direction."""
        dir_cases = [
            # Case 1: Cancellation reversed to delivery inquiry
            (
                "Tôi muốn hủy đơn hàng ORD-1100",
                "Tôi định hủy đơn nhưng thôi không hủy nữa, xem bao giờ giao hộ tôi",
                "cancel_order",
                "delivery_time",
                "Negation reversal (cancel_order -> delivery_time)",
            ),
            # Case 2: In-scope tracking vs Out-of-scope math
            (
                "Kiểm tra đơn hàng ORD-1100",
                "Kiểm tra giúp tôi bài toán 2x + 5 = 15",
                "track_order",
                "out_of_scope",
                "Domain shift (track_order -> out_of_scope)",
            ),
            # Case 3: Policy inquiry vs Urgent refund demand
            (
                "Quy định hoàn tiền của sàn thế nào?",
                "Tôi yêu cầu hoàn tiền lại ngay cho tôi vào tài khoản",
                "refund_policy",
                "request_refund",
                "Escalation to direct action (refund_policy -> request_refund)",
            ),
        ]

        passed = 0
        details = []
        for q1, q2, exp1, exp2, desc in dir_cases:
            r1 = self.predictor.predict(q1)
            r2 = self.predictor.predict(q2)
            is_dir_pass = (r1.intent == exp1 and r2.intent == exp2)
            if is_dir_pass:
                passed += 1
            details.append({
                "description": desc,
                "input_1": q1,
                "predicted_1": r1.intent,
                "expected_1": exp1,
                "input_2": q2,
                "predicted_2": r2.intent,
                "expected_2": exp2,
                "passed": is_dir_pass,
            })

        return {
            "type": "DIR (Directional Expectation Tests)",
            "total": len(dir_cases),
            "passed": passed,
            "pass_rate": round((passed / len(dir_cases)) * 100, 2),
            "details": details,
        }

    def run_all(self) -> Dict[str, Any]:
        return {
            "mft": self.run_mft(),
            "inv": self.run_inv(),
            "dir": self.run_dir(),
        }
