"""SQLite connection, schema initialization, and order migration with indexes."""
import json
from pathlib import Path
import sqlite3
from typing import Optional


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """Connect to SQLite database with WAL journal mode enabled for high concurrency."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db(db_path: Path, mock_orders_path: Optional[Path] = None) -> None:
    """Initialize table schemas for telemetry_logs and orders with indexes."""
    with get_db_connection(db_path) as conn:
        # 1. Telemetry logs table
        conn.execute("""
        CREATE TABLE IF NOT EXISTS telemetry_logs (
            interaction_id TEXT PRIMARY KEY,
            timestamp DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            customer_query TEXT NOT NULL,
            predicted_intent TEXT NOT NULL,
            intent_confidence REAL NOT NULL,
            guardrail_action TEXT NOT NULL,
            retrieved_doc_ids TEXT NOT NULL,
            raw_draft_text TEXT NOT NULL,
            human_action TEXT NULL,
            final_sent_text TEXT NULL,
            agent_notes TEXT NULL,
            latency_ms INTEGER NOT NULL DEFAULT 0
        );
        """)

        # 2. Orders table for Module 3 Database Migration
        conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            order_status TEXT NOT NULL,
            payment_method TEXT NOT NULL,
            payment_status TEXT NOT NULL,
            total_amount INTEGER NOT NULL,
            carrier TEXT NULL,
            tracking_code TEXT NULL,
            estimated_delivery TEXT NULL,
            can_cancel INTEGER NOT NULL DEFAULT 1,
            items_json TEXT NOT NULL,
            shipping_timeline_json TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 3. Dedicated indexes for high-speed sub-millisecond lookups
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_tracking_code ON orders(tracking_code);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);")
        conn.commit()

    # 4. Auto-migrate orders from JSON if table is empty
    if mock_orders_path and mock_orders_path.exists():
        _execute_migration(db_path, mock_orders_path, force=False)


def _execute_migration(db_path: Path, mock_orders_path: Path, force: bool = False) -> int:
    """Internal migration execution helper."""
    with get_db_connection(db_path) as conn:
        cursor = conn.execute("SELECT COUNT(*) FROM orders;")
        existing_count = cursor.fetchone()[0]

        if existing_count > 0 and not force:
            return existing_count

        with open(mock_orders_path, "r", encoding="utf-8") as f:
            orders_data = json.load(f)

        if force:
            conn.execute("DELETE FROM orders;")

        for o in orders_data:
            conn.execute(
                """
                INSERT OR REPLACE INTO orders (
                    order_id, customer_id, customer_name, phone, order_status,
                    payment_method, payment_status, total_amount, carrier,
                    tracking_code, estimated_delivery, can_cancel,
                    items_json, shipping_timeline_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    o.get("order_id"),
                    o.get("customer_id"),
                    o.get("customer_name"),
                    o.get("phone"),
                    o.get("order_status"),
                    o.get("payment_method"),
                    o.get("payment_status"),
                    int(o.get("total_amount", 0)),
                    o.get("carrier"),
                    o.get("tracking_code"),
                    o.get("estimated_delivery"),
                    1 if o.get("can_cancel", True) else 0,
                    json.dumps(o.get("items", []), ensure_ascii=False),
                    json.dumps(o.get("shipping_timeline", []), ensure_ascii=False),
                ),
            )
        conn.commit()
        cursor = conn.execute("SELECT COUNT(*) FROM orders;")
        return cursor.fetchone()[0]


def migrate_mock_orders(db_path: Path, mock_orders_path: Path, force: bool = False) -> int:
    """Public helper ensuring schema exists and migrating orders."""
    if not mock_orders_path.exists():
        return 0
    init_db(db_path)
    return _execute_migration(db_path, mock_orders_path, force=force)
