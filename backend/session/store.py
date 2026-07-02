"""
Conversation session store (in-memory).

Holds the per-session message history so the chat keeps context across turns.
In-memory is fine for the prototype; swap for Redis/DB later behind the same API.
Step 3 (Manager + sections) will also use this to drive slot-filling.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field


@dataclass
class Session:
    session_id: str
    messages: list[dict] = field(default_factory=list)  # {"role": str, "content": str}
    state: dict = field(default_factory=dict)            # reserved for step-3 slot-filling
    updated_at: float = field(default_factory=time.time)


class SessionStore:
    def __init__(self, max_sessions: int = 1000, max_messages: int = 50) -> None:
        self._sessions: dict[str, Session] = {}
        self._max_sessions = max_sessions
        self._max_messages = max_messages

    def get_or_create(self, session_id: str | None) -> Session:
        if not session_id:
            session_id = uuid.uuid4().hex
        if session_id not in self._sessions:
            self._sessions[session_id] = Session(session_id=session_id)
            self._evict()
        return self._sessions[session_id]

    def append(self, session_id: str, role: str, content: str) -> Session:
        session = self.get_or_create(session_id)
        session.messages.append({"role": role, "content": content})
        if len(session.messages) > self._max_messages:
            session.messages[:] = session.messages[-self._max_messages :]
        session.updated_at = time.time()
        return session

    def history(self, session_id: str) -> list[dict]:
        session = self._sessions.get(session_id)
        return list(session.messages) if session else []

    def _evict(self) -> None:
        overflow = len(self._sessions) - self._max_sessions
        if overflow > 0:
            oldest = sorted(self._sessions.values(), key=lambda s: s.updated_at)[:overflow]
            for s in oldest:
                self._sessions.pop(s.session_id, None)


_store = SessionStore()


def get_session_store() -> SessionStore:
    return _store
