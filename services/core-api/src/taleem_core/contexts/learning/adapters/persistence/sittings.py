"""SQLAlchemy repository for unit-check sittings (``learning.unit_check_sitting``, migration 0019).

Maps the pure ``Sitting`` aggregate to its row and back. Optimistic-locked by the row's
``lock_version``: a concurrent writer of the same sitting loses at commit and is retried by the
caller (``retry_on_conflict``), re-reading the latest state — which is what makes answering an item
once per sitting idempotent under concurrency.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...domain.progression import CheckResult, PaperItem, Sitting, SittingAnswer, SittingStatus
from .models import UnitCheckSittingRow


def _to_domain(row: UnitCheckSittingRow) -> Sitting:
    return Sitting(
        sitting_id=row.sitting_id,
        student_ref=row.student_ref,
        pack_id=row.pack_id,
        grade_key=row.grade_key,
        subject_key=row.subject_key,
        unit_id=row.unit_id,
        unit_title={str(k): str(v) for k, v in (row.unit_title or {}).items()},
        items=tuple(PaperItem.from_dict(d) for d in row.items or []),
        pass_percent=row.pass_percent,
        started_at=row.started_at,
        expires_at=row.expires_at,
        status=SittingStatus(row.status),
        answers={
            str(ref): SittingAnswer.from_dict(str(ref), d) for ref, d in (row.answers or {}).items()
        },
        finished_at=row.finished_at,
        result=CheckResult.from_dict(row.result) if row.result else None,
        lock_version=row.lock_version,
    )


def _apply(row: UnitCheckSittingRow, sitting: Sitting) -> None:
    row.status = sitting.status.value
    # New containers so a JSON column change is always detected.
    row.answers = {ref: a.to_dict() for ref, a in sitting.answers.items()}
    row.finished_at = sitting.finished_at
    row.result = sitting.result.to_dict() if sitting.result is not None else None


class SqlAlchemySittingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._rows: dict[str, UnitCheckSittingRow] = {}

    def get(self, sitting_id: str) -> Sitting | None:
        row = self._session.get(UnitCheckSittingRow, sitting_id)
        if row is None:
            return None
        self._rows[row.sitting_id] = row
        return _to_domain(row)

    def for_student(self, student_ref: str) -> list[Sitting]:
        rows = self._session.execute(
            select(UnitCheckSittingRow)
            .where(UnitCheckSittingRow.student_ref == student_ref)
            .order_by(UnitCheckSittingRow.started_at, UnitCheckSittingRow.sitting_id)
        ).scalars()
        out: list[Sitting] = []
        for row in rows:
            self._rows[row.sitting_id] = row
            out.append(_to_domain(row))
        return out

    def add(self, sitting: Sitting) -> None:
        row = UnitCheckSittingRow(
            sitting_id=sitting.sitting_id,
            student_ref=sitting.student_ref,
            pack_id=sitting.pack_id,
            grade_key=sitting.grade_key,
            subject_key=sitting.subject_key,
            unit_id=sitting.unit_id,
            unit_title=dict(sitting.unit_title),
            status=sitting.status.value,
            items=[p.to_dict() for p in sitting.items],
            answers={},
            pass_percent=sitting.pass_percent,
            started_at=sitting.started_at,
            expires_at=sitting.expires_at,
        )
        _apply(row, sitting)
        self._session.add(row)
        self._rows[row.sitting_id] = row

    def save(self, sitting: Sitting) -> None:
        """Write a sitting loaded through this repository (its row is tracked)."""
        row = self._rows.get(sitting.sitting_id)
        if row is None:
            raise KeyError(f"sitting {sitting.sitting_id} was not loaded in this unit of work")
        _apply(row, sitting)
