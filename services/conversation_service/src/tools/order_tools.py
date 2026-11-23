"""Order Tools for Conversation Service (Dynamic Data Lookup).
Reads data/mock_orders.json to retrieve real-time order states.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent
DEFAULT_ORDERS_PATH = ROOT_DIR / "data" / "mock_orders.json"


class OrderTools:
    """Tool execution for querying local mock orders database."""

    def __init__(self, data_path: Optional[Path] = None):
        self.data_path = data_path or DEFAULT_ORDERS_PATH
        if not self.data_path.exists():
            alt = Path("data/mock_orders.json")
            if alt.exists():
                self.data_path = alt

    def get_all_orders(self) -> List[Dict[str, Any]]:
        """Load all orders from JSON store."""
        if not self.data_path.exists():
            return []
        try:
            with open(self.data_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """Look up order by normalized order ID."""
        if not order_id:
            return None
        target = order_id.strip().upper().lstrip("#")
        orders = self.get_all_orders()
        for o in orders:
            curr_id = str(o.get("order_id", "")).strip().upper().lstrip("#")
            if curr_id == target:
                return o
        return None

    def search_by_product_name(self, product_query: str) -> List[Dict[str, Any]]:
        """Search orders containing items matching the product query."""
        if not product_query:
            return []
        query_words = set(product_query.lower().split())
        matched = []
        for o in self.get_all_orders():
            for item in o.get("items", []):
                item_name = str(item.get("name", "")).lower()
                if any(w in item_name for w in query_words if len(w) > 2):
                    matched.append(o)
                    break
        return matched

    @staticmethod
    def format_order_summary(order: Dict[str, Any]) -> str:
        """Format order into polite Vietnamese status string."""
        oid = order.get("order_id", "N/A")
        status = order.get("order_status") or order.get("status", "Đang xử lý")
        carrier = order.get("carrier") or order.get("shipper_name", "Đơn vị vận chuyển Tiki")
        est = order.get("estimated_delivery", "trong thời gian sớm nhất")
        items = ", ".join(f"{it.get('name')} (x{it.get('quantity', 1)})" for it in order.get("items", []))
        return (
            f"Dạ đơn hàng #{oid} ({items}) hiện đang ở trạng thái: **{status}**.\n"
            f"- Đơn vị vận chuyển: {carrier}\n"
            f"- Dự kiến giao hàng: {est}."
        )

