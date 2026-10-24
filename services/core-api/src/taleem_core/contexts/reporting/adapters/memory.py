"""In-memory reporting store + unit of work (unit tests of the service without a database).

Behaves like the SQL adapter: writes become visible only on ``commit``, a second original card for
one learner/class/period or a second successor of one card is a ``ConcurrencyConflictError`` (the
SQL unique indexes), and the acknowledgement is set at most once.
"""

from __future__ import annotations

import dataclasses
from types import TracebackType
from typing import Any

from ....platform.concurrency import ConcurrencyConflictError
from ....platform.ids import uuid7
from ..domain.report_card import ReportCard, ReportingAuditEvent


class InMemoryReportingStore:
    def __init__(self) -> None:
        self.cards: dict[str, ReportCard] = {}
        self.audit: list[ReportingAuditEvent] = []
        self.outbox: list[dict[str, Any]] = []


class _Cards:
    def __init__(self, store: InMemoryReportingStore) -> None:
        self._store = store
        self.pending: list[ReportCard] = []
        self.acks: dict[str, tuple[str, float]] = {}

    def _all(self) -> list[ReportCard]:
        return list(self._store.cards.values())

    def add(self, card: ReportCard) -> None:
        self.pending.append(card)

    def get(self, card_id: str) -> ReportCard | None:
        return self._store.cards.get(card_id)

    def for_student(self, student_ref: str) -> list[ReportCard]:
        return [c for c in self._all() if c.student_ref == student_ref]

    def for_class(self, organization_id: str, class_id: str) -> list[ReportCard]:
        return [
            c for c in self._all() if (c.organization_id, c.class_id) == (organization_id, class_id)
        ]

    def for_slot(
        self, student_ref: str, class_id: str, period_start: int, period_end: int
    ) -> list[ReportCard]:
        return [
            c
            for c in self._all()
            if (c.student_ref, c.class_id, c.period_start, c.period_end)
            == (student_ref, class_id, period_start, period_end)
        ]

    def successors(self, card_ids: list[str]) -> dict[str, str]:
        wanted = set(card_ids)
        return {
            c.supersedes: c.card_id for c in self._all() if c.supersedes in wanted if c.supersedes
        }

    def acknowledge(self, card_id: str, guardian_ref: str, at: float) -> bool:
        card = self._store.cards.get(card_id)
        if card is None or card.acknowledged_at is not None or card_id in self.acks:
            return False
        self.acks[card_id] = (guardian_ref, at)
        return True


class _Audit:
    def __init__(self) -> None:
        self.pending: list[ReportingAuditEvent] = []

    def add(self, event: ReportingAuditEvent) -> None:
        self.pending.append(event)


class _Outbox:
    def __init__(self) -> None:
        self.pending: list[dict[str, Any]] = []

    def add(
        self, *, event_type: str, aggregate_id: str, student_ref: str, payload: dict[str, Any]
    ) -> None:
        self.pending.append(
            {
                "id": f"rpo_{uuid7()}",
                "event_type": event_type,
                "aggregate_id": aggregate_id,
                "student_ref": student_ref,
                "payload": dict(payload),
            }
        )


class InMemoryReportingUnitOfWork:
    def __init__(self, store: InMemoryReportingStore) -> None:
        self._store = store
        self.cards = _Cards(store)
        self.audit = _Audit()
        self.outbox = _Outbox()

    def __enter__(self) -> InMemoryReportingUnitOfWork:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.cards.pending.clear()
        self.cards.acks.clear()
        self.audit.pending.clear()
        self.outbox.pending.clear()

    def commit(self) -> None:
        cards = dict(self._store.cards)
        for card in self.cards.pending:
            existing = list(cards.values())
            if card.card_id in cards:
                raise ConcurrencyConflictError("duplicate card id")
            if card.supersedes and any(c.supersedes == card.supersedes for c in existing):
                raise ConcurrencyConflictError("that card already has a successor")
            if card.supersedes is None and any(
                c.supersedes is None
                and (c.student_ref, c.class_id, c.period_start, c.period_end)
                == (card.student_ref, card.class_id, card.period_start, card.period_end)
                for c in existing
            ):
                raise ConcurrencyConflictError("a card for this learner and period exists")
            cards[card.card_id] = card
        for card_id, (guardian_ref, at) in self.cards.acks.items():
            cards[card_id] = dataclasses.replace(
                cards[card_id], acknowledged_at=at, acknowledged_by=guardian_ref
            )
        self._store.cards = cards
        self._store.audit.extend(self.audit.pending)
        self._store.outbox.extend(self.outbox.pending)
        self.cards.pending.clear()
        self.cards.acks.clear()
        self.audit.pending.clear()
        self.outbox.pending.clear()
