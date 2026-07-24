"""SyncStore bound — storage-exhaustion regression (adversarial validation).

The process-global SyncStore kept an unbounded ``_seen`` idempotency cache and ``_entities`` map, so
an authenticated caller streaming unique clientEventIds / entity keys could grow memory without
limit (DoS). Both are now bounded LRU structures. Eviction is safe: attempt idempotency has a
durable evidence-table backstop, and the progress/preference merge policies are idempotent.
"""

from __future__ import annotations

from taleem_core.contexts.sync import domain as sync_domain
from taleem_core.contexts.sync.domain import DeltaType, SyncDelta, SyncEngine, SyncStore


def _progress(eid: str, key: str, block: int) -> SyncDelta:
    return SyncDelta(eid, DeltaType.PROGRESS, key, {"block": block}, 0)


def test_seen_cache_is_bounded(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(sync_domain, "_MAX_SEEN", 100)
    monkeypatch.setattr(sync_domain, "_MAX_ENTITIES", 100)
    store = SyncStore()
    engine = SyncEngine(store)
    for i in range(5_000):
        engine.apply(_progress(f"e{i}", f"k{i}", 1))
    assert len(store._seen) <= 100
    assert len(store._entities) <= 100


def test_replay_still_idempotent_within_cache_window() -> None:
    store = SyncStore()
    engine = SyncEngine(store)
    d = _progress("e1", "k1", 3)
    assert engine.apply(d).status.value == "applied"
    assert engine.apply(d).status.value == "duplicate"  # replay detected while still cached


def test_is_seen_mark_seen_roundtrip() -> None:
    store = SyncStore()
    assert store.is_seen("x") is False
    store.mark_seen("x")
    assert store.is_seen("x") is True
