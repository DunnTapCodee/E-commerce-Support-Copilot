"""Standardized Function Tools and Dispatcher for Order Management (Module 3)."""
import re
import time
from typing import Any, Dict, List, Optional

from contracts.schemas import ToolCallRecord
from services.gateway.src.clients import MicroserviceClients
from services.telemetry_service.src.cache import normalize_phone


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_details",
            "description": "Tra cứu toàn bộ thông tin chi tiết của đơn hàng (danh sách sản phẩm, số tiền, hình thức thanh toán).",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Mã đơn hàng cần tra cứu (ví dụ: ORD-1001, ORD-1025).",
                    }
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_order_status",
            "description": "Tra cứu trạng thái xử lý, vận chuyển và thời gian dự kiến giao hàng qua mã đơn, số điện thoại hoặc mã vận đơn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "identifier": {
                        "type": "string",
                        "description": "Mã định danh: mã đơn hàng (ORD-xxxx), số điện thoại (0938.242.854), hoặc mã vận đơn (GIAOxxx).",
                    }
                },
                "required": ["identifier"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_order",
            "description": "Hủy đơn hàng nếu đơn hàng chưa giao và còn trong điều kiện được phép hủy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "Mã đơn hàng cần hủy (ví dụ: ORD-1026).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Lý do hủy đơn hàng do khách hàng cung cấp.",
                    },
                },
                "required": ["order_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_customer_orders",
            "description": "Lấy danh sách tất cả các đơn hàng thuộc về một tài khoản khách hàng.",
            "parameters": {
                "type": "object",
                "properties": {
                    "customer_id": {
                        "type": "string",
                        "description": "Mã tài khoản khách hàng (ví dụ: demo-customer, CUST-1001).",
                    }
                },
                "required": ["customer_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_orders",
            "description": "Tìm kiếm đơn hàng theo tên món hàng/sản phẩm, tên khách hàng hoặc thuộc tính khi khách không có mã đơn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "product_name": {
                        "type": "string",
                        "description": "Tên sản phẩm cần tìm (ví dụ: bình giữ nhiệt, chuột không dây).",
                    },
                    "customer_name": {
                        "type": "string",
                        "description": "Tên khách hàng đặt đơn (ví dụ: Hoàng Mai Yến, Trần Đức Nam).",
                    },
                    "brand_or_attributes": {
                        "type": "string",
                        "description": "Thương hiệu hoặc thuộc tính sản phẩm (ví dụ: Lock&Lock, 800ml).",
                    },
                    "status": {
                        "type": "string",
                        "description": "Trạng thái đơn hàng (ví dụ: Shipping, Cancelled).",
                    },
                },
            },
        },
    },
]


