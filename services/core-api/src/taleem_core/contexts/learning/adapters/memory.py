"""In-memory adapters (real, not mocks) — session storage for the vertical slice.

Sessions are transient saga state; an in-memory repository is a real adapter for them (the same
pattern Curriculum Studio uses for its in-memory repository). The durable learning data
(knowledge/evidence/events) is persisted via the SQLAlchemy adapter, not here.
"""

from __future__ import annotations

from ..domain.session import Session


class InMemorySessionRepository:
    """Implements the SessionRepository port."""

    def __init__(self) -> None:
        self._store: dict[str, Session] = {}

    def get(self, session_id: str) -> Session | None:
        return self._store.get(session_id)

    def save(self, session: Session) -> None:
        self._store[session.session_id] = session
