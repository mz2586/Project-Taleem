"""Reporting store: a learner's issued report cards, their audit, and their outbox events.

Three reporting tables name a learner, and only by the pseudonymous ``student_ref``:

- ``reporting.report_card`` — the issued cards (C2 learning records, REPORT_CARD_CONTRACT §4).
  Exported to the guardian with the stored body, its ``content_hash`` and whether it still
  verifies, and erased with the learner. For retention they are ``learning_records``, dated by
  ``issued_at`` (purge stays disabled until M-Gov sets the period).
- ``reporting.report_card_audit`` — who issued or acknowledged which card (``subject_ref`` is the
  learner). Erased with the learner: an audit row that keeps the ref would keep the learner
  identifiable after erasure.
- ``reporting.report_card_outbox`` — ``ReportCardIssued`` events (refs only). Erased too.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ...reporting.adapters.persistence.models import (
    ReportCardAuditRow,
    ReportCardOutboxRow,
    ReportCardRow,
)
from ..domain.policy import RetainedSet
from ._rows import affected, row_dict


def _card(row: ReportCardRow) -> dict[str, Any]:
    out = row_dict(row, exclude=("body",))
    try:
        out["body"] = json.loads(row.body)
    except ValueError:
        out["body"] = row.body
    out["hash_verified"] = hashlib.sha256(row.body.encode()).hexdigest() == row.content_hash
    return out


class ReportingLearnerData:
    name = "reporting"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def covers(self) -> tuple[str, ...]:
        return (
            "reporting.report_card",
            "reporting.report_card_audit",
            "reporting.report_card_outbox",
        )

    def export(self, student_ref: str) -> dict[str, Any]:
        with self._sf() as s:
            cards = s.scalars(
                select(ReportCardRow)
                .where(ReportCardRow.student_ref == student_ref)
                .order_by(ReportCardRow.issued_at, ReportCardRow.card_id)
            ).all()
            audit = s.scalars(
                select(ReportCardAuditRow)
                .where(ReportCardAuditRow.subject_ref == student_ref)
                .order_by(ReportCardAuditRow.at)
            ).all()
            events = s.scalars(
                select(ReportCardOutboxRow)
                .where(ReportCardOutboxRow.student_ref == student_ref)
                .order_by(ReportCardOutboxRow.occurred_at)
            ).all()
            return {
                "report_cards": [_card(r) for r in cards],
                "report_card_audit": [row_dict(r) for r in audit],
                "report_card_events": [row_dict(r) for r in events],
                "withheld": [],
            }

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        with self._sf() as s, s.begin():
            events = s.execute(
                delete(ReportCardOutboxRow).where(ReportCardOutboxRow.student_ref == student_ref)
            )
            audit = s.execute(
                delete(ReportCardAuditRow).where(ReportCardAuditRow.subject_ref == student_ref)
            )
            # Every card of a supersede chain belongs to the same learner, so one statement
            # removes the whole chain (the self-reference is checked at the end of the statement).
            cards = s.execute(delete(ReportCardRow).where(ReportCardRow.student_ref == student_ref))
        return {
            "report_card": affected(cards),
            "report_card_audit": affected(audit),
            "report_card_outbox": affected(events),
        }

    def remaining(self, student_ref: str) -> dict[str, int]:
        with self._sf() as s:

            def count(model: Any, column: Any) -> int:
                return int(
                    s.scalar(select(func.count()).select_from(model).where(column == student_ref))
                    or 0
                )

            return {
                "report_card": count(ReportCardRow, ReportCardRow.student_ref),
                "report_card_audit": count(ReportCardAuditRow, ReportCardAuditRow.subject_ref),
                "report_card_outbox": count(ReportCardOutboxRow, ReportCardOutboxRow.student_ref),
            }

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        """Report cards are learner records (``learning_records``); dry-run counting only."""
        if data_class != "learning_records":
            return None
        with self._sf() as s:
            return int(
                s.scalar(
                    select(func.count())
                    .select_from(ReportCardRow)
                    .where(ReportCardRow.issued_at < cutoff)
                )
                or 0
            )

    def blockers(self) -> list[str]:
        return []
