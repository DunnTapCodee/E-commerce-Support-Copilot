"""Repository handling CRUD operations for telemetry_logs and mock_orders lookup."""
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from contracts.schemas import AuditLogCreate, HumanActionUpdate
from services.telemetry_service.src.database import get_db_connection


class TelemetryRepository:
    """Manages persistence of telemetry audit records and order queries."""

    def __init__(self, db_path: Path, mock_orders_path: Path):
        self.db_path = db_path
        self.mock_orders_path = mock_orders_path

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
            cursor = conn.execute(
                """
                UPDATE telemetry_logs
                SET human_action = ?,
                    final_sent_text = ?,
                    agent_notes = ?,
                    latency_ms = latency_ms + ?
                WHERE interaction_id = ?;
                """,
                (action, final_text, update.agent_notes, update.handling_time_ms, update.interaction_id,),
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

            records = conn.execute(
                "SELECT * FROM telemetry_logs ORDER BY timestamp DESC LIMIT 50;"
            ).fetchall()

        actions_map = {row["human_action"]: row["count"] for row in action_counts}
        guardrail_map = {row["guardrail_action"]: row["count"] for row in guardrail_counts}

        safety_block_rate = round((safety_blocks / total_count * 100), 1) if total_count > 0 else 100.0
        false_escalation_rate = round((false_escalations / total_count * 100), 1) if total_count > 0 else 0.0

        return {
            "total_interactions": total_count,
            "actions_breakdown": actions_map,
            "guardrail_breakdown": guardrail_map,
            "safety_block_rate": safety_block_rate,
            "false_escalation_rate": false_escalation_rate,
            "average_latency_ms": round(float(avg_latency), 2),
            "recent_records": [dict(r) for r in records],
        }

    def get_order(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Look up order from mock_orders.json by customer_id or order_id."""
        if not self.mock_orders_path.exists():
            return None

        with open(self.mock_orders_path, "r", encoding="utf-8") as f:
            orders = json.load(f)

        # Check exact order_id match
        for o in orders:
            if o.get("order_id", "").lower() == customer_id.lower():
                return o

        # Check customer_id match
        for o in orders:
            if o.get("customer_id", "").lower() == customer_id.lower():
                return o

        return None
