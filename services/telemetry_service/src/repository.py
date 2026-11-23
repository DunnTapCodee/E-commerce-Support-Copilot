"""Repository handling CRUD operations for telemetry_logs and high-performance order queries."""
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
import uuid

from contracts.order_actions import evaluate_order_action_eligibility
from contracts.schemas import (
    AuditLogCreate,
    HumanActionUpdate,
    IncidentBroadcastRequest,
    OrderActionDecisionRequest,
    OrderActionProposal,
    get_system_now,
    get_vn_now,
    get_vn_today,
)
from services.telemetry_service.src.cache import OrderLRUCache, normalize_phone
from services.telemetry_service.src.database import get_db_connection
from services.telemetry_service.src.metrics import (
    compute_normalized_levenshtein,
    detect_rubber_stamping,
    is_continual_learning_candidate,
)


def _parse_timestamp_utc(ts: Optional[str], naive_tz: timezone = timezone.utc) -> datetime:
    """Parse ISO (+07:00/Z) or naive legacy SQLite timestamp into UTC datetime for chronological sorting."""
    if not ts or not isinstance(ts, str):
        return datetime.min.replace(tzinfo=timezone.utc)
    cleaned = ts.strip()
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=naive_tz)
        return parsed.astimezone(timezone.utc)
    except ValueError:
        return datetime.min.replace(tzinfo=timezone.utc)


