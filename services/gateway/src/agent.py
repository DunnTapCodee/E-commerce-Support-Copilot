"""ReAct Agent & Multi-Entity Extractor for Dynamic Order Tool Calling (Module 3)."""
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from contracts.schemas import ToolCallRecord
from services.gateway.src.tools import TOOL_DEFINITIONS, ToolExecutor

# Auto-load .env if not in environment
_env_file = Path(__file__).resolve().parent.parent.parent.parent / ".env"
if _env_file.exists():
    try:
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    if _k.strip() not in os.environ:
                        os.environ[_k.strip()] = _v.strip()
    except Exception:
        pass

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

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
        """Process inquiry, extract entities via Gemini/Regex, execute dynamic tools, and synthesize context."""
        records: List[ToolCallRecord] = []
        resolved_order_data: Optional[Dict[str, Any]] = None
        synthesis_text = ""

        # 1. Trích xuất thực thể bằng LLM (Ckey openai-gpt-oss-20b / Gemini)
        entities = await self._extract_entities_llm(query)

        # 2. Bổ trợ bằng Regex (fallback nếu LLM rỗng, lỗi mạng, hoặc chưa cấu hình key)
        regex_entities = extract_entities_advanced(query, customer_id)
        if not entities:
            entities = regex_entities
        else:
            # Gộp thông tin: nếu trường nào LLM chưa nhận diện được thì lấy từ regex
            for k in ["order_id", "phone", "tracking_code", "action", "cancel_reason"]:
                if not entities.get(k) and regex_entities.get(k):
                    entities[k] = regex_entities[k]

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

        # Decision 3: Natural language search by product/customer/attributes (e.g. "bình giữ nhiệt của Hoàng Mai Yến")
        elif not order_id and not phone and not tracking and (entities.get("product_name") or entities.get("customer_name") or entities.get("brand_or_attributes")):
            pname = entities.get("product_name") or ""
            cname = entities.get("customer_name") or ""
            brand = entities.get("brand_or_attributes") or ""
            stt = entities.get("status_hint") or ""

            rec = await self.executor.execute(
                "search_orders",
                {
                    "product_name": pname,
                    "customer_name": cname,
                    "brand_or_attributes": brand,
                    "status": stt,
                },
            )
            records.append(rec)
            if isinstance(rec.result, dict) and rec.result.get("found"):
                best_order = rec.result.get("best_match")
                resolved_order_data = best_order
                # If the customer's intent was to cancel this identified order
                if action == "cancel" and best_order and best_order.get("order_id"):
                    cancel_rec = await self.executor.execute(
                        "cancel_order",
                        {
                            "order_id": best_order["order_id"],
                            "reason": entities.get("cancel_reason") or "Khách yêu cầu hủy qua chat",
                        },
                    )
                    records.append(cancel_rec)
                    if isinstance(cancel_rec.result, dict) and cancel_rec.result.get("order"):
                        resolved_order_data = cancel_rec.result.get("order")

        # Decision 4: List Customer Orders Tool
        elif action == "customer_orders" and customer_id:
            rec = await self.executor.execute("get_customer_orders", {"customer_id": customer_id})
            records.append(rec)

        # Decision 5: Order Details Tool
        elif order_id:
            rec = await self.executor.execute("get_order_details", {"order_id": order_id})
            records.append(rec)
            if isinstance(rec.result, dict):
                resolved_order_data = rec.result

        # Decision 6: General fallback by customer_id if no specific entity mentioned
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
                elif r.tool_name == "search_orders" and isinstance(r.result, dict):
                    res = r.result
                    best = res.get("best_match", {})
                    total = res.get("total_found", 0)
                    oid = best.get("order_id")
                    cname = best.get("customer_name")
                    stt = best.get("order_status")
                    amt = f"{best.get('total_amount', 0):,}đ"
                    items = ", ".join(i.get("name", "") for i in best.get("items", []))
                    if total > 1 and not r.arguments.get("customer_name"):
                        summary_parts.append(
                            f"[Tìm kiếm đơn hàng theo '{r.arguments.get('product_name')}': Tìm thấy {total} đơn phù hợp. "
                            f"Đơn khớp tiêu biểu nhất: Mã {oid} (Khách: {cname}), trạng thái: {stt}, sản phẩm: {items}, số tiền: {amt}. "
                            f"Trợ lý CSKH hãy phản hồi thông tin đơn này hoặc hỏi khách mã đơn cụ thể nếu cần.]"
                        )
                    else:
                        summary_parts.append(
                            f"[Tìm thấy chính xác đơn hàng theo thông tin khách cung cấp: "
                            f"Mã đơn: {oid}, Khách hàng: {cname}, Trạng thái: {stt}, Sản phẩm: {items}, Tổng tiền: {amt}.]"
                        )
                else:
                    summary_parts.append(f"[Tool: {r.tool_name}({r.arguments}) -> Kết quả: {r.result}]")
            synthesis_text = "\n".join(summary_parts)

        return records, resolved_order_data, synthesis_text

    async def _extract_entities_llm(self, query: str) -> Optional[Dict[str, Any]]:
        """Call LLM (Ckey OpenAI-compatible or Gemini) to intelligently extract comprehensive order entity parameters."""
        api_key = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY") or ""
        if not api_key or api_key.startswith("your_"):
            return None

        provider = os.getenv("LLM_PROVIDER", "auto").lower()
        base_url = os.getenv("LLM_BASE_URL", "")
        timeout_sec = float(os.getenv("LLM_EXTRACT_TIMEOUT", "20"))

        system_prompt = (
            "Bạn là trợ lý AI chuyên bóc tách thực thể tra cứu đơn hàng thương mại điện tử Tiki.\n"
            "Nhiệm vụ: Trích xuất TẤT CẢ các thông tin liên quan từ câu nói của khách hàng và trả về DUY NHẤT một chuỗi JSON hợp lệ không kèm lời giải thích:\n"
            "{\n"
            '  "order_id": string hoặc null (chuẩn hóa về dạng "ORD-XXXX", ví dụ: "1003", "#1003", "ORD 1003" -> "ORD-1003"),\n'
            '  "phone": string hoặc null (chuẩn hóa chuỗi số liền, ví dụ "0999 532 448" -> "0999532448"),\n'
            '  "tracking_code": string hoặc null (mã vận đơn, ví dụ GHN..., GIAO..., TIKI...),\n'
            '  "customer_name": string hoặc null (tên khách hàng người mua, ví dụ "Hoàng Mai Yến", "Trần Đức Nam"),\n'
            '  "product_name": string hoặc null (tên món hàng/loại sản phẩm, ví dụ "bình giữ nhiệt", "sạc dự phòng", "tai nghe"),\n'
            '  "brand_or_attributes": string hoặc null (thương hiệu, màu sắc, dung tích, ví dụ "Lock&Lock", "800ml", "màu đen"),\n'
            '  "status_hint": string hoặc null (gợi ý trạng thái đơn: "Shipping", "Cancelled", "Delivered", "Processing", "Returned"),\n'
            '  "action": string ("status", "cancel", "details", "search", "customer_orders"),\n'
            '  "cancel_reason": string hoặc null (lý do hủy nếu có, ví dụ "giao hàng lâu quá")\n'
            "}"
        )

        def try_parse_json(text: str) -> Optional[Dict[str, Any]]:
            if not text:
                return None
            cleaned = text
            if "```json" in cleaned:
                cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in cleaned:
                cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()
            try:
                return json.loads(cleaned)
            except Exception:
                m = re.search(r"\{[\s\S]*\}", cleaned)
                if m:
                    try:
                        return json.loads(m.group(0))
                    except Exception:
                        pass
            return None

        is_openai = provider == "openai" or bool(base_url) or (api_key.startswith("sk-") and not api_key.startswith("AQ."))

        if is_openai:
            endpoint = f"{base_url.rstrip('/')}/chat/completions" if base_url else "https://api.xah.io/v1/chat/completions"
            model = os.getenv("LLM_MODEL", "openai-gpt-oss-20b")
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                "temperature": 0.0,
                "max_tokens": 800,
            }
            try:
                async with httpx.AsyncClient(timeout=timeout_sec, verify=False) as client:
                    resp = await client.post(
                        endpoint,
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json=payload,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        msg = data["choices"][0]["message"]
                        content = (msg.get("content") or "").strip()
                        reasoning = (msg.get("reasoning_content") or "").strip()

                        parsed = try_parse_json(content)
                        if not parsed and reasoning:
                            parsed = try_parse_json(reasoning)
                        if parsed:
                            return parsed
                    else:
                        print(f"[OrderReActAgent] OpenAI-compatible HTTP Error {resp.status_code}: {resp.text}")
            except Exception as e:
                print(f"[OrderReActAgent] OpenAI-compatible extraction failed/timed out: {type(e).__name__} ({e})")
        else:
            # Fallback to Google Gemini
            model = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
            payload = {
                "contents": [{"parts": [{"text": f"{system_prompt}\n\nCâu của khách hàng: \"{query}\""}]}],
                "generationConfig": {"temperature": 0.0, "responseMimeType": "application/json"},
            }
            try:
                async with httpx.AsyncClient(timeout=timeout_sec, verify=False) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                        return try_parse_json(text)
                    else:
                        print(f"[OrderReActAgent] Gemini HTTP Error {resp.status_code}: {resp.text}")
            except Exception as e:
                print(f"[OrderReActAgent] Gemini entity extraction failed/timed out: {type(e).__name__} ({e})")

        return None
