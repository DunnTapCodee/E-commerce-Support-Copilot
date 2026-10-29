"""Compact running context summary generator."""
from __future__ import annotations

from typing import Any, Dict, Optional
from services.conversation_service.src.dialogue_state.state import ConversationState


class ContextSummaryManager:
    """Creates concise, deterministic summary from active dialogue facts and order data."""

    @staticmethod
    def build_summary(state: ConversationState, order_data: Optional[Dict[str, Any]] = None) -> str:
        """Produce a clean one-line or two-line running context summary."""
        parts = []

        if state.customer_id:
            parts.append(f"Khách hàng: {state.customer_id}")

        active_order = state.active_order_id or (order_data.get("order_id") if order_data else None)
        if active_order:
            order_info = f"Đơn hàng: {active_order}"
            if order_data:
                status = order_data.get("order_status")
                pay_status = order_data.get("payment_status")
                total = order_data.get("total_amount")
                details = []
                if status:
                    details.append(f"Trạng thái: {status}")
                if pay_status:
                    details.append(f"Thanh toán: {pay_status}")
                if total:
                    details.append(f"Tổng: {total:,}đ")
                if details:
                    order_info += f" ({', '.join(details)})"
            parts.append(order_info)

        if state.active_intent:
            parts.append(f"Ý định chính: {state.active_intent}")

        if state.is_live_chat:
            parts.append("Chế độ: Đã chuyển Live Chat")

        return " | ".join(parts) if parts else "Chưa có thông tin ngữ cảnh."
