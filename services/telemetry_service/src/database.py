"""SQLite connection and schema initialization with WAL journal mode."""
import sqlite3
from pathlib import Path


def get_db_connection(db_path: Path) -> sqlite3.Connection:
    """Connect to SQLite database with WAL journal mode enabled for high concurrency."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_db(db_path: Path) -> None:
    """Initialize table schemas for telemetry_logs and mock_orders."""
    with get_db_connection(db_path) as conn:
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
        conn.commit()
