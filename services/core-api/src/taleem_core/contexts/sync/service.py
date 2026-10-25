"""Durable sync coordinator — Phase 6.2B.

Routes a sync batch by delta type: ``attempt.submitted`` deltas go to a durable **evidence sink**
(the learning ``SyncEvidenceConsumer``, which records ``AssessmentEvidence`` idempotently); every
other delta type (progress / lesson.completed / preference) keeps the existing in-memory
``SyncEngine`` conflict policy (monotonic max / idempotent set / server-order-wins).

The coordinator preserves the existing contract: deterministic ordering by ``(client_seq,
client_event_id)``, per-item ``ItemResult`` (applied/duplicate/ignored/conflict), and a server-
incremented cursor (never a client wall-clock). Idempotency for attempts is durable — the evidence
table is the ledger — so a replay after a server restart is still detected as ``DUPLICATE``.

``homework.submitted`` deltas (a written answer the child sent while offline) go to a durable
**homework sink** — the school context's offline consumer, which applies them through the SAME
``SchoolService`` submit path as the online routes (auto-marking, self-check, the disclosure screen,
cohort filtering, ``SHARING_REQUIRED``). The sink answers with a status, a reason when nothing was
applied, and the learner's submission view. Idempotency is durable (the submission row remembers
the client submission key), so a replay — even after a restart — is a ``DUPLICATE``.

Child-safety gate: before anything is applied, every learner the batch touches (each attempt's and
each homework submission's ``student_ref`` plus the acting learner of a student token) is
re-checked against live identity state through the injected ``LearnerGate``. A refused learner
rejects the whole batch with ``SyncRefusedError`` — nothing is applied, so the client can hold and
later re-send it intact.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Protocol

from .consent_gate import LearnerGate, enforce
from .domain import DeltaType, ItemResult, Status, SyncDelta, SyncEngine, SyncStore


class EvidenceSink(Protocol):
    """Durable handler for attempt deltas (implemented by the learning SyncEvidenceConsumer)."""

    def apply_attempt(self, delta: SyncDelta) -> Status: ...


@dataclass(frozen=True)
class HomeworkOutcome:
    """What the homework sink did with one delta."""

    status: Status
    reason: str | None = None  # a stable code when nothing was applied (always set on CONFLICT)
    result: dict[str, object] | None = None  # the learner's submission view, when there is one


class HomeworkSink(Protocol):
    """Durable handler for ``homework.submitted`` deltas (the school offline consumer).

    ``replay`` is True when this process already answered the same ``clientEventId``: the sink must
    then change nothing and answer ``DUPLICATE`` with the current view."""

    def apply_homework(self, delta: SyncDelta, *, replay: bool) -> HomeworkOutcome: ...


# Delta types whose payload names the learner they write for (each is consent-gated).
LEARNER_DELTAS: frozenset[DeltaType] = frozenset(
    {DeltaType.ATTEMPT_SUBMITTED, DeltaType.HOMEWORK_SUBMITTED}
)


def learners_touched(deltas: list[SyncDelta], acting_learner: str | None = None) -> set[str]:
    """Every learner whose data this batch would write."""
    refs = {str(d.payload.get("student_ref", "")) for d in deltas if d.type in LEARNER_DELTAS}
    if acting_learner:
        refs.add(acting_learner)
    refs.discard("")
    return refs


class DurableSyncCoordinator:
    """Applies a batch, routing attempt deltas to a durable sink and the rest to the SyncEngine."""

    def __init__(
        self,
        store: SyncStore,
        sink: EvidenceSink,
        gate: LearnerGate | None = None,
        homework: HomeworkSink | None = None,
    ) -> None:
        self._store = store
        self._engine = SyncEngine(store)
        self._sink = sink
        self._gate = gate
        self._homework = homework

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
                elif d.type is DeltaType.HOMEWORK_SUBMITTED:
                    results.append(self._apply_homework(d))
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

    def _apply_homework(self, d: SyncDelta) -> ItemResult:
        if self._homework is None:  # not wired: surfaced, never silently dropped
            return ItemResult(
                d.client_event_id,
                Status.CONFLICT,
                self._store.server_cursor,
                reason="HOMEWORK_UNAVAILABLE",
            )
        outcome = self._homework.apply_homework(d, replay=self._store.is_seen(d.client_event_id))
        # As for attempts: a CONFLICT stored nothing, so its id is not remembered — a later re-send
        # (e.g. after a grown-up allows sharing again) is applied, not answered DUPLICATE.
        if outcome.status is not Status.CONFLICT:
            self._store.mark_seen(d.client_event_id)
        if outcome.status is Status.APPLIED:
            self._store.server_cursor += 1
        return ItemResult(
            d.client_event_id,
            outcome.status,
            self._store.server_cursor,
            reason=outcome.reason,
            result=outcome.result,
        )
