"""SQL repositories for the reporting schema. A card row is inserted once and never updated,
except the one-time acknowledgement (a guarded ``UPDATE ... WHERE acknowledged_at IS NULL``)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .....platform.ids import uuid7
from ...domain.report_card import ReportCard, ReportingAuditEvent
from .models import ReportCardAuditRow, ReportCardOutboxRow, ReportCardRow


def _card(r: ReportCardRow) -> ReportCard:
    return ReportCard(
        card_id=r.card_id,
        student_ref=r.student_ref,
        organization_id=r.organization_id,
        class_id=r.class_id,
        period_start=int(r.period_start),
        period_end=int(r.period_end),
        body_json=r.body,
        content_hash=r.content_hash,
        supersedes=r.supersedes,
        issued_by=r.issued_by,
        issued_at=float(r.issued_at),
        acknowledged_at=r.acknowledged_at,
        acknowledged_by=r.acknowledged_by,
    )


class SqlReportCardRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, card: ReportCard) -> None:
        self._s.add(
            ReportCardRow(
                card_id=card.card_id,
                student_ref=card.student_ref,
                organization_id=card.organization_id,
                class_id=card.class_id,
                period_start=card.period_start,
                period_end=card.period_end,
                body=card.body_json,
                content_hash=card.content_hash,
                supersedes=card.supersedes,
                issued_by=card.issued_by,
                issued_at=card.issued_at,
            )
        )

    def get(self, card_id: str) -> ReportCard | None:
        row = self._s.get(ReportCardRow, card_id, populate_existing=True)
        return _card(row) if row is not None else None

    def for_student(self, student_ref: str) -> list[ReportCard]:
        return self._many(ReportCardRow.student_ref == student_ref)

    def for_class(self, organization_id: str, class_id: str) -> list[ReportCard]:
        return self._many(
            ReportCardRow.organization_id == organization_id, ReportCardRow.class_id == class_id
        )

    def for_slot(
        self, student_ref: str, class_id: str, period_start: int, period_end: int
    ) -> list[ReportCard]:
        return self._many(
            ReportCardRow.student_ref == student_ref,
            ReportCardRow.class_id == class_id,
            ReportCardRow.period_start == period_start,
            ReportCardRow.period_end == period_end,
        )

    def successors(self, card_ids: list[str]) -> dict[str, str]:
        if not card_ids:
            return {}
        rows = self._s.execute(
            select(ReportCardRow.supersedes, ReportCardRow.card_id).where(
                ReportCardRow.supersedes.in_(card_ids)
            )
        )
        return {str(old): str(new) for old, new in rows if old}

    def acknowledge(self, card_id: str, guardian_ref: str, at: float) -> bool:
        result = self._s.execute(
            update(ReportCardRow)
            .where(ReportCardRow.card_id == card_id, ReportCardRow.acknowledged_at.is_(None))
            .values(acknowledged_at=at, acknowledged_by=guardian_ref)
            .execution_options(synchronize_session=False)
        )
        return bool(getattr(result, "rowcount", 0))

    def _many(self, *where: Any) -> list[ReportCard]:
        stmt = select(ReportCardRow).where(*where).order_by(ReportCardRow.issued_at.desc())
        return [_card(r) for r in self._s.scalars(stmt.execution_options(populate_existing=True))]


class SqlReportingAudit:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, event: ReportingAuditEvent) -> None:
        self._s.add(
            ReportCardAuditRow(
                event_id=f"rpa_{uuid7()}",
                action=event.action,
                actor_ref=event.actor_ref,
                actor_role=event.actor_role,
                subject_ref=event.subject_ref,
                organization_id=event.organization_id,
                class_id=event.class_id,
                card_id=event.card_id,
                at=event.at,
            )
        )


class SqlReportingOutbox:
    def __init__(self, session: Session, clock: Callable[[], float]) -> None:
        self._s = session
        self._now = clock

    def add(
        self, *, event_type: str, aggregate_id: str, student_ref: str, payload: dict[str, Any]
    ) -> None:
        self._s.add(
            ReportCardOutboxRow(
                id=f"rpo_{uuid7()}",
                event_type=event_type,
                aggregate_id=aggregate_id,
                student_ref=student_ref,
                payload=dict(payload),
                occurred_at=self._now(),
            )
        )
