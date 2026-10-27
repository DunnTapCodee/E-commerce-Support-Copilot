"""ReAct Agent & Multi-Entity Extractor for Dynamic Order Tool Calling (Module 3)."""
import os
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

from contracts.schemas import ToolCallRecord
from services.gateway.src.tools import TOOL_DEFINITIONS, ToolExecutor

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Regular Expression Patterns
RE_BASELINE_ORDER = re.compile(r"\bORD-[A-Z0-9-]+\b", re.IGNORECASE)
RE_EXTENDED_ORDER = re.compile(
    r"\bORD\s*[-_:]?\s*(\d{4,}(?:-[A-Z0-9]+)?)\b|"
    r"\b(?:đơn\s*(?:hàng)?|order|check|kiểm\s+tra|tra\s+cứu)\s*(?:số|mã|id|code|no\.?|num|number|#)?\s*[:#-]?\s*(\d{4,}(?:-[A-Z0-9]+)?)\b|"
    r"#\s*(\d{4,}(?:-[A-Z0-9]+)?)\b",
    re.IGNORECASE,
)
RE_PHONE = re.compile(
    r"(?:(?:\+84|0)[.\s-]*(?:3|5|7|8|9)(?:[.\s-]*\d){8})\b|"
    r"\b0\d{3}[.\s-]+\d{3}[.\s-]+\d{3}\b|"
    r"\b0\d{9}\b",
    re.IGNORECASE,
)
RE_TRACKING = re.compile(r"\b(?:GIAO|GHN|VTP|SPX)[A-Z0-9]{6,}\b", re.IGNORECASE)


def extract_entities_baseline(query: str) -> Dict[str, Optional[str]]:
    """Baseline regex extraction: only matches strict uppercase ORD-xxxx tokens."""
    match = RE_BASELINE_ORDER.search(query)
    return {
        "order_id": match.group(0).upper() if match else None,
        "phone": None,
        "tracking_code": None,
    }


def extract_entities_advanced(
    query: str, fallback_customer_id: Optional[str] = None
) -> Dict[str, Any]:
    """Advanced entity extraction supporting colloquial syntax, typos, phones, and tracking numbers."""
    extracted_order = None
    extracted_phone = None
    extracted_tracking = None
    action_type = "lookup"

    # 1. Phone number extraction first (with masking)
    m_phone = RE_PHONE.search(query)
    if m_phone:
        extracted_phone = m_phone.group(0).strip()

    # Mask phone from query to prevent phone digits (e.g. 0999) from being falsely matched as order ID
    query_masked = query
    if m_phone:
        query_masked = query[:m_phone.start()] + " " + query[m_phone.end():]

    # 2. Tracking code extraction
    m_track = RE_TRACKING.search(query_masked)
    if m_track:
        extracted_tracking = m_track.group(0).upper()
        query_masked = query_masked[:m_track.start()] + " " + query_masked[m_track.end():]

    # 3. Order ID extraction from masked query
    m_order = RE_EXTENDED_ORDER.search(query_masked)
    if m_order:
        num = m_order.group(1) or m_order.group(2) or m_order.group(3)
        if num:
            extracted_order = f"ORD-{num.upper()}"
        else:
            extracted_order = m_order.group(0).upper()
            extracted_order = re.sub(r"^ORD\s*[-_:]\s*", "ORD-", extracted_order)
            if not extracted_order.startswith("ORD-"):
                extracted_order = "ORD-" + extracted_order.lstrip("#")
    else:
        m_base = RE_BASELINE_ORDER.search(query_masked)
        if m_base:
            extracted_order = m_base.group(0).upper()

    # 4. Action intent detection
    q_lower = query.lower()
    cancel_keywords = [
        "hủy đơn", "hủy hàng", "cancel", "bỏ đơn", "không mua nữa",
        "trả lại tiền", "hủy giúp", "hủy ord", "muốn hủy", "hủy order", "stop order"
    ]
    status_keywords = [
        "trạng thái", "tới đâu", "ở đâu", "giao chưa", "khi nào nhận",
        "vận chuyển", "tracking", "bưu tá", "bao giờ tới", "bao giờ nhận",
        "lịch trình", "đi tới", "người giao", "thời gian giao", "kiểm tra",
        "tra cứu", "check", "track", "status", "where is", "delivery"
    ]
    details_keywords = [
        "chi tiết", "những món gì", "tổng tiền", "hóa đơn", "xem đơn",
        "mua gì", "món gì", "detail", "details", "item", "items"
    ]
    customer_list_keywords = [
        "các đơn", "danh sách đơn", "tất cả đơn", "lịch sử đơn",
        "đã mua những gì", "list order", "all orders", "my orders"
    ]

    if any(k in q_lower for k in cancel_keywords):
        action_type = "cancel"
    elif any(k in q_lower for k in details_keywords):
        action_type = "details"
    elif any(k in q_lower for k in status_keywords):
        action_type = "status"
    elif any(k in q_lower for k in customer_list_keywords):
        action_type = "customer_orders"

    # Extract reason for cancellation if present
    cancel_reason = "Khách hàng yêu cầu hủy đơn qua chat"
    if "vì" in q_lower:
        cancel_reason = query.split("vì", 1)[1].strip(" .,?!")
    elif "do" in q_lower:
        cancel_reason = query.split("do", 1)[1].strip(" .,?!")

    return {
        "order_id": extracted_order,
        "phone": extracted_phone,
        "tracking_code": extracted_tracking,
        "action": action_type,
        "cancel_reason": cancel_reason,
        "customer_id": fallback_customer_id,
    }


