"""School store: a learner's class enrolments, homework submissions, and their audit.

Three school tables name a learner, and only by the pseudonymous ``student_ref``:

- ``school.enrolment`` — which classes the learner is in;
- ``school.submission`` — the learner's written homework answers (their own words) with the
  teacher's mark and feedback (HOMEWORK_AND_MARKING_CONTRACT §5). Exported to the guardian and
  erased with the learner. For retention they are learner work: class ``learning_records``,
  dated by ``submitted_at`` (purge stays disabled until M-Gov sets the period);
- ``school.enrolment_audit`` — who joined or removed the learner from a class, and who submitted,
  marked or returned their homework, and when (``subject_ref`` is the learner). These rows are
  erased with the learner: an audit row that keeps the ref would keep the learner identifiable
  after erasure. The guardian's own actions remain provable in identity's audit trail (consent
  records and its erasure tombstone).

Organizations, teacher accounts, classrooms, and assignments describe adults and teaching
structures, so they are exempt (see ``coverage.py``) and survive a learner's erasure.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from ...school.adapters.persistence.models import EnrolmentRow, SchoolAuditRow, SubmissionRow
from ..domain.policy import RetainedSet
from ._rows import affected, row_dict

# Always present, whether or not anything was withheld, so the export never reveals that a child's
# homework was flagged (the guardian may be the person the child wrote about).
WITHHELD_NOTICE = (
    "Homework answers referenced by a safeguarding record are withheld from a guardian's export "
    "(safeguarding exemption; PENDING M-Gov)."
)


class SchoolLearnerData:
    name = "school"

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        flagged_submissions: Callable[[], set[str]] = lambda: set(),
    ) -> None:
        self._sf = session_factory
        # Submission ids referenced by a safeguarding concern, read from the safeguarding store.
        self._flagged = flagged_submissions

    def covers(self) -> tuple[str, ...]:
        return ("school.enrolment", "school.submission", "school.enrolment_audit")

    def export(self, student_ref: str) -> dict[str, Any]:
        with self._sf() as s:
            rows = s.scalars(
                select(EnrolmentRow).where(EnrolmentRow.student_ref == student_ref)
            ).all()
            flagged = self._flagged()
            # Audit events about a withheld submission are withheld with it, so no trace of it
            # (not even its id) reaches the guardian.
            audit = [
                r
                for r in s.scalars(
                    select(SchoolAuditRow)
                    .where(SchoolAuditRow.subject_ref == student_ref)
                    .order_by(SchoolAuditRow.at)
                ).all()
                if (r.object_ref or "") not in flagged
            ]
            submissions = [
                r
                for r in s.scalars(
                    select(SubmissionRow)
                    .where(SubmissionRow.student_ref == student_ref)
                    .order_by(SubmissionRow.submitted_at, SubmissionRow.submission_id)
                ).all()
                if r.submission_id not in flagged
            ]
            return {
                "enrolments": [row_dict(r) for r in rows],
                "submissions": [row_dict(r, exclude=("version",)) for r in submissions],
                "enrolment_audit": [row_dict(r) for r in audit],
                "withheld": [WITHHELD_NOTICE],
            }

    def erase(self, student_ref: str, retained: RetainedSet) -> dict[str, int]:
        with self._sf() as s, s.begin():
            submissions = s.execute(
                delete(SubmissionRow).where(SubmissionRow.student_ref == student_ref)
            )
            enrolments = s.execute(
                delete(EnrolmentRow).where(EnrolmentRow.student_ref == student_ref)
            )
            audit = s.execute(
                delete(SchoolAuditRow).where(SchoolAuditRow.subject_ref == student_ref)
            )
        return {
            "enrolment": affected(enrolments),
            "submission": affected(submissions),
            "enrolment_audit": affected(audit),
        }

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
            submissions = s.scalar(
                select(func.count())
                .select_from(SubmissionRow)
                .where(SubmissionRow.student_ref == student_ref)
            )
            return {
                "enrolment": int(enrolments or 0),
                "submission": int(submissions or 0),
                "enrolment_audit": int(audit or 0),
            }

    def count_older_than(self, data_class: str, cutoff: float) -> int | None:
        """Submissions are learner work (``learning_records``); dry-run counting only."""
        if data_class != "learning_records":
            return None
        with self._sf() as s:
            return int(
                s.scalar(
                    select(func.count())
                    .select_from(SubmissionRow)
                    .where(SubmissionRow.submitted_at < cutoff)
                )
                or 0
            )

    def blockers(self) -> list[str]:
        return []
