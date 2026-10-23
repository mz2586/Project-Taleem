"""Durable sync coordinator — Phase 6.2B.

Routes a sync batch by delta type: ``attempt.submitted`` deltas go to a durable **evidence sink**
(the learning ``SyncEvidenceConsumer``, which records ``AssessmentEvidence`` idempotently); every
other delta type (progress / lesson.completed / preference) keeps the existing in-memory
``SyncEngine`` conflict policy (monotonic max / idempotent set / server-order-wins).

The coordinator preserves the existing contract: deterministic ordering by ``(client_seq,
client_event_id)``, per-item ``ItemResult`` (applied/duplicate/ignored/conflict), and a server-
incremented cursor (never a client wall-clock). Idempotency for attempts is durable — the evidence
table is the ledger — so a replay after a server restart is still detected as ``DUPLICATE``.

Child-safety gate: before anything is applied, every learner the batch touches (each attempt's
``student_ref`` plus the acting learner of a student token) is re-checked against live identity
state through the injected ``LearnerGate``. A refused learner rejects the whole batch with
``SyncRefusedError`` — nothing is applied, so the client can hold and later re-send it intact.
"""

from __future__ import annotations

import contextlib
from typing import Protocol

from .consent_gate import LearnerGate, enforce
from .domain import DeltaType, ItemResult, Status, SyncDelta, SyncEngine, SyncStore


class EvidenceSink(Protocol):
    """Durable handler for attempt deltas (implemented by the learning SyncEvidenceConsumer)."""

    def apply_attempt(self, delta: SyncDelta) -> Status: ...


def learners_touched(deltas: list[SyncDelta], acting_learner: str | None = None) -> set[str]:
    """Every learner whose data this batch would write."""
    refs = {
        str(d.payload.get("student_ref", ""))
        for d in deltas
        if d.type is DeltaType.ATTEMPT_SUBMITTED
    }
    if acting_learner:
        refs.add(acting_learner)
    refs.discard("")
    return refs


class DurableSyncCoordinator:
    """Applies a batch, routing attempt deltas to a durable sink and the rest to the SyncEngine."""

    def __init__(
        self, store: SyncStore, sink: EvidenceSink, gate: LearnerGate | None = None
    ) -> None:
        self._store = store
        self._engine = SyncEngine(store)
        self._sink = sink
        self._gate = gate

    def apply_batch(
        self, deltas: list[SyncDelta], *, acting_learner: str | None = None
    ) -> tuple[list[ItemResult], int]:
        # Gate first, for the whole batch: a refusal must leave no partial writes behind.
        enforce(self._gate, learners_touched(deltas, acting_learner))
        ordered = sorted(deltas, key=lambda d: (d.client_seq, d.client_event_id))
        results: list[ItemResult] = []
        # A sink may scope per-batch work (the learning consumer reads each lesson once per batch).
        # Each delta is still applied — and committed — on its own.
        batch_scope = getattr(self._sink, "batch", None)
        with batch_scope() if callable(batch_scope) else contextlib.nullcontext():
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
        # A CONFLICT recorded nothing (malformed / lesson not published). Remembering its id would
        # make a later re-send answer DUPLICATE — and the client would release work the server
        # never stored. Only outcomes that are final for this id are remembered.
        if status is not Status.CONFLICT:
            self._store.mark_seen(d.client_event_id)
        if status is Status.APPLIED:
            self._store.server_cursor += 1
        return ItemResult(d.client_event_id, status, self._store.server_cursor)
