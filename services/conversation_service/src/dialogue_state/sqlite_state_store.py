"""Persistent SQLite state store for conversation sessions and dialogue turns.
Guarantees long-term persistence across restarts and UI tab navigations.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from contracts.schemas import ConversationTurnItem
from services.conversation_service.src.config import ROOT_DIR
from services.conversation_service.src.dialogue_state.state import ConversationState

DB_PATH = Path(os.getenv("CONVERSATIONS_DB_PATH", str(ROOT_DIR / "copilot_conversations.sqlite3")))


def get_system_now_str() -> str:
    """Returns current system time shifted by +12 hours."""
    return (datetime.now() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")


def get_db_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    """Connect to SQLite database with WAL mode."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def init_conversation_db(db_path: Path = DB_PATH) -> None:
    """Initialize persistent schema for conversation sessions and turns."""
    with get_db_connection(db_path) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_sessions (
            session_id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL,
            title TEXT NOT NULL,
            active_intent TEXT NULL,
            active_order_id TEXT NULL,
            facts_json TEXT NOT NULL DEFAULT '{}',
            context_summary TEXT NULL,
            is_live_chat INTEGER NOT NULL DEFAULT 0,
            copilot_draft TEXT NULL,
            copilot_response_json TEXT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS conversation_turns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            turn_id INTEGER NOT NULL DEFAULT 1,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            is_acknowledgement INTEGER NOT NULL DEFAULT 0,
            intent TEXT NULL,
            confidence REAL NULL,
            facts_json TEXT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
        );
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_customer_id ON conversation_sessions(customer_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON conversation_sessions(updated_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_session_id ON conversation_turns(session_id);")
        conn.commit()


class PersistentStateStore:
    """Persistent SQLite-backed State Store replacing in-memory ephemeral store."""

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        init_conversation_db(self.db_path)

    def get_or_create(self, session_id: str, customer_id: Optional[str] = None) -> ConversationState:
        cust_id = customer_id or "demo-customer"
        with get_db_connection(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM conversation_sessions WHERE session_id = ?;",
                (session_id,),
            ).fetchone()

            if not row:
                now_str = get_system_now_str()
                conn.execute(
                    """
                    INSERT INTO conversation_sessions (
                        session_id, customer_id, title, facts_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?);
                    """,
                    (session_id, cust_id, "Hội thoại mới", "{}", now_str, now_str),
                )
                conn.commit()
                return ConversationState(
                    session_id=session_id,
                    customer_id=cust_id,
                )

            # Load past turns
            turn_rows = conn.execute(
                """
                SELECT turn_id, role, content, intent, confidence, facts_json, is_acknowledgement, created_at
                FROM conversation_turns
                WHERE session_id = ?
                ORDER BY id ASC;
                """,
                (session_id,),
            ).fetchall()

            turns = []
            for t in turn_rows:
                facts_dict = {}
                if t["facts_json"]:
                    try:
                        facts_dict = json.loads(t["facts_json"])
                    except Exception:
                        pass
                turns.append(
                    ConversationTurnItem(
                        turn_id=t["turn_id"],
                        customer_query=t["content"] if t["role"] == "customer" else "",
                        agent_response=t["content"] if t["role"] in ("agent", "acknowledgement") else "",
                        intent=t["intent"],
                        confidence=t["confidence"],
                        facts=facts_dict,
                    )
                )

            facts_data = {}
            if row["facts_json"]:
                try:
                    facts_data = json.loads(row["facts_json"])
                except Exception:
                    pass

            return ConversationState(
                session_id=row["session_id"],
                customer_id=row["customer_id"],
                active_intent=row["active_intent"],
                active_order_id=row["active_order_id"],
                facts=facts_data,
                is_live_chat=bool(row["is_live_chat"]),
                turns=turns,
                context_summary=row["context_summary"],
                last_updated=row["updated_at"],
            )

    def save(
        self,
        state: ConversationState,
        copilot_draft: Optional[str] = None,
        copilot_response_json: Optional[str] = None,
    ) -> None:
        """Persist state and sync latest turns to database."""
        now_str = get_system_now_str()
        with get_db_connection(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO conversation_sessions (
                    session_id, customer_id, title, active_intent, active_order_id,
                    facts_json, context_summary, is_live_chat, copilot_draft,
                    copilot_response_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    active_intent = excluded.active_intent,
                    active_order_id = excluded.active_order_id,
                    facts_json = excluded.facts_json,
                    context_summary = excluded.context_summary,
                    is_live_chat = excluded.is_live_chat,
                    copilot_draft = COALESCE(excluded.copilot_draft, conversation_sessions.copilot_draft),
                    copilot_response_json = COALESCE(excluded.copilot_response_json, conversation_sessions.copilot_response_json),
                    updated_at = excluded.updated_at;
                """,
                (
                    state.session_id,
                    state.customer_id,
                    "Hội thoại",
                    state.active_intent,
                    state.active_order_id,
                    json.dumps(state.facts, ensure_ascii=False),
                    state.context_summary,
                    1 if state.is_live_chat else 0,
                    copilot_draft,
                    copilot_response_json,
                    now_str,
                ),
            )
            conn.commit()

    def add_turn_record(
        self,
        session_id: str,
        role: str,
        content: str,
        is_acknowledgement: bool = False,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        facts: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Append a single chat message turn directly to database."""
        now_str = get_system_now_str()
        with get_db_connection(self.db_path) as conn:
            # Get max turn_id
            cursor = conn.execute(
                "SELECT COALESCE(MAX(turn_id), 0) FROM conversation_turns WHERE session_id = ?;",
                (session_id,),
            )
            next_turn_id = cursor.fetchone()[0] + 1

            conn.execute(
                """
                INSERT INTO conversation_turns (
                    session_id, turn_id, role, content, is_acknowledgement,
                    intent, confidence, facts_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (
                    session_id,
                    next_turn_id,
                    role,
                    content.strip(),
                    1 if is_acknowledgement else 0,
                    intent,
                    confidence,
                    json.dumps(facts, ensure_ascii=False) if facts else None,
                    now_str,
                ),
            )

            # Update session's updated_at
            conn.execute(
                "UPDATE conversation_sessions SET updated_at = ? WHERE session_id = ?;",
                (now_str, session_id),
            )
            conn.commit()
            return next_turn_id

    def list_sessions(self) -> List[str]:
        """Return list of active session IDs."""
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute("SELECT session_id FROM conversation_sessions ORDER BY updated_at DESC;").fetchall()
            return [r["session_id"] for r in rows]

    def list_sessions_by_customer(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all persistent conversation sessions for a customer."""
        with get_db_connection(self.db_path) as conn:
            if customer_id:
                rows = conn.execute(
                    """
                    SELECT s.session_id, s.customer_id, s.title, s.created_at, s.updated_at,
                           s.copilot_draft, COUNT(t.id) as message_count
                    FROM conversation_sessions s
                    LEFT JOIN conversation_turns t ON s.session_id = t.session_id
                    WHERE s.customer_id = ?
                    GROUP BY s.session_id
                    ORDER BY s.updated_at DESC;
                    """,
                    (customer_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT s.session_id, s.customer_id, s.title, s.created_at, s.updated_at,
                           s.copilot_draft, COUNT(t.id) as message_count
                    FROM conversation_sessions s
                    LEFT JOIN conversation_turns t ON s.session_id = t.session_id
                    GROUP BY s.session_id
                    ORDER BY s.updated_at DESC;
                    """
                ).fetchall()

            return [
                {
                    "sessionId": r["session_id"],
                    "customerId": r["customer_id"],
                    "title": r["title"],
                    "createdAt": r["created_at"],
                    "updatedAt": r["updated_at"],
                    "copilotDraft": r["copilot_draft"] or "",
                    "messageCount": r["message_count"],
                }
                for r in rows
            ]

    def get_full_session_details(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session metadata and full list of ordered chat messages."""
        with get_db_connection(self.db_path) as conn:
            sess_row = conn.execute(
                "SELECT * FROM conversation_sessions WHERE session_id = ?;",
                (session_id,),
            ).fetchone()
            if not sess_row:
                return None

            turn_rows = conn.execute(
                """
                SELECT id, turn_id, role, content, is_acknowledgement, created_at, intent
                FROM conversation_turns
                WHERE session_id = ?
                ORDER BY id ASC;
                """,
                (session_id,),
            ).fetchall()

            copilot_resp = None
            if sess_row["copilot_response_json"]:
                try:
                    copilot_resp = json.loads(sess_row["copilot_response_json"])
                except Exception:
                    pass

            messages = [
                {
                    "id": str(t["id"]),
                    "role": t["role"],
                    "content": t["content"],
                    "timestamp": t["created_at"][11:16] if len(t["created_at"]) >= 16 else t["created_at"],
                    "isAcknowledgement": bool(t["is_acknowledgement"]),
                }
                for t in turn_rows
            ]

            facts_data = {}
            if sess_row["facts_json"]:
                try:
                    facts_data = json.loads(sess_row["facts_json"])
                except Exception:
                    pass

            return {
                "sessionId": sess_row["session_id"],
                "customerId": sess_row["customer_id"],
                "title": sess_row["title"],
                "createdAt": sess_row["created_at"],
                "updatedAt": sess_row["updated_at"],
                "copilotDraft": sess_row["copilot_draft"] or "",
                "copilotResponse": copilot_resp,
                "facts": facts_data,
                "messages": messages,
            }

    def update_session_title(self, session_id: str, new_title: str) -> bool:
        """Update display title of a session."""
        with get_db_connection(self.db_path) as conn:
            cursor = conn.execute(
                "UPDATE conversation_sessions SET title = ? WHERE session_id = ?;",
                (new_title.strip(), session_id),
            )
            conn.commit()
            return cursor.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        """Delete session and cascade delete all its turns."""
        with get_db_connection(self.db_path) as conn:
            conn.execute("DELETE FROM conversation_turns WHERE session_id = ?;", (session_id,))
            cursor = conn.execute("DELETE FROM conversation_sessions WHERE session_id = ?;", (session_id,))
            conn.commit()
            return cursor.rowcount > 0
