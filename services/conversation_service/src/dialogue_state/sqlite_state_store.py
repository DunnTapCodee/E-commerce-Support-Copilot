"""Persistent SQLite state store for conversation sessions and dialogue turns.
Guarantees long-term persistence across restarts and UI tab navigations.
"""
from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional
import uuid

from contracts.schemas import ConversationTurnItem, VN_TZ, get_system_now
from services.conversation_service.src.config import ROOT_DIR
from services.conversation_service.src.dialogue_state.state import ConversationState

DB_PATH = Path(os.getenv("CONVERSATIONS_DB_PATH", str(ROOT_DIR / "copilot_conversations.sqlite3")))


def get_system_now_str() -> str:
    """Return current timezone-aware Vietnam timestamp (ISO 8601 +07:00)."""
    return get_system_now()


def _parse_vn_timestamp(ts: Optional[str]) -> datetime:
    """Parse ISO (+07:00/Z) or legacy naive timestamp into VN_TZ datetime for chronological sorting."""
    if not ts or not isinstance(ts, str):
        return datetime.min.replace(tzinfo=VN_TZ)
    cleaned = ts.strip()
    try:
        parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=VN_TZ)
        return parsed.astimezone(VN_TZ)
    except ValueError:
        return datetime.min.replace(tzinfo=VN_TZ)


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

        conn.execute("""
        CREATE TABLE IF NOT EXISTS copilot_draft_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            interaction_id TEXT NOT NULL,
            customer_question TEXT NULL,
            draft_text TEXT NOT NULL,
            response_json TEXT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at DATETIME NULL,
            UNIQUE(session_id, interaction_id),
            FOREIGN KEY (session_id) REFERENCES conversation_sessions(session_id) ON DELETE CASCADE
        );
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_customer_id ON conversation_sessions(customer_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON conversation_sessions(updated_at);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_turns_session_id ON conversation_turns(session_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_draft_queue_session_status ON copilot_draft_queue(session_id, status, id);")
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
        interaction_id: Optional[str] = None,
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

            # Update session's updated_at (and auto-update title on first customer message if default)
            if role == "customer" and next_turn_id == 1:
                clean_txt = content.strip()
                short_title = f"{clean_txt[:28]}..." if len(clean_txt) > 30 else clean_txt
                conn.execute(
                    """
                    UPDATE conversation_sessions
                    SET updated_at = ?,
                        title = CASE WHEN title IN ('Hội thoại mới', 'Hội thoại') THEN ? ELSE title END
                    WHERE session_id = ?;
                    """,
                    (now_str, short_title, session_id),
                )
            elif role == "agent" and not is_acknowledgement:
                # Resolve the targeted interaction (or oldest FIFO pending draft) and advance queue head
                if interaction_id:
                    conn.execute(
                        """
                        UPDATE copilot_draft_queue
                        SET status = 'APPROVED', resolved_at = ?
                        WHERE session_id = ? AND interaction_id = ? AND status = 'PENDING';
                        """,
                        (now_str, session_id, interaction_id),
                    )
                else:
                    conn.execute(
                        """
                        UPDATE copilot_draft_queue
                        SET status = 'APPROVED', resolved_at = ?
                        WHERE id = (
                            SELECT id FROM copilot_draft_queue
                            WHERE session_id = ? AND status = 'PENDING'
                            ORDER BY id ASC
                            LIMIT 1
                        );
                        """,
                        (now_str, session_id),
                    )
                self._sync_session_draft_head_conn(conn, session_id, now_str)
            else:
                conn.execute(
                    "UPDATE conversation_sessions SET updated_at = ? WHERE session_id = ?;",
                    (now_str, session_id),
                )
            conn.commit()
            return next_turn_id

    @staticmethod
    def _sync_session_draft_head_conn(
        conn: sqlite3.Connection, session_id: str, now_str: str
    ) -> None:
        """Keep conversation_sessions.copilot_draft aligned with the oldest PENDING queue item."""
        head = conn.execute(
            """
            SELECT draft_text, response_json
            FROM copilot_draft_queue
            WHERE session_id = ? AND status = 'PENDING'
            ORDER BY id ASC
            LIMIT 1;
            """,
            (session_id,),
        ).fetchone()
        if head:
            conn.execute(
                """
                UPDATE conversation_sessions
                SET copilot_draft = ?, copilot_response_json = ?, updated_at = ?
                WHERE session_id = ?;
                """,
                (head["draft_text"], head["response_json"], now_str, session_id),
            )
        else:
            conn.execute(
                """
                UPDATE conversation_sessions
                SET copilot_draft = NULL, copilot_response_json = NULL, updated_at = ?
                WHERE session_id = ?;
                """,
                (now_str, session_id),
            )

    def set_copilot_draft(
        self,
        session_id: str,
        copilot_draft: str,
        copilot_response_dict: Optional[Dict[str, Any]] = None,
        interaction_id: Optional[str] = None,
        customer_question: Optional[str] = None,
    ) -> None:
        """Enqueue the generated Copilot draft per interaction_id (FIFO) without dropping prior pending drafts."""
        now_str = get_system_now_str()
        resp_payload = dict(copilot_response_dict) if copilot_response_dict else None
        eff_interaction_id = (
            interaction_id
            or (resp_payload.get("interaction_id") if resp_payload else None)
            or f"draft_{uuid.uuid4().hex[:10]}"
        )
        eff_question = customer_question or (resp_payload.get("customer_question") if resp_payload else None)

        with get_db_connection(self.db_path) as conn:
            # Dedup: If a PENDING draft already exists for this session with the exact same customer question,
            # reuse its interaction_id so it updates in-place rather than creating duplicate unapproved drafts
            if eff_question and eff_question.strip():
                existing_row = conn.execute(
                    """
                    SELECT interaction_id FROM copilot_draft_queue
                    WHERE session_id = ? AND status = 'PENDING' AND customer_question IS NOT NULL AND TRIM(customer_question) = TRIM(?)
                    ORDER BY id DESC LIMIT 1;
                    """,
                    (session_id, eff_question.strip()),
                ).fetchone()
                if existing_row and existing_row["interaction_id"]:
                    eff_interaction_id = existing_row["interaction_id"]

            if resp_payload is not None:
                resp_payload.setdefault("interaction_id", eff_interaction_id)
                if eff_question:
                    resp_payload.setdefault("customer_question", eff_question)
            resp_json = json.dumps(resp_payload, ensure_ascii=False) if resp_payload else None

            conn.execute(
                """
                INSERT INTO copilot_draft_queue (
                    session_id, interaction_id, customer_question, draft_text, response_json, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'PENDING', ?)
                ON CONFLICT(session_id, interaction_id) DO UPDATE SET
                    customer_question = COALESCE(excluded.customer_question, copilot_draft_queue.customer_question),
                    draft_text = excluded.draft_text,
                    response_json = excluded.response_json,
                    status = 'PENDING',
                    resolved_at = NULL;
                """,
                (session_id, eff_interaction_id, eff_question, copilot_draft, resp_json, now_str),
            )
            self._sync_session_draft_head_conn(conn, session_id, now_str)
            conn.commit()

    def clear_copilot_draft(
        self,
        session_id: str,
        interaction_id: Optional[str] = None,
        resolution_status: str = "DISMISSED",
    ) -> None:
        """Resolve a specific interaction's draft (or oldest FIFO pending draft) and advance queue head."""
        now_str = get_system_now_str()
        safe_status = resolution_status if resolution_status in {"APPROVED", "DISMISSED"} else "DISMISSED"
        with get_db_connection(self.db_path) as conn:
            if interaction_id:
                conn.execute(
                    """
                    UPDATE copilot_draft_queue
                    SET status = ?, resolved_at = ?
                    WHERE session_id = ? AND interaction_id = ? AND status = 'PENDING';
                    """,
                    (safe_status, now_str, session_id, interaction_id),
                )
            else:
                conn.execute(
                    """
                    UPDATE copilot_draft_queue
                    SET status = ?, resolved_at = ?
                    WHERE id = (
                        SELECT id FROM copilot_draft_queue
                        WHERE session_id = ? AND status = 'PENDING'
                        ORDER BY id ASC
                        LIMIT 1
                    );
                    """,
                    (safe_status, now_str, session_id),
                )
            self._sync_session_draft_head_conn(conn, session_id, now_str)
            conn.commit()

    def list_sessions(self) -> List[str]:
        """Return list of active session IDs ordered chronologically descending."""
        with get_db_connection(self.db_path) as conn:
            rows = conn.execute("SELECT session_id, updated_at FROM conversation_sessions;").fetchall()
            ordered = sorted(rows, key=lambda r: _parse_vn_timestamp(r["updated_at"]), reverse=True)
            return [r["session_id"] for r in ordered]

    def list_sessions_by_customer(self, customer_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all persistent conversation sessions for a customer."""
        with get_db_connection(self.db_path) as conn:
            if customer_id:
                rows = conn.execute(
                    """
                    SELECT s.session_id, s.customer_id, s.title, s.created_at, s.updated_at,
                           s.copilot_draft, COUNT(t.id) as message_count,
                           (SELECT COUNT(*) FROM copilot_draft_queue q
                            WHERE q.session_id = s.session_id AND q.status = 'PENDING') as pending_draft_count
                    FROM conversation_sessions s
                    LEFT JOIN conversation_turns t ON s.session_id = t.session_id
                    WHERE s.customer_id = ?
                    GROUP BY s.session_id;
                    """,
                    (customer_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT s.session_id, s.customer_id, s.title, s.created_at, s.updated_at,
                           s.copilot_draft, COUNT(t.id) as message_count,
                           (SELECT COUNT(*) FROM copilot_draft_queue q
                            WHERE q.session_id = s.session_id AND q.status = 'PENDING') as pending_draft_count
                    FROM conversation_sessions s
                    LEFT JOIN conversation_turns t ON s.session_id = t.session_id
                    GROUP BY s.session_id;
                    """
                ).fetchall()

            ordered_rows = sorted(rows, key=lambda r: _parse_vn_timestamp(r["updated_at"]), reverse=True)
            return [
                {
                    "sessionId": r["session_id"],
                    "customerId": r["customer_id"],
                    "title": r["title"],
                    "createdAt": r["created_at"],
                    "updatedAt": r["updated_at"],
                    "copilotDraft": r["copilot_draft"] or "",
                    "pendingDraftCount": int(r["pending_draft_count"] or 0),
                    "messageCount": r["message_count"],
                }
                for r in ordered_rows
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

            queue_rows = conn.execute(
                """
                SELECT interaction_id, customer_question, draft_text, response_json, created_at
                FROM copilot_draft_queue
                WHERE session_id = ? AND status = 'PENDING'
                ORDER BY id ASC;
                """,
                (session_id,),
            ).fetchall()

            pending_drafts: List[Dict[str, Any]] = []
            for qrow in queue_rows:
                q_resp = None
                if qrow["response_json"]:
                    try:
                        q_resp = json.loads(qrow["response_json"])
                    except Exception:
                        pass
                pending_drafts.append(
                    {
                        "interactionId": qrow["interaction_id"],
                        "customerQuestion": qrow["customer_question"] or "",
                        "copilotDraft": qrow["draft_text"] or "",
                        "copilotResponse": q_resp,
                        "createdAt": qrow["created_at"],
                    }
                )

            copilot_resp = pending_drafts[0]["copilotResponse"] if pending_drafts else None
            if copilot_resp is None and sess_row["copilot_response_json"]:
                try:
                    copilot_resp = json.loads(sess_row["copilot_response_json"])
                except Exception:
                    pass
            head_draft = (
                pending_drafts[0]["copilotDraft"]
                if pending_drafts
                else (sess_row["copilot_draft"] or "")
            )

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
                "copilotDraft": head_draft,
                "copilotResponse": copilot_resp,
                "pendingDrafts": pending_drafts,
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