class TelemetryRepository:
    """Manages persistence of telemetry audit records and cached order queries."""

    def __init__(self, db_path: Path, mock_orders_path: Path, cache_size: int = 256):
        self.db_path = db_path
        self.mock_orders_path = mock_orders_path
        self.cache = OrderLRUCache(max_size=cache_size)

    def insert_audit_log(self, record: AuditLogCreate) -> None:
        """Insert or update initial interaction log with explicit +07:00 timestamp."""
        now_ts = get_system_now()
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO telemetry_logs
                (interaction_id, timestamp, customer_query, predicted_intent, intent_confidence,
                 guardrail_action, retrieved_doc_ids, raw_draft_text, latency_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(interaction_id) DO UPDATE SET
                 timestamp=excluded.timestamp,
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
                    now_ts,
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

            raw_records = conn.execute(
                "SELECT * FROM telemetry_logs ORDER BY rowid DESC LIMIT 200;"
            ).fetchall()
            records = sorted(
                (dict(r) for r in raw_records),
                key=lambda r: _parse_timestamp_utc(r.get("timestamp"), naive_tz=timezone.utc),
                reverse=True,
            )[:50]

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
            "recent_records": records,
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
                ORDER BY rowid DESC
                LIMIT ?;
                """,
                (max(limit * 4, 200),),
            ).fetchall()
            sorted_rows = sorted(
                (dict(r) for r in rows),
                key=lambda r: _parse_timestamp_utc(r.get("timestamp"), naive_tz=timezone.utc),
                reverse=True,
            )
            return sorted_rows[:limit]

    # -------------------------------------------------------------------
    # Module 3: High-Performance Indexed SQLite + LRU Cached Order Lookups
    # -------------------------------------------------------------------
    def get_orders_by_phone(
        self, phone: str, customer_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Retrieve ALL orders associated with a phone number, scoped by customer_id if provided."""
        if not phone:
            return []
        from contracts.safety import is_order_owned_by_customer

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
        if customer_id:
            orders = [o for o in orders if is_order_owned_by_customer(o, customer_id)]
        for o in orders:
            self.cache.put(o)
        return orders

    def get_order(
        self, identifier: str, customer_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Look up order from LRU cache first, falling back to indexed SQLite (with optional customer isolation)."""
        if not identifier:
            return None

        from contracts.safety import canonical_customer_ids, is_order_owned_by_customer

        clean_id = identifier.strip()
        norm_order_id = re.sub(r"\bORD\s*[-_:]\s*", "ORD-", clean_id, flags=re.IGNORECASE)
        if norm_order_id.isdigit() and len(norm_order_id) >= 4:
            norm_order_id = f"ORD-{norm_order_id}"

        # 1. Try In-Memory LRU Cache first (< 0.05ms), enforcing ownership when scoped
        cached = self.cache.get(clean_id) or self.cache.get(norm_order_id)
        if cached:
            if customer_id and not is_order_owned_by_customer(cached, customer_id):
                return None

            return cached

        # Check if identifier is a phone number with multiple orders
        phone_clean = normalize_phone(clean_id)
        if phone_clean and len(phone_clean) >= 9:
            phone_orders = self.get_orders_by_phone(clean_id, customer_id=customer_id)
            if phone_orders:
                latest = phone_orders[0].copy()
                if len(phone_orders) > 1:
                    latest["all_orders_for_phone"] = [
                        {"order_id": o["order_id"], "order_status": o["order_status"], "total_amount": o.get("total_amount")}
                        for o in phone_orders
                    ]
                return latest
            if customer_id:
                return None


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

            # Check customer_id via explicit alias group only (never synthesize ORD-XXXX from CUST-XXXX)
            if not row:
                aliases = sorted(canonical_customer_ids(clean_id))
                if aliases:
                    placeholders = ", ".join("?" for _ in aliases)
                    row = conn.execute(
                        f"SELECT * FROM orders WHERE LOWER(customer_id) IN ({placeholders}) ORDER BY order_id DESC LIMIT 1;",
                        tuple(aliases),
                    ).fetchone()

        if row:
            order_data = self._row_to_order_dict(row)
            if customer_id and not is_order_owned_by_customer(order_data, customer_id):
                return None

            self.cache.put(order_data)
            return order_data

        # Fallback to direct JSON scan if table is unpopulated
        return self._fallback_json_get(clean_id, customer_id=customer_id)

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
                SET order_status = 'Cancelled', can_cancel = 0, updated_at = ?
                WHERE order_id = ?;
                """,
                (get_system_now(), real_order_id),
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
        """Retrieve all orders placed by a specific customer (respecting explicit alias group)."""
        from contracts.safety import canonical_customer_ids

        aliases = sorted(canonical_customer_ids(customer_id))
        if not aliases:
            return []
        placeholders = ", ".join("?" for _ in aliases)
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM orders WHERE LOWER(customer_id) IN ({placeholders}) ORDER BY order_id DESC;",
                tuple(aliases),
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

    def _fallback_json_get(
        self, identifier: str, customer_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Fallback to JSON file lookup if database is unavailable."""
        if not self.mock_orders_path.exists():
            return None

        from contracts.safety import canonical_customer_ids, is_order_owned_by_customer

        with open(self.mock_orders_path, "r", encoding="utf-8") as f:
            orders = json.load(f)

        id_aliases = canonical_customer_ids(identifier)
        for o in orders:
            matched = (
                o.get("order_id", "").lower() == identifier.lower()
                or str(o.get("customer_id", "")).strip().lower() in id_aliases
                or o.get("phone", "").lower() == identifier.lower()
            )
            if matched:
                if customer_id and not is_order_owned_by_customer(o, customer_id):
                    return None

                return o

        return None

    # -------------------------------------------------------------------
    # Dot 2 (Task 4): In-Chat Order Action Proposals & HITL Quick Approval
    # -------------------------------------------------------------------
    def propose_order_action(self, proposal: OrderActionProposal) -> Dict[str, Any]:
        """Persist a PENDING order modification proposal without mutating the orders table."""
        now_ts = proposal.created_at or get_system_now()
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO order_action_requests (
                    action_id, session_id, interaction_id, order_id, customer_id,
                    action_type, before_values_json, proposed_values_json,
                    eligible, ineligibility_reason, customer_reason, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'PENDING', ?);
                """,
                (
                    proposal.action_id,
                    proposal.session_id,
                    proposal.interaction_id,
                    proposal.order_id,
                    proposal.customer_id,
                    proposal.action_type,
                    json.dumps(proposal.before_values, ensure_ascii=False),
                    json.dumps(proposal.proposed_values, ensure_ascii=False),
                    1 if proposal.eligible else 0,
                    proposal.ineligibility_reason,
                    proposal.customer_reason,
                    now_ts,
                ),
            )
            conn.commit()
            row = conn.execute(
                "SELECT * FROM order_action_requests WHERE action_id = ?;",
                (proposal.action_id,),
            ).fetchone()
            return self._row_to_action_dict(row) if row else proposal.model_dump()

    def list_order_actions(
        self,
        order_id: Optional[str] = None,
        session_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List stored order action requests filtered by order, session, or status."""
        clauses: List[str] = []
        params: List[Any] = []
        if order_id:
            clauses.append("order_id = ? COLLATE NOCASE")
            params.append(order_id.strip())
        if session_id:
            clauses.append("session_id = ?")
            params.append(session_id.strip())
        if status:
            clauses.append("status = ?")
            params.append(status.strip().upper())
        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT * FROM order_action_requests {where_sql} ORDER BY created_at DESC LIMIT 100;",
                tuple(params),
            ).fetchall()
            return [self._row_to_action_dict(r) for r in rows]

    def decide_order_action(
        self, action_id: str, payload: OrderActionDecisionRequest
    ) -> Optional[Dict[str, Any]]:
        """Execute APPROVED order update atomically or record REJECTED decision with mandatory reason."""
        decision = payload.decision
        reason = (payload.reason or "").strip()
        if decision == "REJECT" and not reason:
            raise ValueError("Từ chối yêu cầu (REJECT) bắt buộc phải nhập lý do.")

        now_ts = get_system_now()
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM order_action_requests WHERE action_id = ?;",
                (action_id,),
            ).fetchone()
            if not row:
                return None

            action_dict = self._row_to_action_dict(row)
            if action_dict["status"] != "PENDING":
                raise ValueError(
                    f"Yêu cầu {action_id} đã được xử lý trước đó ({action_dict['status']})."
                )

            order_id = action_dict["order_id"]
            if decision == "REJECT":
                conn.execute(
                    """
                    UPDATE order_action_requests
                    SET status = 'REJECTED', decision_reason = ?, performed_by = ?, decided_at = ?
                    WHERE action_id = ?;
                    """,
                    (reason, payload.performed_by, now_ts, action_id),
                )
                conn.commit()
                updated_action = self._row_to_action_dict(
                    conn.execute(
                        "SELECT * FROM order_action_requests WHERE action_id = ?;",
                        (action_id,),
                    ).fetchone()
                )
                return {
                    "status": "REJECTED",
                    "action": updated_action,
                    "order": self.get_order(order_id),
                    "reply_message": (
                        f"Dạ Tiki chào anh/chị, rất tiếc yêu cầu cho đơn hàng #{order_id} "
                        f"chưa thể thực hiện được vì lý do: {reason}. Mong anh/chị thông cảm ạ!"
                    ),
                }

            # APPROVE: validate live order state atomically inside SQLite transaction
            order_row = conn.execute(
                "SELECT * FROM orders WHERE order_id = ? COLLATE NOCASE;",
                (order_id,),
            ).fetchone()
            if not order_row:
                raise ValueError(f"Không tìm thấy đơn hàng {order_id} trong cơ sở dữ liệu.")

            live_order = self._row_to_order_dict(order_row)
            eligible, inelig_reason = evaluate_order_action_eligibility(
                action_dict["action_type"], live_order
            )
            if not eligible:
                raise ValueError(inelig_reason or "Trạng thái đơn hiện tại không đủ điều kiện cập nhật.")

            proposed = action_dict["proposed_values"]
            act_type = action_dict["action_type"]
            if act_type == "cancel_order":
                conn.execute(
                    "UPDATE orders SET order_status = 'Cancelled', can_cancel = 0, updated_at = ? WHERE order_id = ?;",
                    (now_ts, live_order["order_id"]),
                )
                reply_msg = f"Dạ đơn hàng #{live_order['order_id']} đã được hủy thành công theo yêu cầu của anh/chị ạ."
            elif act_type == "return_product":
                conn.execute(
                    "UPDATE orders SET order_status = 'Return_Requested', can_cancel = 0, updated_at = ? WHERE order_id = ?;",
                    (now_ts, live_order["order_id"]),
                )
                reply_msg = f"Dạ yêu cầu trả hàng cho đơn #{live_order['order_id']} đã được xác nhận tiếp nhận trên hệ thống ạ."
            elif act_type == "update_address":
                new_addr = str(proposed.get("shipping_address", "")).strip()
                if not new_addr:
                    raise ValueError("Thiếu địa chỉ giao hàng mới để cập nhật.")
                conn.execute(
                    "UPDATE orders SET shipping_address = ?, updated_at = ? WHERE order_id = ?;",
                    (new_addr, now_ts, live_order["order_id"]),
                )
                reply_msg = f"Dạ địa chỉ giao hàng của đơn #{live_order['order_id']} đã được cập nhật thành: {new_addr} ạ."
            elif act_type == "update_receiver":
                new_name = str(proposed.get("customer_name") or live_order.get("customer_name") or "").strip()
                new_phone = str(proposed.get("phone") or live_order.get("phone") or "").strip()
                conn.execute(
                    "UPDATE orders SET customer_name = ?, phone = ?, updated_at = ? WHERE order_id = ?;",
                    (new_name, new_phone, now_ts, live_order["order_id"]),
                )
                reply_msg = f"Dạ thông tin người nhận đơn #{live_order['order_id']} đã được cập nhật ({new_name} - {new_phone}) ạ."
            else:
                raise ValueError(f"Hành động '{act_type}' không hợp lệ.")

            conn.execute(
                """
                UPDATE order_action_requests
                SET status = 'APPROVED', decision_reason = ?, performed_by = ?, decided_at = ?
                WHERE action_id = ?;
                """,
                (reason or "Nhân viên CSKH đã duyệt", payload.performed_by, now_ts, action_id),
            )
            conn.commit()
            updated_action = self._row_to_action_dict(
                conn.execute(
                    "SELECT * FROM order_action_requests WHERE action_id = ?;",
                    (action_id,),
                ).fetchone()
            )

        self.cache.invalidate(order_id)
        refreshed_order = self.get_order(order_id)
        return {
            "status": "APPROVED",
            "action": updated_action,
            "order": refreshed_order,
            "reply_message": reply_msg,
        }

    # -------------------------------------------------------------------
    # Dot 2 (Task 5): Proactive Overdue-Shipping Agent & Incident Clustering
    # -------------------------------------------------------------------
    def scan_overdue_shipping_orders(
        self,
        reference_date: Optional[str] = None,
        min_overdue_days: int = 3,
    ) -> Dict[str, Any]:
        """Scan Shipping orders > min_overdue_days past promised_delivery_date (idempotent via delay_notifications)."""
        ref_str = (reference_date or os.getenv("DELAY_REFERENCE_DATE") or "").strip()
        ref_date = date.fromisoformat(ref_str[:10]) if ref_str else get_vn_today()
        now_ts = get_system_now()

        newly_created: List[Dict[str, Any]] = []
        total_overdue = 0

        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT order_id, customer_id, customer_name, promised_delivery_date
                FROM orders
                WHERE LOWER(order_status) = 'shipping'
                  AND promised_delivery_date IS NOT NULL
                  AND TRIM(promised_delivery_date) != '';
                """
            ).fetchall()

            for r in rows:
                try:
                    promised = date.fromisoformat(str(r["promised_delivery_date"])[:10])
                except ValueError:
                    continue
                days_overdue = (ref_date - promised).days
                if days_overdue <= min_overdue_days:
                    continue
                total_overdue += 1

                oid = r["order_id"]
                exists = conn.execute(
                    "SELECT 1 FROM delay_notifications WHERE order_id = ?;", (oid,)
                ).fetchone()
                if exists:
                    continue

                voucher_code = f"TIKI-DELAY30K-{oid.replace('ORD-', '')}"
                cname = r["customer_name"] or "Quý khách"
                msg = (
                    f"Dạ Tiki thành thật xin lỗi anh/chị {cname} vì đơn hàng #{oid} đang giao chậm "
                    f"{days_overdue} ngày so với ngày dự kiến ({promised.isoformat()}). "
                    f"Tiki xin gửi tặng mã voucher tri ân 30.000 VNĐ ({voucher_code}) để hỗ trợ anh/chị ở đơn tiếp theo ạ!"
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO delay_notifications (
                        order_id, customer_id, customer_name, promised_delivery_date,
                        days_overdue, voucher_code, voucher_amount, message_text, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, 30000, ?, 'PENDING_SEND', ?);
                    """,
                    (oid, r["customer_id"], cname, promised.isoformat(), days_overdue, voucher_code, msg, now_ts),
                )
                newly_created.append(
                    {
                        "order_id": oid,
                        "customer_id": r["customer_id"],
                        "customer_name": cname,
                        "promised_delivery_date": promised.isoformat(),
                        "days_overdue": days_overdue,
                        "voucher_code": voucher_code,
                        "voucher_amount": 30000,
                        "message_text": msg,
                        "status": "PENDING_SEND",
                        "created_at": now_ts,
                    }
                )
            conn.commit()

        return {
            "reference_date": ref_date.isoformat(),
            "min_overdue_days": min_overdue_days,
            "total_overdue_matching": total_overdue,
            "newly_created_count": len(newly_created),
            "newly_created": newly_created,
            "notifications": self.list_delay_notifications(),
        }

    def list_delay_notifications(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """List proactive overdue delay notifications ordered newest first."""
        with get_db_connection(self.db_path) as conn:
            if status:
                rows = conn.execute(
                    "SELECT * FROM delay_notifications WHERE status = ? ORDER BY days_overdue DESC, order_id ASC;",
                    (status.strip().upper(),),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM delay_notifications ORDER BY CASE WHEN status = 'PENDING_SEND' THEN 0 ELSE 1 END, days_overdue DESC, order_id ASC;"
                ).fetchall()
            return [dict(r) for r in rows]

    def dispatch_delay_notifications(
        self, order_ids: Optional[List[str]] = None, performed_by: str = "CS Staff"
    ) -> Dict[str, Any]:
        """Mark PENDING_SEND delay notifications as SENT (Staff bulk release)."""
        now_ts = get_system_now()
        with get_db_connection(self.db_path) as conn:
            if order_ids:
                placeholders = ", ".join("?" for _ in order_ids)
                targets = conn.execute(
                    f"SELECT * FROM delay_notifications WHERE status = 'PENDING_SEND' AND order_id IN ({placeholders});",
                    tuple(order_ids),
                ).fetchall()
                conn.execute(
                    f"UPDATE delay_notifications SET status = 'SENT', sent_at = ? WHERE status = 'PENDING_SEND' AND order_id IN ({placeholders});",
                    (now_ts, *order_ids),
                )
            else:
                targets = conn.execute(
                    "SELECT * FROM delay_notifications WHERE status = 'PENDING_SEND';"
                ).fetchall()
                conn.execute(
                    "UPDATE delay_notifications SET status = 'SENT', sent_at = ? WHERE status = 'PENDING_SEND';",
                    (now_ts,),
                )
            conn.commit()
        return {
            "dispatched_count": len(targets),
            "performed_by": performed_by,
            "sent_at": now_ts,
            "dispatched": [dict(r) for r in targets],
        }

    @staticmethod
    def _classify_incident_topic(query: str) -> str:
        """Group free-text queries into normalized operational incident topics."""
        q = (query or "").lower()
        if any(k in q for k in ("bão", "mưa", "ngập", "lũ", "thời tiết")):
            return "Sự cố thời tiết / thiên tai giao hàng"
        if any(k in q for k in ("trễ", "chậm", "lâu quá", "quá hạn", "chưa thấy giao")):
            return "Chậm trễ vận chuyển hàng loạt"
        if any(k in q for k in ("vỡ", "móp", "rách", "hư hỏng", "thiếu hàng", "sai sản phẩm")):
            return "Hư hỏng / Sai thiếu kiện hàng"
        if any(k in q for k in ("thanh toán", "momo", "zalopay", "vnpay", "trừ tiền", "lỗi thẻ")):
            return "Lỗi cổng thanh toán / đối soát"
        if any(k in q for k in ("voucher", "mã giảm", "freeship")):
            return "Lỗi áp dụng mã giảm giá / voucher"
        return "Yêu cầu hỗ trợ chung"

    def get_incident_clusters(
        self, window_hours: int = 24, min_cluster_size: int = 3
    ) -> Dict[str, Any]:
        """Cluster recent telemetry interactions to surface widespread operational incidents."""
        cutoff_utc = datetime.now(timezone.utc) - timedelta(hours=max(1, window_hours))
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT interaction_id, timestamp, customer_query, predicted_intent
                FROM telemetry_logs
                ORDER BY rowid DESC
                LIMIT 500;
                """
            ).fetchall()
            broadcast_rows = conn.execute(
                "SELECT * FROM incident_broadcasts ORDER BY created_at DESC LIMIT 20;"
            ).fetchall()

        buckets: Dict[tuple, Dict[str, Any]] = {}
        for r in rows:
            ts_utc = _parse_timestamp_utc(r["timestamp"], naive_tz=timezone.utc)
            if ts_utc != datetime.min.replace(tzinfo=timezone.utc) and ts_utc < cutoff_utc:
                continue
            intent = r["predicted_intent"] or "unknown_query"
            topic = self._classify_incident_topic(r["customer_query"] or "")
            key = (intent, topic)
            entry = buckets.get(key)
            if not entry:
                cid = f"INC-{abs(hash(key)) % 100000:05d}"
                buckets[key] = {
                    "cluster_id": cid,
                    "predicted_intent": intent,
                    "issue_topic": topic,
                    "count": 1,
                    "sample_queries": [r["customer_query"]],
                    "latest_timestamp": r["timestamp"],
                }
            else:
                entry["count"] += 1
                if len(entry["sample_queries"]) < 3 and r["customer_query"] not in entry["sample_queries"]:
                    entry["sample_queries"].append(r["customer_query"])

        clusters = []
        for entry in sorted(buckets.values(), key=lambda x: x["count"], reverse=True):
            count = entry["count"]
            is_wide = count >= min_cluster_size
            clusters.append(
                {
                    **entry,
                    "is_widespread": is_wide,
                    "suggested_broadcast": (
                        f"Dạ Tiki xin thông báo hiện đang ghi nhận tình trạng '{entry['issue_topic']}'. "
                        "Đội ngũ vận hành đang khẩn trương xử lý ưu tiên và sẽ cập nhật tiến độ mới nhất đến quý khách ngay ạ!"
                    ),
                }
            )

        return {
            "window_hours": window_hours,
            "min_cluster_size": min_cluster_size,
            "widespread_count": sum(1 for c in clusters if c["is_widespread"]),
            "clusters": clusters,
            "recent_broadcasts": [dict(b) for b in broadcast_rows],
        }

    def record_incident_broadcast(self, req: IncidentBroadcastRequest) -> Dict[str, Any]:
        """Persist staff bulk incident broadcast announcement to audit table."""
        now_ts = get_system_now()
        bid = f"bcast_{uuid.uuid4().hex[:10]}"
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO incident_broadcasts (
                    broadcast_id, cluster_id, issue_topic, message_text,
                    performed_by, session_ids_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    bid,
                    req.cluster_id,
                    req.issue_topic,
                    req.message_text.strip(),
                    req.performed_by,
                    json.dumps(req.session_ids, ensure_ascii=False),
                    now_ts,
                ),
            )
            conn.commit()
        return {
            "status": "broadcast_recorded",
            "broadcast_id": bid,
            "cluster_id": req.cluster_id,
            "created_at": now_ts,
        }

    @staticmethod
    def _row_to_action_dict(row: Any) -> Dict[str, Any]:
        """Deserialize an order_action_requests SQLite row."""
        d = dict(row)
        for jcol, out_col in (
            ("before_values_json", "before_values"),
            ("proposed_values_json", "proposed_values"),
        ):
            try:
                d[out_col] = json.loads(d.get(jcol) or "{}")
            except Exception:
                d[out_col] = {}
            d.pop(jcol, None)
        d["eligible"] = bool(d.get("eligible", 1))
        return d
