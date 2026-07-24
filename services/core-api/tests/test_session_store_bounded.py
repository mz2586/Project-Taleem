"""Session store bound — storage-exhaustion regression (adversarial validation).

The in-memory session repository was unbounded: an authenticated caller could create sessions with
no limit and grow process memory (DoS). It is now a bounded LRU store — this locks that in.
"""

from __future__ import annotations

from taleem_core.contexts.learning.adapters.memory import InMemorySessionRepository
from taleem_core.contexts.learning.domain.session import Session


def _session(sid: str) -> Session:
    return Session(session_id=sid, student_ref="stu")


def test_store_never_exceeds_capacity() -> None:
    repo = InMemorySessionRepository(max_sessions=100)
    for i in range(10_000):
        repo.save(_session(f"s{i}"))
    assert len(repo) == 100  # bounded regardless of how many were created


def test_lru_evicts_oldest_first() -> None:
    repo = InMemorySessionRepository(max_sessions=3)
    for sid in ("a", "b", "c"):
        repo.save(_session(sid))
    # Touch "a" so it becomes most-recently-used; adding "d" should evict "b" (the LRU), not "a".
    assert repo.get("a") is not None
    repo.save(_session("d"))
    assert repo.get("a") is not None
    assert repo.get("b") is None  # evicted
    assert repo.get("c") is not None
    assert repo.get("d") is not None


def test_recent_sessions_are_retained() -> None:
    repo = InMemorySessionRepository(max_sessions=50)
    for i in range(1_000):
        repo.save(_session(f"s{i}"))
    # The most recent 50 survive; older ones are gone.
    assert repo.get("s999") is not None
    assert repo.get("s950") is not None
    assert repo.get("s0") is None
