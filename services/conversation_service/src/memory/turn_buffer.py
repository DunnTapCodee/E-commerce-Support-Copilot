"""Turn buffer for storing recent dialogue history in memory."""
from __future__ import annotations

from typing import List
from contracts.schemas import ConversationTurnItem


class TurnBuffer:
    """Fixed-capacity buffer for raw multi-turn history."""

    def __init__(self, max_turns: int = 5):
        self.max_turns = max_turns

    def get_recent_turns(self, turns: List[ConversationTurnItem]) -> List[ConversationTurnItem]:
        """Return the most recent N turns."""
        return turns[-self.max_turns:] if len(turns) > self.max_turns else list(turns)

    def format_as_context(self, turns: List[ConversationTurnItem]) -> str:
        """Render recent turns into concise dialogue context string."""
        recent = self.get_recent_turns(turns)
        if not recent:
            return ""

        lines = []
        for t in recent:
            lines.append(f"Khách hàng: {t.customer_query}")
            lines.append(f"CSKH / AI: {t.agent_response}")
        return "\n".join(lines)
