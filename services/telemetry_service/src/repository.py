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
        """Update CS agent decision on a specific interaction."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                """
                UPDATE telemetry_logs
                SET human_action=?, final_sent_text=?, agent_notes=?, latency_ms=?
                WHERE interaction_id=?;
                """,
                (
                    update.action,
                    update.final_text,
                    update.agent_notes,
                    update.handling_time_ms,
                    update.interaction_id,
                ),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_stats(self) -> Dict[str, Any]:
        """Aggregate audit statistics for dashboards."""
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
            avg_latency = conn.execute(
                "SELECT AVG(latency_ms) FROM telemetry_logs;"
            ).fetchone()[0] or 0.0

            records = conn.execute(
                "SELECT * FROM telemetry_logs ORDER BY timestamp DESC LIMIT 50;"
            ).fetchall()

        actions_map = {row["human_action"]: row["count"] for row in action_counts}
        return {
            "total_interactions": total_count,
            "actions_breakdown": actions_map,
            "average_latency_ms": round(float(avg_latency), 2),
            "recent_records": [dict(r) for r in records],
        }

    def get_order(self, customer_id: str) -> Optional[Dict[str, Any]]:
        """Look up order from mock_orders.json for customer_id."""
        if not self.mock_orders_path.exists():
            return None

        with open(self.mock_orders_path, "r", encoding="utf-8") as f:
            orders = json.load(f)

        for o in orders:
            if o.get("customer_id") == customer_id:
                return o

        # Default fallback sample if customer not found directly
        if orders:
            sample = orders[0].copy()
            sample["customer_id"] = customer_id
            return sample

        return None
