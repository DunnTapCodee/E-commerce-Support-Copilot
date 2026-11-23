"""End-to-End System Evaluation for E-Commerce Support Copilot.
Tests complete multi-turn dialogue pipelines against the Gateway ingress.
"""
import uuid
import httpx
from typing import Any, Dict, List


class EndToEndEvaluator:
    """Executes multi-turn conversation scenarios against the live Gateway."""

    def __init__(self, gateway_url: str = "http://localhost:18000"):
        self.gateway_url = gateway_url.rstrip("/")

    async def run_scenario_multi_turn_order_tracking(self) -> Dict[str, Any]:
        """Scenario A: 2-turn order inquiry:
        Turn 1: Customer asks without order ID -> Bot acknowledges and asks for order ID.
        Turn 2: Customer provides 'ORD-1100' -> System retrieves order data, matches customer Lê Văn Sơn, and drafts answer.
        """
        session_id = f"e2e_test_{uuid.uuid4().hex[:6]}"
        customer_id = "CUST-1100"

        turns_results = []
        async with httpx.AsyncClient(timeout=25.0) as client:
            # Turn 1
            payload_1 = {
                "query": "Kiểm tra đơn hàng của mình đến đâu rồi",
                "session_id": session_id,
                "customer_id": customer_id,
            }
            r1 = await client.post(f"{self.gateway_url}/api/v1/copilot/query", json=payload_1)
            t1_ok = (r1.status_code == 200)
            d1 = r1.json() if t1_ok else {}

            turns_results.append({
                "turn": 1,
                "user_query": payload_1["query"],
                "status_code": r1.status_code,
                "intent": d1.get("intent", {}).get("intent"),
                "ack": d1.get("customer_acknowledgement"),
                "has_draft": bool(d1.get("draft_text")),
            })

            # Turn 2: Provide order ID
            payload_2 = {
                "query": "ORD-1100",
                "session_id": session_id,
                "customer_id": customer_id,
            }
            r2 = await client.post(f"{self.gateway_url}/api/v1/copilot/query", json=payload_2)
            t2_ok = (r2.status_code == 200)
            d2 = r2.json() if t2_ok else {}

            order_matched = bool(d2.get("order_data") and d2["order_data"].get("order_id") == "ORD-1100")
            turns_results.append({
                "turn": 2,
                "user_query": payload_2["query"],
                "status_code": r2.status_code,
                "intent": d2.get("intent", {}).get("intent"),
                "ack": d2.get("customer_acknowledgement"),
                "order_matched": order_matched,
                "order_status": d2.get("order_data", {}).get("status") if d2.get("order_data") else None,
                "has_draft": bool(d2.get("draft_text")),
            })

        scenario_passed = (t1_ok and t2_ok and order_matched)
        return {
            "scenario": "Multi-turn Order Tracking (ORD-1100)",
            "passed": scenario_passed,
            "turns": turns_results,
        }

    async def run_scenario_financial_refund_interception(self) -> Dict[str, Any]:
        """Scenario B: Financial Risk Interception:
        Customer directly demands a refund -> System intercepts with DIRECT_REFUND_FORM guardrail.
        """
        session_id = f"e2e_test_{uuid.uuid4().hex[:6]}"
        payload = {
            "query": "Tôi yêu cầu hoàn tiền lại cho tôi ngay vào tài khoản",
            "session_id": session_id,
            "customer_id": "CUST-1100",
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(f"{self.gateway_url}/api/v1/copilot/query", json=payload)
            ok = (r.status_code == 200)
            data = r.json() if ok else {}

            action_type = data.get("guardrail", {}).get("action_type")
            is_financial_blocked = (action_type == "DIRECT_REFUND_FORM" or data.get("generation_mode") == "blocked_financial_guard")

        return {
            "scenario": "Financial Risk Interception (Request Refund)",
            "passed": ok and is_financial_blocked,
            "action_type": action_type,
            "status_code": r.status_code,
        }

    async def run_scenario_policy_retrieval_and_citations(self) -> Dict[str, Any]:
        """Scenario C: Standard Policy Inquiry:
        Customer asks about return policy -> Copilot returns citations and grounded draft.
        """
        session_id = f"e2e_test_{uuid.uuid4().hex[:6]}"
        payload = {
            "query": "Chính sách đổi trả hàng hóa của sàn thế nào?",
            "session_id": session_id,
            "customer_id": "CUST-GUEST",
        }
        async with httpx.AsyncClient(timeout=25.0) as client:
            r = await client.post(f"{self.gateway_url}/api/v1/copilot/query", json=payload)
            ok = (r.status_code == 200)
            data = r.json() if ok else {}

            citations = data.get("citations", [])
            has_citations = len(citations) > 0
            has_draft = bool(data.get("draft_text"))

        return {
            "scenario": "Policy Retrieval & Citations (Return Policy)",
            "passed": ok and has_citations and has_draft,
            "citations_count": len(citations),
            "status_code": r.status_code,
        }

    async def run_all(self) -> Dict[str, Any]:
        sc_a = await self.run_scenario_multi_turn_order_tracking()
        sc_b = await self.run_scenario_financial_refund_interception()
        sc_c = await self.run_scenario_policy_retrieval_and_citations()

        total = 3
        passed = sum([1 for sc in [sc_a, sc_b, sc_c] if sc["passed"]])

        return {
            "total_scenarios": total,
            "passed_scenarios": passed,
            "pass_rate": round((passed / total) * 100, 2),
            "scenarios": [sc_a, sc_b, sc_c],
        }

