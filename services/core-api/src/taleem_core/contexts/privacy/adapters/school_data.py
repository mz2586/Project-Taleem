"""School store: a learner's class enrolments and the audit of those enrolments.

Two school tables name a learner, and only by the pseudonymous ``student_ref``:

- ``school.enrolment`` — which classes the learner is in;
- ``school.enrolment_audit`` — who joined or removed the learner from a class, and when
  (``subject_ref`` is the learner). These rows are erased with the learner: an audit row that keeps
  the ref would keep the learner identifiable after erasure. The guardian's own actions remain
  provable in identity's audit trail (consent records and its erasure tombstone).

Organizations, teacher accounts, classrooms, and assignments describe adults and teaching
structures, so they are exempt (see ``coverage.py``) and survive a learner's erasure.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ...school.adapters.persistence.models import EnrolmentRow, SchoolAuditRow
from ..domain.policy import RetainedSet
from ._rows import affected, row_dict


class SchoolLearnerData:
    name = "school"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def covers(self) -> tuple[str, ...]:
        return ("school.enrolment", "school.enrolment_audit")

    def export(self, student_ref: str) -> dict[str, Any]:
        with self._sf() as s:
            rows = s.scalars(
                select(EnrolmentRow).where(EnrolmentRow.student_ref == student_ref)
            ).all()
            audit = s.scalars(
                select(SchoolAuditRow)
                .where(SchoolAuditRow.subject_ref == student_ref)
                .order_by(SchoolAuditRow.at)
            ).all()
            return {
                "enrolments": [row_dict(r) for r in rows],
                "enrolment_audit": [row_dict(r) for r in audit],
                "withheld": [],
            }

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        with self._sf() as s, s.begin():
            enrolments = s.execute(
                delete(EnrolmentRow).where(EnrolmentRow.student_ref == student_ref)
            )
            audit = s.execute(
                delete(SchoolAuditRow).where(SchoolAuditRow.subject_ref == student_ref)
            )
        return {"enrolment": affected(enrolments), "enrolment_audit": affected(audit)}

    def remaining(self, student_ref: str) -> dict[str, int]:
        with self._sf() as s:
            enrolments = s.scalar(
                select(func.count())
                .select_from(EnrolmentRow)
                .where(EnrolmentRow.student_ref == student_ref)
            )
            audit = s.scalar(
                select(func.count())
                .select_from(SchoolAuditRow)
                .where(SchoolAuditRow.subject_ref == student_ref)
            )
            return {"enrolment": int(enrolments or 0), "enrolment_audit": int(audit or 0)}

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        return None

    def blockers(self) -> list[str]:
        return []
