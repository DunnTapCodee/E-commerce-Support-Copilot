"""Dialogue state management for multi-turn sessions."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from contracts.schemas import ConversationTurnItem


def get_system_now_str() -> str:
    return (datetime.now() + timedelta(hours=12)).strftime("%Y-%m-%d %H:%M:%S")


class ConversationState(BaseModel):
    """Rich conversational state tracked across turns."""
    session_id: str
    customer_id: Optional[str] = "demo-customer"
    active_intent: Optional[str] = None
    active_order_id: Optional[str] = None
    recent_order_ids: List[str] = Field(default_factory=list)
    facts: Dict[str, Any] = Field(default_factory=dict)
    is_live_chat: bool = False
    turns: List[ConversationTurnItem] = Field(default_factory=list)
    context_summary: Optional[str] = None
    awaiting_slot: Optional[str] = None  # e.g., 'order_id', 'confirmation'
    last_updated: str = Field(default_factory=get_system_now_str)

    def register_order_id(self, order_id: str) -> None:
        """Register an order_id into state, maintaining historical order of referenced orders."""
        cleaned = order_id.strip().upper()
        self.active_order_id = cleaned
        if cleaned not in self.recent_order_ids:
            self.recent_order_ids.append(cleaned)

    def get_alternative_order_id(self) -> Optional[str]:
        """Retrieve previous/alternative order id when customer references 'đơn kia' or 'đơn trước'."""
        if len(self.recent_order_ids) >= 2:
            # Return the one before the active order
            for oid in reversed(self.recent_order_ids):
                if oid != self.active_order_id:
                    return oid
        return None

    def add_turn(
        self,
        customer_query: str,
        agent_response: str,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        new_facts: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append turn to history and keep facts fresh."""
        turn_num = len(self.turns) + 1
        merged_facts = dict(self.facts)
        if new_facts:
            merged_facts.update(new_facts)
            self.facts = merged_facts

        if "order_id" in merged_facts and merged_facts["order_id"]:
            self.register_order_id(merged_facts["order_id"])

        self.turns.append(
            ConversationTurnItem(
                turn_id=turn_num,
                customer_query=customer_query,
                agent_response=agent_response,
                intent=intent or self.active_intent,
                confidence=confidence,
                facts=merged_facts,
            )
        )
        self.last_updated = get_system_now_str()


class StateStore:
    """In-memory thread-safe state repository for active sessions."""

    def __init__(self):
        self._sessions: Dict[str, ConversationState] = {}

    def get_or_create(self, session_id: str, customer_id: Optional[str] = None) -> ConversationState:
        if session_id not in self._sessions:
            self._sessions[session_id] = ConversationState(
                session_id=session_id,
                customer_id=customer_id or "demo-customer",
            )
        elif customer_id and self._sessions[session_id].customer_id != customer_id:
            self._sessions[session_id].customer_id = customer_id
        return self._sessions[session_id]

    def save(self, state: ConversationState) -> None:
        self._sessions[state.session_id] = state

    def list_sessions(self) -> List[str]:
        return list(self._sessions.keys())


# Global singleton store backed by persistent SQLite database
from services.conversation_service.src.dialogue_state.sqlite_state_store import PersistentStateStore, DB_PATH
state_store = PersistentStateStore(DB_PATH)
