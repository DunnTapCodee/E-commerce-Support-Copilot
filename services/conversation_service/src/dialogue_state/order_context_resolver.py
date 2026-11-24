"""Data-driven Scoped Order Context Resolver for Conversation Service.

Separates order lookup, IDOR ownership checks, and multi-order portfolio assembly
from HTTP/FastAPI routing in main.py.
"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from services.conversation_service.src.dialogue_state.state import ConversationState


def detect_order_status_filter(customer_query: str) -> Optional[Tuple[set[str], str]]:
    """Detect whether the customer is filtering their orders by canonical order_status."""
    q = (customer_query or "").lower()
    if any(k in q for k in ("giao trễ", "bị trễ", "chậm giao", "quá hạn", "delay", "trễ hẹn")):
        return {"DELIVERY_DELAYED"}, "đang bị giao trễ"
    if any(k in q for k in ("đang xử lý", "chờ xử lý", "chưa đóng gói", "processing")):
        return {"PROCESSING"}, "đang xử lý"
    if any(k in q for k in ("đang giao", "đang vận chuyển", "trên đường giao", "shipping", "in_transit")):
        return {"SHIPPING", "IN_TRANSIT"}, "đang vận chuyển"
    if any(k in q for k in ("đã giao", "hoàn thành", "delivered")):
        return {"DELIVERED"}, "đã giao thành công"
    if any(k in q for k in ("đã hủy", "bị hủy", "cancelled")):
        return {"CANCELLED"}, "đã hủy"
    if any(k in q for k in ("trả hàng", "hoàn hàng", "returned")):
        return {"RETURNED", "RETURN_REQUESTED", "RETURN_APPROVED"}, "đổi/trả hàng"
    if any(k in q for k in ("lỗi thanh toán", "thanh toán thất bại", "payment_failed")):
        return {"PAYMENT_FAILED"}, "lỗi thanh toán"
    return None


def compute_portfolio_stats(orders: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compute factual portfolio totals and status breakdown directly from order records."""
    by_status: Dict[str, int] = {}
    paid_orders: List[Dict[str, Any]] = []
    for o in orders:
        st = str(o.get("order_status") or o.get("status") or "Unknown").strip()
        by_status[st] = by_status.get(st, 0) + 1
        if st.upper() not in {"CANCELLED", "PAYMENT_FAILED", "RETURNED"}:
            paid_orders.append(o)
    return {
        "total_orders": len(orders),
        "paid_order_count": len(paid_orders),
        "total_paid_amount": sum(int(o.get("total_amount") or 0) for o in paid_orders),
        "excluded_count": len(orders) - len(paid_orders),
        "by_status": by_status,
    }


def filter_orders_by_dynamic_attributes(
    customer_query: str, orders: List[Dict[str, Any]]
) -> Optional[Tuple[List[Dict[str, Any]], str]]:
    """Data-driven filter matching actual attribute values (payment_method, carrier) present in orders."""
    q_lower = " ".join((customer_query or "").lower().split())
    if not q_lower or not orders:
        return None

    generic_words = {
        "ví", "thẻ", "tín", "dụng", "ngân", "hàng", "giao", "nhanh", "tiết", "kiệm",
        "mua", "trước", "trả", "sau", "chuyển", "khoản", "tiền", "mặt", "điện", "tử",
    }
    for field_name in ("payment_method", "carrier"):
        distinct_vals = {
            str(o.get(field_name) or "").strip()
            for o in orders
            if str(o.get(field_name) or "").strip()
        }
        for raw_val in sorted(distinct_vals, key=len, reverse=True):
            clean_val = re.sub(r"\([^)]*\)", "", raw_val).strip().lower()
            words = [w for w in re.split(r"\s+", clean_val) if w]
            if not words:
                continue
            full_pat = r"\b" + r"\s*".join(re.escape(w) for w in words) + r"\b"
            core_words = [w for w in words if w not in generic_words and len(w) >= 3]
            core_compact = "".join(core_words)
            q_no_space = re.sub(r"\s+", "", q_lower)
            matched_core = bool(core_words) and (
                re.search(r"\b" + r"\s*".join(re.escape(w) for w in core_words) + r"\b", q_lower) is not None
                or (len(core_compact) >= 4 and core_compact in q_no_space)
            )
            if re.search(full_pat, q_lower) or matched_core:
                matched = [o for o in orders if str(o.get(field_name) or "").strip() == raw_val]
                if matched:
                    return matched, raw_val
    return None


