"""Offline sync domain (pure, framework-free).

Conflict policy (docs/33 §6, remediated per audit AR-H-28):
  - Ordering uses a SERVER-incremented version counter + client Lamport seq — never client wall-clock.
  - progress: monotonic max (never regress a completed block).
  - lesson completion: idempotent set (once completed, stays completed).
  - assessment attempt: append-only, merge by UNION (no attempt is ever overwritten/lost).
  - preference: server version wins (server-receive order as tiebreaker).
Idempotency: replaying a delta with a seen clientEventId is a no-op → replaying a queue twice
yields identical server state (04-NFR OFFL-02).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class DeltaType(str, Enum):
    PROGRESS = "progress.updated"
    LESSON_COMPLETED = "lesson.completed"
    ATTEMPT_SUBMITTED = "attempt.submitted"
    PREFERENCE = "preference.set"


class Status(str, Enum):
    APPLIED = "applied"
    DUPLICATE = "duplicate"
    IGNORED = "ignored"  # e.g. a stale progress value that would regress — safely dropped
    CONFLICT = "conflict"


@dataclass(frozen=True)
class SyncDelta:
    client_event_id: str  # idempotency key (UUIDv7 from the device)
    type: DeltaType
    entity_key: str  # e.g. "student:S1|lesson:L1"
    payload: dict[str, object]
    client_seq: int = 0  # Lamport seq for intra-batch ordering (NOT wall-clock)


@dataclass(frozen=True)
class ItemResult:
    client_event_id: str
    status: Status
    server_version: int


@dataclass
class _EntityState:
    version: int = 0
    progress_block: int = -1
    completed: bool = False
    attempts: set[str] = field(default_factory=set)
    preference: object | None = None


@dataclass
class SyncStore:
    """In-memory, synthetic store. No live child data. Not persistent."""

    server_cursor: int = 0
    _seen: set[str] = field(default_factory=set)
    _entities: dict[str, _EntityState] = field(default_factory=dict)

    def _entity(self, key: str) -> _EntityState:
        return self._entities.setdefault(key, _EntityState())

    def snapshot(self, key: str) -> _EntityState:
        return self._entity(key)


class SyncEngine:
    """Deterministic batch apply. Pure logic; the store is injected."""

    def __init__(self, store: SyncStore) -> None:
        self._store = store

    def apply_batch(self, deltas: list[SyncDelta]) -> tuple[list[ItemResult], int]:
        # Intra-batch determinism: order by client Lamport seq then event id (stable, clock-free).
        ordered = sorted(deltas, key=lambda d: (d.client_seq, d.client_event_id))
        results = [self._apply_one(d) for d in ordered]
        return results, self._store.server_cursor

    def _apply_one(self, d: SyncDelta) -> ItemResult:
        if d.client_event_id in self._store._seen:  # idempotency — the heart of safe replay
            ent = self._store._entity(d.entity_key)
            return ItemResult(d.client_event_id, Status.DUPLICATE, ent.version)

        ent = self._store._entity(d.entity_key)
        status = self._merge(d, ent)

        # Mark seen regardless of applied/ignored so a replay is always a no-op.
        self._store._seen.add(d.client_event_id)
        if status is Status.APPLIED:
            self._store.server_cursor += 1
            ent.version = self._store.server_cursor
        return ItemResult(d.client_event_id, status, ent.version)

    def _merge(self, d: SyncDelta, ent: _EntityState) -> Status:
        if d.type is DeltaType.PROGRESS:
            block = int(d.payload.get("block", -1))  # type: ignore[arg-type]
            if block <= ent.progress_block:
                return Status.IGNORED  # never regress; stale progress is safely dropped
            ent.progress_block = block
            return Status.APPLIED

        if d.type is DeltaType.LESSON_COMPLETED:
            if ent.completed:
                return Status.IGNORED  # idempotent set
            ent.completed = True
            return Status.APPLIED

        if d.type is DeltaType.ATTEMPT_SUBMITTED:
            attempt_id = str(d.payload.get("attempt_id", d.client_event_id))
            if attempt_id in ent.attempts:
                return Status.DUPLICATE
            ent.attempts.add(attempt_id)  # append-only union — nothing overwritten
            return Status.APPLIED

        if d.type is DeltaType.PREFERENCE:
            ent.preference = d.payload.get("value")  # server order wins (no client clock)
            return Status.APPLIED

        return Status.CONFLICT  # unknown type — surfaced, never silently dropped