class ToolExecutor:
    """Dispatches tool calls to downstream microservices and measures latency."""

    def __init__(self, clients: MicroserviceClients):
        self.clients = clients

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> ToolCallRecord:
        """Execute a named tool with provided arguments."""
        start_time = time.perf_counter()
        result: Any = None

        try:
            if tool_name == "get_order_details":
                order_id = str(arguments.get("order_id", "")).strip()
                result = await self.clients.lookup_order(order_id)

            elif tool_name == "check_order_status":
                identifier = str(arguments.get("identifier", "")).strip()
                phone_digits = normalize_phone(identifier)
                if phone_digits and len(phone_digits) >= 9:
                    orders = await self.clients.lookup_orders_by_phone(identifier)
                    if orders:
                        if len(orders) > 1:
                            result = {
                                "identifier": identifier,
                                "customer_name": orders[0].get("customer_name"),
                                "total_orders": len(orders),
                                "orders": [
                                    {
                                        "order_id": o.get("order_id"),
                                        "order_status": o.get("order_status"),
                                        "total_amount": o.get("total_amount"),
                                        "carrier": o.get("carrier"),
                                        "tracking_code": o.get("tracking_code"),
                                        "estimated_delivery": o.get("estimated_delivery"),
                                        "latest_timeline": (o.get("shipping_timeline") or [{}])[-1],
                                    }
                                    for o in orders
                                ],
                            }
                        else:
                            o = orders[0]
                            result = {
                                "order_id": o.get("order_id"),
                                "order_status": o.get("order_status"),
                                "customer_name": o.get("customer_name"),
                                "total_amount": o.get("total_amount"),
                                "carrier": o.get("carrier"),
                                "tracking_code": o.get("tracking_code"),
                                "estimated_delivery": o.get("estimated_delivery"),
                                "total_orders": 1,
                                "latest_timeline": (o.get("shipping_timeline") or [{}])[-1],
                            }
                    else:
                        result = {"found": False, "identifier": identifier, "message": "Không tìm thấy đơn hàng cho số điện thoại này."}
                else:
                    order = await self.clients.lookup_order(identifier)
                    if order:
                        result = {
                            "order_id": order.get("order_id"),
                            "order_status": order.get("order_status"),
                            "carrier": order.get("carrier"),
                            "tracking_code": order.get("tracking_code"),
                            "estimated_delivery": order.get("estimated_delivery"),
                            "latest_timeline": (order.get("shipping_timeline") or [{}])[-1],
                        }
                    else:
                        result = {"found": False, "identifier": identifier, "message": "Không tìm thấy đơn hàng."}

            elif tool_name == "cancel_order":
                order_id = str(arguments.get("order_id", "")).strip()
                reason = str(arguments.get("reason", "Khách hàng yêu cầu hủy đơn qua chat")).strip()
                result = await self.clients.cancel_order(order_id, reason)

            elif tool_name == "get_customer_orders":
                customer_id = str(arguments.get("customer_id", "")).strip()
                orders = await self.clients.get_customer_orders(customer_id)
                result = {"customer_id": customer_id, "total": len(orders), "orders": orders}

            elif tool_name == "search_orders":
                pname = str(arguments.get("product_name") or "").strip().lower()
                cname = str(arguments.get("customer_name") or "").strip().lower()
                brand = str(arguments.get("brand_or_attributes") or "").strip().lower()
                stt = str(arguments.get("status") or "").strip().lower()
                result = self._search_orders_multi_criteria(pname, cname, brand, stt)

            else:
                result = {"error": f"Tool '{tool_name}' is not recognized."}

        except Exception as e:
            result = {"error": str(e)}

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
        return ToolCallRecord(
            tool_name=tool_name,
            arguments=arguments,
            result=result,
            latency_ms=latency_ms,
        )

    def _search_orders_multi_criteria(
        self,
        product_name: str = "",
        customer_name: str = "",
        brand: str = "",
        status: str = "",
    ) -> Dict[str, Any]:
        """Rank and return orders matching natural language criteria (product, customer, brand, status)."""
        import json
        from pathlib import Path

        json_path = Path(__file__).resolve().parent.parent.parent.parent / "data" / "mock_orders.json"
        if not json_path.exists():
            return {"found": False, "message": "Database mock_orders.json not found."}

        with open(json_path, "r", encoding="utf-8") as f:
            all_orders = json.load(f)

        scored: List[Tuple[float, Dict[str, Any], List[str]]] = []
        for o in all_orders:
            score = 0.0
            reasons = []

            # 1. Customer Name (0 - 50)
            if customer_name:
                cust = str(o.get("customer_name", "")).lower()
                if customer_name == cust:
                    score += 50.0
                    reasons.append(f"exact_customer:{cust}")
                elif customer_name in cust or cust in customer_name:
                    score += 42.0
                    reasons.append(f"partial_customer:{cust}")

            # 2. Product Name / Type (0 - 45)
            if product_name:
                best_item_score = 0.0
                for it in o.get("items", []):
                    iname = str(it.get("name", "")).lower()
                    if product_name in iname:
                        best_item_score = max(best_item_score, 45.0)
                    else:
                        p_words = set(product_name.split())
                        i_words = set(iname.split())
                        overlap = len(p_words & i_words)
                        if overlap >= 2:
                            best_item_score = max(best_item_score, 30.0 * (overlap / max(1, len(p_words))))
                if best_item_score > 0:
                    score += best_item_score
                    reasons.append(f"product:{product_name}")

            # 3. Brand or Attributes (0 - 25)
            if brand:
                for it in o.get("items", []):
                    iname = str(it.get("name", "")).lower()
                    if brand in iname:
                        score += 25.0
                        reasons.append(f"brand:{brand}")
                        break

            # 4. Status (0 - 15)
            if status:
                ostt = str(o.get("order_status", "")).lower()
                if status in ostt or ostt in status:
                    score += 15.0
                    reasons.append(f"status:{ostt}")

            if score > 0:
                scored.append((score, o, reasons))

        if not scored:
            return {"found": False, "message": "Không tìm thấy đơn hàng phù hợp với các tiêu chí tìm kiếm."}

        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[0][1]
        top_score = scored[0][0]
        reasons = scored[0][2]

        return {
            "found": True,
            "total_found": len(scored),
            "best_match": best,
            "confidence": min(1.0, round(top_score / 100.0, 2)),
            "reasons": reasons,
            "matches": [
                {
                    "order_id": o.get("order_id"),
                    "customer_name": o.get("customer_name"),
                    "order_status": o.get("order_status"),
                    "total_amount": o.get("total_amount"),
                    "items": [it.get("name") for it in o.get("items", [])],
                }
                for _, o, _ in scored[:5]
            ],
        }
