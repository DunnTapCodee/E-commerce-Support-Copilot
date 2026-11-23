"""In-chat order action extraction & deterministic eligibility guardrails.

Shared by Conversation Service, Gateway fallback, and Telemetry Service so
proposals are never executed without explicit CS Staff approval (HITL).
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, Optional, Tuple

from contracts.safety import is_order_owned_by_customer
from contracts.schemas import OrderActionProposal, OrderActionType, get_system_now

_CANCEL_CUES = re.compile(
    r"\b(hủy\s+đơn|huy\s+don|hủy\s+lệnh|cancel\s+order|không\s+mua\s+nữa|đặt\s+nhầm)\b",
    re.IGNORECASE,
)
_RETURN_CUES = re.compile(
    r"\b(muốn\s+trả\s+hàng|yêu\s+cầu\s+trả|đổi\s+trả\s+đơn|hoàn\s+hàng|trả\s+lại\s+sản\s+phẩm|return\s+order)\b",
    re.IGNORECASE,
)
_ADDRESS_CUES = re.compile(
    r"(?:đổi|thay\s+đổi|sửa|cập\s+nhật|chuyển)\s*(?:giúp\s+(?:mình|em|tôi)\s+)?(?:địa\s+chỉ(?:\s+giao(?:\s+hàng)?)?|nơi\s+nhận)\s*(?:mới\s*)?(?:thành|sang|về|tới|là|:)?\s*([^\n!?]{6,140})"
    r"|(?:giao\s+(?:về|tới|sang)\s+địa\s+chỉ)\s*(?:mới\s*)?(?:là|:)?\s*([^\n!?]{6,140})",
    re.IGNORECASE,
)
_PHONE_EXTRACT_RE = re.compile(
    r"(?:đổi|sửa|cập\s+nhật)\s*(?:giúp\s+)?(?:số\s+điện\s+thoại|sđt|sdt|số\s+liên\s+hệ)\s*(?:người\s+nhận\s*)?(?:mới\s*)?(?:thành|sang|là|:)?\s*(0\d[\d.\s-]{7,13}\d)",
    re.IGNORECASE,
)
_RECEIVER_NAME_RE = re.compile(
    r"(?:đổi|sửa|cập\s+nhật)\s*(?:tên\s+)?người\s+nhận\s*(?:hàng\s*)?(?:mới\s*)?(?:thành|sang|là|:)?\s*([^\n,.!?0-9]{2,60})",
    re.IGNORECASE,
)


def evaluate_order_action_eligibility(
    action_type: OrderActionType,
    order_data: Optional[Dict[str, Any]],
) -> Tuple[bool, Optional[str]]:
    """Deterministic eligibility check against current order_status."""
    if not order_data:
        return False, "Chưa xác định được đơn hàng hợp lệ thuộc tài khoản khách."

    status_raw = str(order_data.get("order_status") or order_data.get("status") or "").strip()
    status_upper = status_raw.upper()

    if action_type == "cancel_order":
        if status_upper in {"CANCELLED", "RETURNED", "RETURN_REQUESTED", "DELIVERED"}:
            return False, f"Đơn hàng đã ở trạng thái '{status_raw}' nên không thể hủy."
        if status_upper in {"SHIPPING", "IN_TRANSIT"} or order_data.get("can_cancel") is False:
            return (
                False,
                f"Đơn hàng đang vận chuyển ('{status_raw}') đã bàn giao đơn vị giao nhận, không thể hủy trực tiếp.",
            )
        return True, None

    if action_type in {"update_address", "update_receiver"}:
        if status_upper in {"PROCESSING", "PAYMENT_FAILED"}:
            return True, None
        return (
            False,
            f"Chỉ được đổi địa chỉ/người nhận khi đơn đang 'Processing'; hiện đơn đang '{status_raw}'.",
        )

    if action_type == "return_product":
        if status_upper in {"DELIVERED", "RETURN_APPROVED"}:
            return True, None
        return (
            False,
            f"Chỉ áp dụng trả hàng khi đơn đã giao thành công ('Delivered'); hiện đơn đang '{status_raw}'.",
        )

    return False, f"Loại yêu cầu '{action_type}' không được hỗ trợ."


def detect_order_action_intent(
    customer_query: str, intent: Optional[str] = None
) -> Optional[Tuple[OrderActionType, Dict[str, Any]]]:
    """Identify structured order modification intent & proposed field values from chat text."""
    if not customer_query:
        return None
    q = customer_query.strip()

    # Check receiver/address modification cues first so they don't get masked by generic track/delivery intent
    addr_match = _ADDRESS_CUES.search(q)
    if addr_match:
        new_addr = (addr_match.group(1) or addr_match.group(2) or "").strip(" ,.;:")
        if len(new_addr) >= 6:
            return "update_address", {"shipping_address": new_addr}

    phone_match = _PHONE_EXTRACT_RE.search(q)
    recv_match = _RECEIVER_NAME_RE.search(q)
    if phone_match or recv_match:
        proposed: Dict[str, Any] = {}
        if recv_match:
            proposed["customer_name"] = recv_match.group(1).strip(" ,.;:")
        if phone_match:
            proposed["phone"] = phone_match.group(1).strip()
        if proposed:
            return "update_receiver", proposed

    if intent == "cancel_order" or _CANCEL_CUES.search(q):
        return "cancel_order", {"order_status": "Cancelled", "can_cancel": False}

    if intent == "return_product" or _RETURN_CUES.search(q):
        return "return_product", {"order_status": "Return_Requested"}

    return None


def extract_order_action_proposal(
    customer_query: str,
    intent: Optional[str],
    order_data: Optional[Dict[str, Any]],
    customer_id: Optional[str],
    session_id: Optional[str] = None,
    interaction_id: Optional[str] = None,
) -> Optional[OrderActionProposal]:
    """Build a read-only PENDING OrderActionProposal if query asks to modify an owned order."""
    if not order_data or not order_data.get("order_id"):
        return None
    if not is_order_owned_by_customer(order_data, customer_id):
        return None

    detected = detect_order_action_intent(customer_query, intent=intent)
    if not detected:
        return None

    action_type, proposed_values = detected
    eligible, ineligibility_reason = evaluate_order_action_eligibility(action_type, order_data)

    if action_type == "cancel_order":
        before_values = {
            "order_status": order_data.get("order_status") or order_data.get("status"),
            "can_cancel": bool(order_data.get("can_cancel", True)),
        }
    elif action_type == "update_address":
        before_values = {
            "shipping_address": order_data.get("shipping_address") or "Chưa cập nhật",
        }
    elif action_type == "update_receiver":
        before_values = {}
        if "customer_name" in proposed_values:
            before_values["customer_name"] = order_data.get("customer_name") or ""
        if "phone" in proposed_values:
            before_values["phone"] = order_data.get("phone") or ""
    else:
        before_values = {
            "order_status": order_data.get("order_status") or order_data.get("status"),
        }

    return OrderActionProposal(
        action_id=f"act_{uuid.uuid4().hex[:10]}",
        interaction_id=interaction_id,
        session_id=session_id,
        order_id=str(order_data["order_id"]),
        customer_id=str(order_data.get("customer_id") or customer_id or ""),
        action_type=action_type,
        before_values=before_values,
        proposed_values=proposed_values,
        eligible=eligible,
        ineligibility_reason=ineligibility_reason,
        customer_reason=customer_query.strip(),
        status="PENDING",
        created_at=get_system_now(),
    )
