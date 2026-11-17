"""Repository handling CRUD operations for telemetry_logs and high-performance order queries."""
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional

from contracts.schemas import AuditLogCreate, HumanActionUpdate
from services.telemetry_service.src.cache import OrderLRUCache, normalize_phone
from services.telemetry_service.src.database import get_db_connection
from services.telemetry_service.src.metrics import (
    compute_normalized_levenshtein,
    detect_rubber_stamping,
    is_continual_learning_candidate,
)


class TelemetryRepository:
    """Manages persistence of telemetry audit records and cached order queries."""

    def __init__(self, db_path: Path, mock_orders_path: Path, cache_size: int = 256):
        self.db_path = db_path
        self.mock_orders_path = mock_orders_path
        self.cache = OrderLRUCache(max_size=cache_size)

    def insert_audit_log(self, record: AuditLogCreate) -> None:
        """Insert or update initial interaction log."""
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO telemetry_logs
                (interaction_id, customer_query, predicted_intent, intent_confidence,
                 guardrail_action, retrieved_doc_ids, raw_draft_text, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(interaction_id) DO UPDATE SET
                 customer_query=excluded.customer_query,
                 predicted_intent=excluded.predicted_intent,
                 intent_confidence=excluded.intent_confidence,
                 guardrail_action=excluded.guardrail_action,
                 retrieved_doc_ids=excluded.retrieved_doc_ids,
                 raw_draft_text=excluded.raw_draft_text,
                 latency_ms=excluded.latency_ms;
                """,
                (
                    record.interaction_id,
                    record.customer_query,
                    record.predicted_intent,
                    record.intent_confidence,
                    record.guardrail_action,
                    record.retrieved_doc_ids,
                    record.raw_draft_text,
                    record.latency_ms,
                ),
            )
            conn.commit()

    def update_human_action(self, update: HumanActionUpdate) -> bool:
        """Record the support agent's review decision."""
        action = update.action

        # APPROVE và EDIT cần có nội dung cuối cùng để lưu.
        if action in {"APPROVE", "EDIT"}:
            if not update.final_text or not update.final_text.strip():
                raise ValueError(
                    f"final_text không được để trống với action={action}"
                )

        # Không coi bản nháp là tin nhắn đã thực sự gửi cho khách.
        # final_sent_text ở đây lưu nội dung cuối cùng nhân viên xác nhận.
        final_text = (
            update.final_text.strip()
            if update.final_text and update.final_text.strip()
            else None
        )

        with get_db_connection(self.db_path) as conn:
            # Look up initial raw draft text to compute edit metrics
            row = conn.execute(
                "SELECT raw_draft_text FROM telemetry_logs WHERE interaction_id = ?;",
                (update.interaction_id,),
            ).fetchone()
            raw_draft = row["raw_draft_text"] if row else ""

            edit_distance = compute_normalized_levenshtein(raw_draft, final_text or "")
            is_rubber = 1 if detect_rubber_stamping(update.handling_time_ms, raw_draft, action) else 0
            is_cl = 1 if is_continual_learning_candidate(raw_draft, final_text or "", action, edit_distance) else 0

            cursor = conn.execute(
                """
                UPDATE telemetry_logs
                SET human_action = ?,
                    final_sent_text = ?,
                    agent_notes = ?,
                    handling_time_ms = ?,
                    edit_distance = ?,
                    is_rubber_stamping = ?,
                    is_continual_learning = ?,
                    latency_ms = latency_ms + ?
                WHERE interaction_id = ?;
                """,
                (
                    action,
                    final_text,
                    update.agent_notes,
                    update.handling_time_ms,
                    edit_distance,
                    is_rubber,
                    is_cl,
                    update.handling_time_ms,
                    update.interaction_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate audit statistics for dashboards, including Module 4 Safety Metrics."""
        with get_db_connection(self.db_path) as conn:
            total_count = conn.execute("SELECT COUNT(*) FROM telemetry_logs;").fetchone()[0]
            action_counts = conn.execute(
                """
                SELECT human_action, COUNT(*) as count
                FROM telemetry_logs
                WHERE human_action IS NOT NULL
                GROUP BY human_action;
                """
            ).fetchall()
            guardrail_counts = conn.execute(
                """
                SELECT guardrail_action, COUNT(*) as count
                FROM telemetry_logs
                GROUP BY guardrail_action;
                """
            ).fetchall()
            # Calculate safety blocks (financial interceptions or human escalations)
            safety_blocks = conn.execute(
                """
                SELECT COUNT(*) FROM telemetry_logs
                WHERE guardrail_action IN ('DIRECT_REFUND_FORM', 'ESCALATE_HUMAN');
                """
            ).fetchone()[0]
            # Potential false escalations: queries escalated but approved by human agent without edits
            false_escalations = conn.execute(
                """
                SELECT COUNT(*) FROM telemetry_logs
                WHERE guardrail_action = 'ESCALATE_HUMAN' AND human_action = 'APPROVE';
                """
            ).fetchone()[0]

            avg_latency = conn.execute(
                "SELECT AVG(latency_ms) FROM telemetry_logs;"
            ).fetchone()[0] or 0.0

            # MLIP Chapter 19 Telemetry Metrics
            avg_edit_dist = conn.execute(
                "SELECT AVG(edit_distance) FROM telemetry_logs WHERE edit_distance IS NOT NULL;"
            ).fetchone()[0] or 0.0

            rubber_stamping_count = conn.execute(
                "SELECT COUNT(*) FROM telemetry_logs WHERE is_rubber_stamping = 1;"
            ).fetchone()[0] or 0

            cl_count = conn.execute(
                "SELECT COUNT(*) FROM telemetry_logs WHERE is_continual_learning = 1;"
            ).fetchone()[0] or 0

            intent_counts = conn.execute(
                """
                SELECT predicted_intent, COUNT(*) as count
                FROM telemetry_logs
                GROUP BY predicted_intent
                ORDER BY count DESC;
                """
            ).fetchall()

            records = conn.execute(
                "SELECT * FROM telemetry_logs ORDER BY timestamp DESC LIMIT 50;"
            ).fetchall()

        actions_map = {row["human_action"]: row["count"] for row in action_counts}
        guardrail_map = {row["guardrail_action"]: row["count"] for row in guardrail_counts}
        intent_map = {row["predicted_intent"]: row["count"] for row in intent_counts if row["predicted_intent"]}

        safety_block_rate = round((safety_blocks / total_count * 100), 1) if total_count > 0 else 0.0
        false_escalation_rate = round((false_escalations / total_count * 100), 1) if total_count > 0 else 0.0
        rubber_rate = round((rubber_stamping_count / total_count * 100), 1) if total_count > 0 else 0.0

        auto_approved_rate = round((actions_map.get("APPROVE", 0) / total_count), 2) if total_count > 0 else 0.0
        escalation_rate = round((safety_blocks / total_count), 2) if total_count > 0 else 0.0

        return {
            "total_interactions": total_count,
            "total_queries": total_count,
            "actions_breakdown": actions_map,
            "guardrail_breakdown": guardrail_map,
            "guardrail_actions": guardrail_map,
            "intent_distribution": intent_map,
            "auto_approved_rate": auto_approved_rate,
            "escalation_rate": escalation_rate,
            "safety_block_rate": safety_block_rate,
            "false_escalation_rate": false_escalation_rate,
            "rubber_stamping_count": rubber_stamping_count,
            "rubber_stamping_rate": rubber_rate,
            "mean_edit_distance": round(float(avg_edit_dist), 4),
            "continual_learning_pool_count": cl_count,
            "average_latency_ms": round(float(avg_latency), 2),
            "avg_latency_ms": round(float(avg_latency), 2),
            "recent_records": [dict(r) for r in records],
            "cache_stats": self.cache.stats(),
        }

    def get_continual_learning_pool(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch verified, agent-approved interaction pairs for continual learning few-shot prompting."""
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT interaction_id, customer_query, predicted_intent,
                       raw_draft_text, final_sent_text, edit_distance, timestamp
                FROM telemetry_logs
                WHERE is_continual_learning = 1
                ORDER BY timestamp DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]

    # -------------------------------------------------------------------
    # Module 3: High-Performance Indexed SQLite + LRU Cached Order Lookups
    # -------------------------------------------------------------------
    def get_orders_by_phone(self, phone: str) -> List[Dict[str, Any]]:
        """Retrieve ALL orders associated with a phone number, sorted newest first."""
        if not phone:
            return []
        phone_clean = normalize_phone(phone)
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT * FROM orders 
                WHERE phone = ? 
                   OR REPLACE(REPLACE(REPLACE(phone, '.', ''), ' ', ''), '-', '') = ? 
                ORDER BY order_id DESC;
                """,
                (phone.strip(), phone_clean),
            ).fetchall()
        orders = [self._row_to_order_dict(r) for r in rows]
        for o in orders:
            self.cache.put(o)
        return orders

    def get_order(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Look up order from LRU cache first, falling back to indexed SQLite."""
        if not identifier:
            return None

        clean_id = identifier.strip()
        norm_order_id = re.sub(r"\bORD\s*[-_:]\s*", "ORD-", clean_id, flags=re.IGNORECASE)
        if norm_order_id.isdigit() and len(norm_order_id) >= 4:
            norm_order_id = f"ORD-{norm_order_id}"

        # 1. Try In-Memory LRU Cache first (< 0.05ms)
        cached = self.cache.get(clean_id) or self.cache.get(norm_order_id)
        if cached:
            return cached

        # Check if identifier is a phone number with multiple orders
        phone_clean = normalize_phone(clean_id)
        if phone_clean and len(phone_clean) >= 9:
            phone_orders = self.get_orders_by_phone(clean_id)
            if phone_orders:
                latest = phone_orders[0].copy()
                if len(phone_orders) > 1:
                    latest["all_orders_for_phone"] = [
                        {"order_id": o["order_id"], "order_status": o["order_status"], "total_amount": o.get("total_amount")}
                        for o in phone_orders
                    ]
                return latest

        # 2. Fall back to Indexed SQLite Query (< 1.0ms)
        with get_db_connection(self.db_path) as conn:
            # Check order_id
            row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ? COLLATE NOCASE OR order_id = ? COLLATE NOCASE LIMIT 1;",
                (clean_id, norm_order_id),
            ).fetchone()

            # Check phone
            if not row:
                if phone_clean:
                    row = conn.execute(
                        "SELECT * FROM orders WHERE phone = ? OR REPLACE(REPLACE(phone, '.', ''), ' ', '') = ? LIMIT 1;",
                        (clean_id, phone_clean),
                    ).fetchone()

            # Check tracking code
            if not row:
                row = conn.execute(
                    "SELECT * FROM orders WHERE tracking_code = ? COLLATE NOCASE LIMIT 1;",
                    (clean_id.upper(),),
                ).fetchone()

            # Check customer_id (and CUST-XXXX to ORD-XXXX mapping)
            if not row:
                row = conn.execute(
                    "SELECT * FROM orders WHERE customer_id = ? COLLATE NOCASE ORDER BY order_id DESC LIMIT 1;",
                    (clean_id,),
                ).fetchone()

            if not row and clean_id.upper().startswith("CUST-"):
                num_part = clean_id.split("-")[-1]
                row = conn.execute(
                    "SELECT * FROM orders WHERE order_id = ? COLLATE NOCASE OR customer_id = ? COLLATE NOCASE LIMIT 1;",
                    (f"ORD-{num_part}", f"cust-{num_part}"),
                ).fetchone()

        if row:
            order_data = self._row_to_order_dict(row)
            self.cache.put(order_data)
            return order_data

        # Fallback to direct JSON scan if table is unpopulated
        return self._fallback_json_get(clean_id)

    def cancel_order(self, order_id: str, reason: str = "Khách hàng yêu cầu hủy đơn") -> Dict[str, Any]:
        """Cancel an order if eligible, updating SQLite and invalidating LRU Cache."""
        clean_id = order_id.strip()
        order = self.get_order(clean_id)
        if not order:
            return {
                "success": False,
                "order_id": clean_id,
                "message": f"Không tìm thấy đơn hàng {clean_id} trong hệ thống.",
                "updated_status": None,
            }

        real_order_id = order["order_id"]
        current_status = str(order.get("order_status", "")).lower()

        # Check cancellation eligibility
        if not order.get("can_cancel", True):
            return {
                "success": False,
                "order_id": real_order_id,
                "message": f"Đơn hàng {real_order_id} đang ở trạng thái '{order.get('order_status')}' và không thể hủy trực tiếp.",
                "updated_status": order.get("order_status"),
            }

        if current_status in ("cancelled", "delivered", "shipping"):
            return {
                "success": False,
                "order_id": real_order_id,
                "message": f"Đơn hàng {real_order_id} đã ở trạng thái '{order.get('order_status')}', không thể hủy.",
                "updated_status": order.get("order_status"),
            }

        # Update order in SQLite
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                UPDATE orders
                SET order_status = 'Cancelled', can_cancel = 0, updated_at = CURRENT_TIMESTAMP
                WHERE order_id = ?;
                """,
                (real_order_id,),
            )
            conn.commit()

        # Invalidate in cache so fresh data is loaded
        self.cache.invalidate(real_order_id)
        updated_order = self.get_order(real_order_id)

        return {
            "success": True,
            "order_id": real_order_id,
            "message": f"Đã hủy đơn hàng {real_order_id} thành công. Lý do ghi nhận: {reason}.",
            "updated_status": "Cancelled",
            "order": updated_order,
        }

    def get_customer_orders(self, customer_id: str) -> List[Dict[str, Any]]:
        """Retrieve all orders placed by a specific customer."""
        clean_id = customer_id.strip()
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM orders WHERE customer_id = ? COLLATE NOCASE ORDER BY order_id DESC;",
                (clean_id,),
            ).fetchall()

        if rows:
            orders = [self._row_to_order_dict(r) for r in rows]
            for o in orders:
                self.cache.put(o)
            return orders
        return []

    def list_staff(self) -> List[Dict[str, Any]]:
        """Retrieve all support staff members."""
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                "SELECT staff_id, name, email, role, department, created_at FROM staff ORDER BY staff_id ASC;"
            ).fetchall()
            return [dict(r) for r in rows]

    def get_staff(self, staff_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single staff member by ID."""
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT staff_id, name, email, role, department, created_at FROM staff WHERE staff_id = ? COLLATE NOCASE;",
                (staff_id.strip(),),
            ).fetchone()
            return dict(row) if row else None

    def list_customers(self, assigned_staff_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve customers, optionally filtered by assigned_staff_id."""
        with get_db_connection(self.db_path) as conn:
            if assigned_staff_id and assigned_staff_id.strip():
                rows = conn.execute(
                    """
                    SELECT c.customer_id, c.name, c.phone, c.email, c.assigned_staff_id,
                           s.name AS assigned_staff_name, c.created_at
                    FROM customers c
                    LEFT JOIN staff s ON c.assigned_staff_id = s.staff_id
                    WHERE c.assigned_staff_id = ? COLLATE NOCASE
                    ORDER BY c.customer_id ASC;
                    """,
                    (assigned_staff_id.strip(),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT c.customer_id, c.name, c.phone, c.email, c.assigned_staff_id,
                           s.name AS assigned_staff_name, c.created_at
                    FROM customers c
                    LEFT JOIN staff s ON c.assigned_staff_id = s.staff_id
                    ORDER BY c.customer_id ASC;
                    """
                ).fetchall()
            return [dict(r) for r in rows]

    def get_customer(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a single customer profile with assigned staff details."""
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT c.customer_id, c.name, c.phone, c.email, c.assigned_staff_id,
                       s.name AS assigned_staff_name, c.created_at
                FROM customers c
                LEFT JOIN staff s ON c.assigned_staff_id = s.staff_id
                WHERE c.customer_id = ? COLLATE NOCASE;
                """,
                (customer_id.strip(),),
            ).fetchone()
            return dict(row) if row else None

    def get_cache_stats(self) -> Dict[str, Any]:
        """Expose current LRU Cache performance metrics."""
        return self.cache.stats()

    def _row_to_order_dict(self, row: Any) -> Dict[str, Any]:
        """Deserialize database row into dictionary with parsed JSON fields."""
        d = dict(row)
        try:
            d["items"] = json.loads(d.get("items_json", "[]"))
        except Exception:
            d["items"] = []
        try:
            d["shipping_timeline"] = json.loads(d.get("shipping_timeline_json", "[]"))
        except Exception:
            d["shipping_timeline"] = []

        d["can_cancel"] = bool(d.get("can_cancel", 1))
        d.pop("items_json", None)
        d.pop("shipping_timeline_json", None)
        return d

    def _fallback_json_get(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Fallback to JSON file lookup if database is unavailable."""
        if not self.mock_orders_path.exists():
            return None

        with open(self.mock_orders_path, "r", encoding="utf-8") as f:
            orders = json.load(f)

        for o in orders:
            if o.get("order_id", "").lower() == identifier.lower():
                return o
            if o.get("customer_id", "").lower() == identifier.lower():
                return o
            if o.get("phone", "").lower() == identifier.lower():
                return o

        return None