class OrderReActAgent:
    """ReAct / Tool-Calling Agent determining dynamic order actions and executing tools."""

    def __init__(self, executor: ToolExecutor):
        self.executor = executor

    async def run(
        self, query: str, customer_id: Optional[str] = None
    ) -> Tuple[List[ToolCallRecord], Optional[Dict[str, Any]], str]:
        """Process inquiry, decide which tool(s) to call, execute them, and formulate synthesis context."""
        records: List[ToolCallRecord] = []
        resolved_order_data: Optional[Dict[str, Any]] = None
        synthesis_text = ""

        # Check if Gemini Function Calling should be called
        if GEMINI_API_KEY:
            tool_decisions = await self._decide_tools_gemini(query)
            if tool_decisions:
                for tool_name, args in tool_decisions:
                    rec = await self.executor.execute(tool_name, args)
                    records.append(rec)
                    if isinstance(rec.result, dict) and "order_id" in rec.result:
                        resolved_order_data = rec.result

        # Fallback to local heuristic ReAct decision engine
        if not records:
            entities = extract_entities_advanced(query, customer_id)
            order_id = entities.get("order_id")
            phone = entities.get("phone")
            tracking = entities.get("tracking_code")
            action = entities.get("action")

            # Decision 1: Cancellation Tool
            if action == "cancel" and order_id:
                rec = await self.executor.execute(
                    "cancel_order",
                    {"order_id": order_id, "reason": entities.get("cancel_reason")},
                )
                records.append(rec)
                if isinstance(rec.result, dict):
                    resolved_order_data = rec.result.get("order")

            # Decision 2: Order Status Check Tool
            elif action == "status" or phone or tracking:
                ident = order_id or tracking or phone or customer_id
                if ident:
                    rec = await self.executor.execute("check_order_status", {"identifier": ident})
                    records.append(rec)
                    # For phone lookups without specific order_id, check for multiple orders
                    if phone and not order_id and not tracking:
                        orders_list = await self.executor.clients.lookup_orders_by_phone(phone)
                        if len(orders_list) > 1:
                            resolved_order_data = {
                                "phone": phone,
                                "customer_name": orders_list[0].get("customer_name"),
                                "total_orders": len(orders_list),
                                "orders": orders_list,
                            }
                        elif orders_list:
                            resolved_order_data = orders_list[0]
                    else:
                        full_order = await self.executor.clients.lookup_order(ident)
                        if full_order:
                            resolved_order_data = full_order

            # Decision 3: List Customer Orders Tool
            elif action == "customer_orders" and customer_id:
                rec = await self.executor.execute("get_customer_orders", {"customer_id": customer_id})
                records.append(rec)

            # Decision 4: Order Details Tool
            elif order_id:
                rec = await self.executor.execute("get_order_details", {"order_id": order_id})
                records.append(rec)
                if isinstance(rec.result, dict):
                    resolved_order_data = rec.result

            # Decision 5: General fallback by customer_id if no specific entity mentioned
            elif customer_id:
                full_order = await self.executor.clients.lookup_order(customer_id)
                if full_order:
                    resolved_order_data = full_order

        # Build synthesized summary text for LLM generation context
        if records:
            summary_parts = []
            for r in records:
                if isinstance(r.result, dict) and r.result.get("total_orders", 0) > 1:
                    total = r.result["total_orders"]
                    cname = r.result.get("customer_name", "")
                    briefs = []
                    for o in r.result.get("orders", []):
                        oid = o.get("order_id")
                        stt = o.get("order_status")
                        carrier = o.get("carrier") or "Đang xử lý tại kho"
                        amt = f"{o.get('total_amount', 0):,}đ"
                        briefs.append(f"• Mã {oid}: {amt}, Trạng thái: {stt} ({carrier})")
                    summary_parts.append(
                        f"[Tra cứu SĐT {r.arguments.get('identifier')} (Khách hàng: {cname}): Tìm thấy {total} đơn hàng:\n"
                        + "\n".join(briefs)
                        + "\nTrợ lý CSKH hãy tóm tắt danh sách các đơn hàng này cho khách hàng và hỏi khách muốn xử lý đơn nào.]"
                    )
                else:
                    summary_parts.append(f"[Tool: {r.tool_name}({r.arguments}) -> Kết quả: {r.result}]")
            synthesis_text = "\n".join(summary_parts)

        return records, resolved_order_data, synthesis_text

    async def _decide_tools_gemini(self, query: str) -> List[Tuple[str, Dict[str, Any]]]:
        """Optionally prompt Gemini with tool declarations to return structured function calls."""
        return []
