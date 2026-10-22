"""School store: a learner's class enrolments.

``school.enrolment`` is the only school table that names a learner, and only by the pseudonymous
``student_ref``. Organizations, teacher accounts, classrooms, and assignments describe adults and
teaching structures, so they are exempt (see ``coverage.py``) and survive a learner's erasure.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ...school.adapters.persistence.models import EnrolmentRow
from ..domain.policy import RetainedSet
from ._rows import affected, row_dict


class SchoolLearnerData:
    name = "school"

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sf = session_factory

    def covers(self) -> tuple[str, ...]:
        return ("school.enrolment",)

    def export(self, student_ref: str) -> dict[str, Any]:
        with self._sf() as s:
            rows = s.scalars(
                select(EnrolmentRow).where(EnrolmentRow.student_ref == student_ref)
            ).all()
            return {"enrolments": [row_dict(r) for r in rows], "withheld": []}

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        with self._sf() as s, s.begin():
            result = s.execute(delete(EnrolmentRow).where(EnrolmentRow.student_ref == student_ref))
        return {"enrolment": affected(result)}

    def remaining(self, student_ref: str) -> dict[str, int]:
        with self._sf() as s:
            count = s.scalar(
                select(func.count())
                .select_from(EnrolmentRow)
                .where(EnrolmentRow.student_ref == student_ref)
            )
            return {"enrolment": int(count or 0)}

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        return None

    def blockers(self) -> list[str]:
        return []
