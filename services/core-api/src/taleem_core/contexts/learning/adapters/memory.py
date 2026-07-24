"""In-memory adapters (real, not mocks) — session storage for the vertical slice.

Sessions are transient saga state; an in-memory repository is a real adapter for them (the same
pattern Curriculum Studio uses for its in-memory repository). The durable learning data
(knowledge/evidence/events) is persisted via the SQLAlchemy adapter, not here.

The store is **bounded** with LRU eviction: sessions are short-lived orchestration state, so an
unbounded dict would let an authenticated caller (or just a long-running pilot) grow process memory
without limit — a storage-exhaustion DoS. Evicting the least-recently-used session only drops stale
transient state; the durable learning record for that session was already persisted separately.
"""

from __future__ import annotations

from collections import OrderedDict

from ..domain.session import Session

# Generous ceiling for a pilot: far above the working set of active sessions, low enough that a
# flood of session creations can never exhaust memory. Oldest-touched sessions evict first.
DEFAULT_MAX_SESSIONS = 10_000


class InMemorySessionRepository:
    """Implements the SessionRepository port with a bounded LRU store."""

    def __init__(self, max_sessions: int = DEFAULT_MAX_SESSIONS) -> None:
        self._max = max(1, max_sessions)
        self._store: OrderedDict[str, Session] = OrderedDict()

    def get(self, session_id: str) -> Session | None:
        session = self._store.get(session_id)
        if session is not None:
            self._store.move_to_end(session_id)  # mark most-recently-used
        return session

    def save(self, session: Session) -> None:
        self._store[session.session_id] = session
        self._store.move_to_end(session.session_id)
        while len(self._store) > self._max:
            self._store.popitem(last=False)  # evict least-recently-used

    def __len__(self) -> int:
        return len(self._store)
