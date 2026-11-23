"""Dialogue state package with persistent SQLite storage."""
from .state import ConversationState
from .sqlite_state_store import PersistentStateStore, DB_PATH
from .tracker import IntentTracker

persistent_state_store = PersistentStateStore(DB_PATH)
state_store = persistent_state_store

__all__ = ["ConversationState", "state_store", "persistent_state_store", "IntentTracker"]
