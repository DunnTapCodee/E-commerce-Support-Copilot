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
            handling_time_ms INTEGER NOT NULL DEFAULT 0,
            edit_distance REAL NULL,
            is_rubber_stamping INTEGER NOT NULL DEFAULT 0,
            is_continual_learning INTEGER NOT NULL DEFAULT 0,
            latency_ms INTEGER NOT NULL DEFAULT 0
        );
        """)

        # Safely ensure new columns exist for existing databases
        columns_to_add = [
            ("handling_time_ms", "INTEGER NOT NULL DEFAULT 0"),
            ("edit_distance", "REAL NULL"),
            ("is_rubber_stamping", "INTEGER NOT NULL DEFAULT 0"),
            ("is_continual_learning", "INTEGER NOT NULL DEFAULT 0"),
        ]
        existing_cols = {col[1] for col in conn.execute("PRAGMA table_info(telemetry_logs);").fetchall()}
        for col_name, col_type in columns_to_add:
            if col_name not in existing_cols:
                try:
                    conn.execute(f"ALTER TABLE telemetry_logs ADD COLUMN {col_name} {col_type};")
                except Exception:
                    pass

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

        # 3. Staff & Customer tables for Role-Based Access Control (Customer & Staff)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS staff (
            staff_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            role TEXT NOT NULL DEFAULT 'CS Agent',
            department TEXT NOT NULL DEFAULT 'Customer Support',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            phone TEXT NULL,
            email TEXT NULL,
            assigned_staff_id TEXT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (assigned_staff_id) REFERENCES staff(staff_id)
        );
        """)

        # 4. Dedicated indexes for high-speed sub-millisecond lookups
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_phone ON orders(phone);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_tracking_code ON orders(tracking_code);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(order_status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_customers_assigned_staff_id ON customers(assigned_staff_id);")
        conn.commit()

    # 5. Auto-migrate orders from JSON if table is empty
    if mock_orders_path and mock_orders_path.exists():
        _execute_migration(db_path, mock_orders_path, force=False)

    # 6. Auto-seed staff & customers if empty
    _seed_staff_and_customers(db_path)


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


def _seed_staff_and_customers(db_path: Path) -> None:
    """Seed default Staff and derive Customer profiles from existing orders."""
    default_staff = [
        ("staff-01", "Nguyễn Minh Anh", "minhanh@tiki-copilot.vn", "Senior CS", "Chăm sóc Đơn hàng & Vận chuyển"),
        ("staff-02", "Trần Hoàng Nam", "hoangnam@tiki-copilot.vn", "Policy Admin", "Quản lý Chính sách & Khiếu nại"),
        ("staff-03", "Lê Thảo Vy", "thaovy@tiki-copilot.vn", "CS Agent", "Hỗ trợ Thanh toán & Hoàn tiền"),
    ]
    staff_ids = [s[0] for s in default_staff]

    with get_db_connection(db_path) as conn:
        staff_count = conn.execute("SELECT COUNT(*) FROM staff;").fetchone()[0]
        if staff_count == 0:
            conn.executemany(
                "INSERT OR IGNORE INTO staff (staff_id, name, email, role, department) VALUES (?, ?, ?, ?, ?);",
                default_staff,
            )

        cust_count = conn.execute("SELECT COUNT(*) FROM customers;").fetchone()[0]
        if cust_count == 0:
            # Derive customers from existing orders table so all mock orders map cleanly
            order_rows = conn.execute(
                "SELECT DISTINCT customer_id, customer_name, phone FROM orders WHERE customer_id IS NOT NULL ORDER BY customer_id;"
            ).fetchall()

            customers_to_insert = []
            seen_ids = set()
            for idx, r in enumerate(order_rows):
                cid = r["customer_id"]
                if cid and cid not in seen_ids:
                    seen_ids.add(cid)
                    cname = r["customer_name"] or cid
                    phone = r["phone"] or ""
                    email_slug = cid.lower().replace(" ", "_")
                    email = f"{email_slug}@customer.tiki.vn"
                    assigned_staff = staff_ids[idx % len(staff_ids)]
                    customers_to_insert.append((cid, cname, phone, email, assigned_staff))

            # Ensure core demo customers exist even if orders table is empty
            fallback_customers = [
                ("CUST-1100", "Lê Văn Sơn", "0998.708.581", "son.le@customer.tiki.vn", "staff-01"),
                ("CUST-1002", "Phan Văn An", "0974.716.127", "an.phan@customer.tiki.vn", "staff-02"),
                ("CUST-1001", "Bùi Thị An", "0938.242.854", "an.bui@customer.tiki.vn", "staff-01"),
                ("CUST-1003", "Vũ Thanh Linh", "0912.345.678", "linh.vu@customer.tiki.vn", "staff-03"),
                ("demo-customer", "Bùi Thị An", "0938.242.854", "demo@customer.tiki.vn", "staff-01"),
            ]
            for fc in fallback_customers:
                if fc[0] not in seen_ids:
                    seen_ids.add(fc[0])
                    customers_to_insert.append(fc)

            conn.executemany(
                """
                INSERT OR IGNORE INTO customers (customer_id, name, phone, email, assigned_staff_id)
                VALUES (?, ?, ?, ?, ?);
                """,
                customers_to_insert,
            )

        conn.commit()

