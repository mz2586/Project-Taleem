"""Durable sync coordinator — Phase 6.2B.

Routes a sync batch by delta type: ``attempt.submitted`` deltas go to a durable **evidence sink**
(the learning ``SyncEvidenceConsumer``, which records ``AssessmentEvidence`` idempotently); every
other delta type (progress / lesson.completed / preference) keeps the existing in-memory
``SyncEngine`` conflict policy (monotonic max / idempotent set / server-order-wins).

The coordinator preserves the existing contract: deterministic ordering by ``(client_seq,
client_event_id)``, per-item ``ItemResult`` (applied/duplicate/ignored/conflict), and a server-
incremented cursor (never a client wall-clock). Idempotency for attempts is durable — the evidence
table is the ledger — so a replay after a server restart is still detected as ``DUPLICATE``.
"""

from __future__ import annotations

from typing import Protocol

from .domain import DeltaType, ItemResult, Status, SyncDelta, SyncEngine, SyncStore


class EvidenceSink(Protocol):
    """Durable handler for attempt deltas (implemented by the learning SyncEvidenceConsumer)."""

    def apply_attempt(self, delta: SyncDelta) -> Status: ...


class DurableSyncCoordinator:
    """Applies a batch, routing attempt deltas to a durable sink and the rest to the SyncEngine."""

    def __init__(self, store: SyncStore, sink: EvidenceSink) -> None:
        self._store = store
        self._engine = SyncEngine(store)
        self._sink = sink

    def apply_batch(self, deltas: list[SyncDelta]) -> tuple[list[ItemResult], int]:
        ordered = sorted(deltas, key=lambda d: (d.client_seq, d.client_event_id))
        results: list[ItemResult] = []
        for d in ordered:
            if d.type is DeltaType.ATTEMPT_SUBMITTED:
                results.append(self._apply_attempt(d))
            else:
                results.append(self._engine.apply(d))
        return results, self._store.server_cursor

    def _apply_attempt(self, d: SyncDelta) -> ItemResult:
        # Fast in-process idempotency (a replay within the same run); the durable check is the
        # evidence table inside the sink, which also catches replays across restarts.
        if self._store.is_seen(d.client_event_id):
            return ItemResult(d.client_event_id, Status.DUPLICATE, self._store.server_cursor)
        status = self._sink.apply_attempt(d)
        self._store.mark_seen(d.client_event_id)
        if status is Status.APPLIED:
            self._store.server_cursor += 1
        return ItemResult(d.client_event_id, status, self._store.server_cursor)
