"""Dialogue state management for multi-turn sessions."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from contracts.schemas import ConversationTurnItem


class ConversationState(BaseModel):
    """Rich conversational state tracked across turns."""
    session_id: str
    customer_id: Optional[str] = "demo-customer"
    active_intent: Optional[str] = None
    active_order_id: Optional[str] = None
    facts: Dict[str, Any] = Field(default_factory=dict)
    is_live_chat: bool = False
    turns: List[ConversationTurnItem] = Field(default_factory=list)
    context_summary: Optional[str] = None
    awaiting_slot: Optional[str] = None  # e.g., 'order_id', 'confirmation'
    last_updated: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

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

        if "order_id" in merged_facts:
            self.active_order_id = merged_facts["order_id"]

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
        self.last_updated = datetime.now().strftime("%Y-%m-%d %H:%M:%S")


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


# Global singleton store
state_store = StateStore()