def is_multi_order_list_query(customer_query: str) -> bool:
    """Detect generic/list order inquiries that should disambiguate when customer has >1 order."""
    q = " ".join((customer_query or "").lower().split())
    return any(
        k in q
        for k in (
            "đơn nào",
            "những đơn",
            "các đơn",
            "danh sách đơn",
            "tất cả đơn",
            "kiểm tra đơn",
            "tra cứu đơn",
            "xem đơn",
            "đơn hàng của tôi",
            "đơn của tôi",
            "đơn hàng của mình",
            "đơn của mình",
            "lịch sử đơn",
            "lịch sử mua",
            "mấy đơn",
            "bao nhiêu đơn",
        )
    )


def is_personal_order_portfolio_inquiry(customer_query: str) -> bool:
    """Return True only when an unscoped utterance asks about the customer's own orders or spending.

    Prevents general policy questions, account/password help, or off-topic trivia from
    receiving a multi-order portfolio context merely because the customer owns >1 order.
    """
    q = " ".join((customer_query or "").lower().split())
    if not q:
        return False

    if is_multi_order_list_query(q):
        return True

    # General policy / regulation / membership / account questions without personal order ownership cues
    is_general_policy_or_account = any(
        term in q
        for term in (
            "chính sách",
            "quy định",
            "quy chế",
            "điều khoản",
            "thể lệ",
            "biểu phí",
            "gói tikipro",
            "tikipro là",
            "tikinow là",
            "quên mật khẩu",
            "đổi mật khẩu",
            "khôi phục mật khẩu",
            "tạo tài khoản",
            "đăng ký tài khoản",
        )
    ) and not any(p in q for p in ("đơn của mình", "đơn của tôi", "đơn hàng của mình", "đơn hàng của tôi", "mình đặt", "tôi đặt", "em đặt"))
    if is_general_policy_or_account:
        return False

    # 1. Portfolio spending / order-count aggregation inquiries
    if re.search(
        r"\b(tổng\s+(tiền|thanh toán|chi tiêu|đơn)|đã\s+(thanh toán|chi|mua)\s+.*bao nhiêu|bao nhiêu tiền\s+rồi|hết bao nhiêu tiền)\b",
        q,
    ):
        return True

    # 2. Personal order / parcel tracking or delivery status without an explicit ORD-* ID
    has_order_noun = bool(re.search(r"\b(đơn hàng|đơn mua|kiện hàng|bưu kiện|gói hàng)\b", q))
    has_personal_or_status_cue = bool(
        re.search(
            r"\b(ở đâu|đến đâu|tới đâu|sao rồi|như nào rồi|bao giờ giao|khi nào giao|bao giờ nhận|khi nào nhận|tình trạng|tiến độ|xuất kho|của tôi|của mình|mình đặt|tôi đặt|em đặt|vừa đặt)\b",
            q,
        )
    )
    return has_order_noun and has_personal_or_status_cue


