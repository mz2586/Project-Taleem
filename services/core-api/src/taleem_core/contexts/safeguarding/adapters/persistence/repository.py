"""SQL repositories for the safeguarding schema (row <-> domain mapping lives here only)."""

from __future__ import annotations

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from ...domain.model import (
    AuditEntry,
    Category,
    Concern,
    Note,
    Outcome,
    Priority,
    RaisedBy,
    Status,
)
from .models import ConcernAuditRow, ConcernNoteRow, ConcernRow

_PRIORITY_RANK = case(
    {Priority.T1.value: 1, Priority.T2.value: 2, Priority.T3.value: 3},
    value=ConcernRow.priority,
    else_=9,
)


def _to_domain(row: ConcernRow) -> Concern:
    return Concern(
        concern_id=row.concern_id,
        subject_ref=row.subject_ref,
        raised_by_ref=row.raised_by_ref,
        raised_by_role=RaisedBy(row.raised_by_role),
        category=Category(row.category),
        priority=Priority(row.priority),
        free_text=row.free_text,
        context_screen=row.context_screen,
        context_lesson_id=row.context_lesson_id,
        status=Status(row.status),
        created_at=row.created_at,
        acknowledged_at=row.acknowledged_at,
        acknowledged_by=row.acknowledged_by,
        escalated_at=row.escalated_at,
        escalated_by=row.escalated_by,
        resolved_at=row.resolved_at,
        resolved_by=row.resolved_by,
        outcome=Outcome(row.outcome) if row.outcome else None,
        version=row.version,
    )


def _apply(row: ConcernRow, concern: Concern) -> None:
    # Identity of the concern (who, about whom, what was said) is never rewritten after creation;
    # only the triage fields change.
    row.status = concern.status.value
    row.outcome = concern.outcome.value if concern.outcome else None
    row.acknowledged_at = concern.acknowledged_at
    row.acknowledged_by = concern.acknowledged_by
    row.escalated_at = concern.escalated_at
    row.escalated_by = concern.escalated_by
    row.resolved_at = concern.resolved_at
    row.resolved_by = concern.resolved_by


class SqlConcernRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, concern: Concern) -> None:
        row = ConcernRow(
            concern_id=concern.concern_id,
            subject_ref=concern.subject_ref,
            raised_by_ref=concern.raised_by_ref,
            raised_by_role=concern.raised_by_role.value,
            category=concern.category.value,
            priority=concern.priority.value,
            free_text=concern.free_text,
            context_screen=concern.context_screen,
            context_lesson_id=concern.context_lesson_id,
            created_at=concern.created_at,
        )
        _apply(row, concern)
        self._s.add(row)

    def get(self, concern_id: str) -> Concern | None:
        row = self._s.get(ConcernRow, concern_id)
        return _to_domain(row) if row is not None else None

    def save(self, concern: Concern) -> None:
        row = self._s.get(ConcernRow, concern.concern_id)
        if row is None:  # pragma: no cover - the service always loads before saving
            raise LookupError(concern.concern_id)
        _apply(row, concern)
        # The version column guards the UPDATE: a second lead acting on the same concern at the
        # same moment matches no row and gets StaleDataError, which the app maps to a 409.
        self._s.flush()

    def queue(self, statuses: frozenset[Status], limit: int) -> list[Concern]:
        stmt = (
            select(ConcernRow)
            .where(ConcernRow.status.in_(sorted(s.value for s in statuses)))
            .order_by(_PRIORITY_RANK, ConcernRow.created_at, ConcernRow.concern_id)
            .limit(limit)
        )
        return [_to_domain(r) for r in self._s.scalars(stmt)]

    def raised_by(self, raised_by_ref: str, limit: int) -> list[Concern]:
        stmt = (
            select(ConcernRow)
            .where(ConcernRow.raised_by_ref == raised_by_ref)
            .order_by(ConcernRow.created_at.desc(), ConcernRow.concern_id)
            .limit(limit)
        )
        return [_to_domain(r) for r in self._s.scalars(stmt)]

    def open_counts(self) -> dict[Priority, list[float]]:
        stmt = select(ConcernRow.priority, ConcernRow.created_at).where(
            ConcernRow.status == Status.OPEN.value
        )
        out: dict[Priority, list[float]] = {p: [] for p in Priority}
        for priority, created_at in self._s.execute(stmt):
            out.setdefault(Priority(priority), []).append(float(created_at))
        return out


class SqlNoteRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, note: Note) -> None:
        self._s.add(
            ConcernNoteRow(
                note_id=note.note_id,
                concern_id=note.concern_id,
                author_ref=note.author_ref,
                body=note.body,
                created_at=note.created_at,
            )
        )

    def for_concern(self, concern_id: str) -> list[Note]:
        stmt = (
            select(ConcernNoteRow)
            .where(ConcernNoteRow.concern_id == concern_id)
            .order_by(ConcernNoteRow.created_at, ConcernNoteRow.note_id)
        )
        return [
            Note(r.note_id, r.concern_id, r.author_ref, r.body, r.created_at)
            for r in self._s.scalars(stmt)
        ]


class SqlAuditRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def append(self, entry: AuditEntry) -> None:
        self._s.add(
            ConcernAuditRow(
                event_id=entry.event_id,
                concern_id=entry.concern_id,
                action=entry.action,
                actor_ref=entry.actor_ref,
                actor_role=entry.actor_role,
                at=entry.at,
                detail=dict(entry.detail),
            )
        )

    def for_concern(self, concern_id: str) -> list[AuditEntry]:
        stmt = (
            select(ConcernAuditRow)
            .where(ConcernAuditRow.concern_id == concern_id)
            .order_by(ConcernAuditRow.at, ConcernAuditRow.event_id)
        )
        return [
            AuditEntry(
                event_id=r.event_id,
                concern_id=r.concern_id,
                action=r.action,
                actor_ref=r.actor_ref,
                actor_role=r.actor_role,
                at=r.at,
                detail={str(k): str(v) for k, v in (r.detail or {}).items()},
            )
            for r in self._s.scalars(stmt)
        ]
