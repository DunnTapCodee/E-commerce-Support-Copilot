"""Non-blocking background memory update worker."""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional
from services.conversation_service.src.dialogue_state.state import state_store
from services.conversation_service.src.memory.context_summary import ContextSummaryManager


class MemoryWorker:
    """Background task running concurrently to update turn buffers and summaries."""

    @staticmethod
    async def update_memory_task(
        session_id: str,
        customer_query: str,
        agent_response: str,
        intent: Optional[str] = None,
        confidence: Optional[float] = None,
        new_facts: Optional[Dict[str, Any]] = None,
        order_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Asynchronously record turn and refresh summary."""
        # Yield to event loop to avoid delaying immediate response
        await asyncio.sleep(0.01)

        state = state_store.get_or_create(session_id)
        state.add_turn(
            customer_query=customer_query,
            agent_response=agent_response,
            intent=intent,
            confidence=confidence,
            new_facts=new_facts,
        )
        # Update running summary
        state.context_summary = ContextSummaryManager.build_summary(state, order_data)
        state_store.save(state)