async def resolve_scoped_order_and_guard(
    customer_query: str,
    state: ConversationState,
    customer_id: str,
    telemetry_client: Any,
    order_tools: Any,
    load_customer_orders_fn: Callable[[str], Awaitable[List[Dict[str, Any]]]],
) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[Dict[str, Any]]]:
    """Resolve order strictly scoped to customer_id, handling IDOR guards and multi-order portfolio context."""
    from contracts.order_actions import detect_order_action_intent, evaluate_order_action_eligibility
    from contracts.safety import detect_foreign_customer_query, is_order_owned_by_customer
    from services.conversation_service.src.input_pipeline.fact_extractor import (
        extract_all_order_ids,
        extract_facts,
    )
    from services.conversation_service.src.input_pipeline.order_matcher import get_order_matcher

    pre_facts = extract_facts(customer_query, customer_id=customer_id)
    foreign_cid = pre_facts.get("foreign_customer_id") or detect_foreign_customer_query(
        customer_query, customer_id
    )
    if foreign_cid:
        return (
            None,
            f"Truy vấn đề cập mã khách hàng '{foreign_cid}' không thuộc tài khoản đang đăng nhập ({customer_id}).",
            None,
        )

    explicit_oids = extract_all_order_ids(customer_query)
    order_data: Optional[Dict[str, Any]] = None

    # 1. Multiple explicit ORD-* mentions in the same utterance
    if len(explicit_oids) > 1:
        owned_matches: List[Dict[str, Any]] = []
        for oid in explicit_oids:
            cand = await telemetry_client.lookup_order(oid, customer_id=customer_id)
            if not cand:
                cand = order_tools.get_order_by_id(oid, customer_id=customer_id)
            if cand and is_order_owned_by_customer(cand, customer_id):
                owned_matches.append(cand)
        if len(owned_matches) > 1:
            return None, None, {"candidates": owned_matches, "reason": "multiple_explicit_orders"}
        if len(owned_matches) == 1:
            order_data = owned_matches[0]
            state.active_order_id = order_data["order_id"]
            state.facts["order_id"] = order_data["order_id"]
            state.facts["order_cached"] = order_data
            return order_data, None, None

    # 2. Single explicit ORD-* mention in current utterance
    if len(explicit_oids) == 1:
        explicit_oid = explicit_oids[0]
        try:
            order_data = await telemetry_client.lookup_order(explicit_oid, customer_id=customer_id)
        except Exception as exc:
            print(f"[ConversationService] Scoped order lookup error: {exc}")
        if not order_data:
            order_data = order_tools.get_order_by_id(explicit_oid, customer_id=customer_id)

        if order_data and is_order_owned_by_customer(order_data, customer_id):
            state.active_order_id = order_data["order_id"]
            state.facts["order_id"] = order_data["order_id"]
            state.facts["order_cached"] = order_data
            return order_data, None, None

        unscoped_hit: Optional[Dict[str, Any]] = None
        try:
            unscoped_hit = await telemetry_client.lookup_order(explicit_oid)
        except Exception:
            pass
        if not unscoped_hit:
            unscoped_hit = order_tools.get_order_by_id(explicit_oid)
        if unscoped_hit and not is_order_owned_by_customer(unscoped_hit, customer_id):
            return (
                None,
                f"Đơn hàng {explicit_oid} thuộc khách hàng khác; từ chối truy xuất và tiết lộ PII.",
                None,
            )
        return None, None, None

    # 3. No explicit ORD-* in current utterance: check customer's multi-order portfolio
    customer_orders = await load_customer_orders_fn(customer_id)
    portfolio_stats = compute_portfolio_stats(customer_orders) if customer_orders else {}

    # 3a. Data-driven attribute filter (payment_method, carrier) or canonical status filter
    dyn_filter = filter_orders_by_dynamic_attributes(customer_query, customer_orders)
    if dyn_filter:
        filtered, filter_label = dyn_filter
        if len(filtered) == 1 and not is_multi_order_list_query(customer_query):
            order_data = filtered[0]
            state.active_order_id = order_data["order_id"]
            state.facts["order_id"] = order_data["order_id"]
            state.facts["order_cached"] = order_data
            return order_data, None, None
        return (
            None,
            None,
            {
                "candidates": filtered,
                "reason": "status_filter",
                "filter_label": filter_label,
                "computed_summary": compute_portfolio_stats(filtered),
            },
        )

    status_filter = detect_order_status_filter(customer_query)
    if status_filter and customer_orders:
        allowed_statuses, filter_label = status_filter
        filtered = [
            o
            for o in customer_orders
            if str(o.get("order_status") or o.get("status") or "").strip().upper() in allowed_statuses
        ]
        if len(filtered) == 1 and not is_multi_order_list_query(customer_query):
            order_data = filtered[0]
            state.active_order_id = order_data["order_id"]
            state.facts["order_id"] = order_data["order_id"]
            state.facts["order_cached"] = order_data
            return order_data, None, None
        if filtered:
            return (
                None,
                None,
                {
                    "candidates": filtered,
                    "reason": "status_filter",
                    "filter_label": filter_label,
                    "computed_summary": compute_portfolio_stats(filtered),
                },
            )
        return (
            None,
            None,
            {
                "candidates": [],
                "reason": "status_filter_empty",
                "filter_label": filter_label,
                "computed_summary": portfolio_stats,
            },
        )

    # 3b. Ambiguous order-modification intent without explicit ORD-*
    detected_action = detect_order_action_intent(customer_query)
    if detected_action and len(customer_orders) > 1:
        action_type, _ = detected_action
        eligible_orders = [
            o for o in customer_orders if evaluate_order_action_eligibility(action_type, o)[0]
        ]
        if len(eligible_orders) == 1:
            order_data = eligible_orders[0]
            state.active_order_id = order_data["order_id"]
            state.facts["order_id"] = order_data["order_id"]
            state.facts["order_cached"] = order_data
            return order_data, None, None
        if len(eligible_orders) > 1:
            return (
                None,
                None,
                {
                    "candidates": eligible_orders,
                    "reason": f"ambiguous_{action_type}",
                },
            )
        return (
            None,
            None,
            {
                "candidates": customer_orders[:5],
                "reason": f"no_eligible_{action_type}",
            },
        )

    # 3c. Semantic / product match across customer's orders
    try:
        matcher = get_order_matcher()
        if hasattr(matcher, "match_all"):
            product_matches = matcher.match_all(customer_query, customer_id=customer_id, limit=6)
            if len(product_matches) > 1:
                return (
                    None,
                    None,
                    {
                        "candidates": product_matches,
                        "reason": "multiple_matching_orders",
                    },
                )
            if len(product_matches) == 1:
                order_data = product_matches[0]
                state.active_order_id = order_data["order_id"]
                state.facts["order_id"] = order_data["order_id"]
                state.facts["order_cached"] = order_data
                return order_data, None, None
    except Exception as exc:
        print(f"[ConversationService] Multi-order product match skipped: {exc}")

    # 3d. Generic multi-order query when customer has >1 order and asks about their orders/spending
    if len(customer_orders) > 1 and (
        is_multi_order_list_query(customer_query)
        or (not state.active_order_id and is_personal_order_portfolio_inquiry(customer_query))
    ):
        return (
            None,
            None,
            {
                "candidates": customer_orders,
                "reason": "multiple_customer_orders",
                "computed_summary": portfolio_stats,
            },
        )

    # 4. Fallback: reuse active_order_id, or single customer_id order ONLY when customer owns <=1 order
    lookup_key = state.active_order_id or (customer_id if len(customer_orders) <= 1 else None)
    if lookup_key:
        try:
            order_data = await telemetry_client.lookup_order(lookup_key, customer_id=customer_id)
        except Exception as exc:
            print(f"[ConversationService] Order lookup error: {exc}")
    if not order_data and state.active_order_id:
        order_data = order_tools.get_order_by_id(state.active_order_id, customer_id=customer_id)
    if not order_data and state.facts.get("order_cached"):
        cached = state.facts["order_cached"]
        if is_order_owned_by_customer(cached, customer_id):
            order_data = cached

    if order_data and is_order_owned_by_customer(order_data, customer_id) and order_data.get("order_id"):
        state.active_order_id = order_data["order_id"]
        state.facts["order_id"] = order_data["order_id"]
        state.facts["order_cached"] = order_data
        return order_data, None, None

    return None, None, None
