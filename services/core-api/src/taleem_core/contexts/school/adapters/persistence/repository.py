"""SQL repositories for the school schema.

Every multi-tenant read filters by ``organization_id``.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from .....platform.concurrency import ConcurrencyConflictError
from ...domain.model import (
    Assignment,
    Classroom,
    Enrolment,
    MarkOutcome,
    Organization,
    Submission,
    SubmissionSource,
    SubmissionStatus,
    Teacher,
    TeacherStatus,
)
from .models import (
    AssignmentRow,
    ClassroomRow,
    EnrolmentRow,
    OrganizationRow,
    SubmissionRow,
    TeacherRow,
)


class SqlOrganizationRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, org: Organization) -> None:
        self._s.add(
            OrganizationRow(
                organization_id=org.organization_id,
                name=org.name,
                country=org.country,
                curriculum_pack_id=org.curriculum_pack_id,
                default_locale=org.default_locale,
                created_at=org.created_at,
            )
        )

    def get(self, organization_id: str) -> Organization | None:
        row = self._s.get(OrganizationRow, organization_id)
        if row is None:
            return None
        return Organization(
            organization_id=row.organization_id,
            name=row.name,
            country=row.country,
            curriculum_pack_id=row.curriculum_pack_id,
            default_locale=row.default_locale,
            created_at=row.created_at,
        )


def _teacher(row: TeacherRow) -> Teacher:
    return Teacher(
        teacher_ref=row.teacher_ref,
        organization_id=row.organization_id,
        email=row.email,
        display_name=row.display_name,
        passphrase_hash=row.passphrase_hash,
        status=TeacherStatus(row.status),
        failed_attempts=row.failed_attempts,
        created_at=row.created_at,
        cohort=row.cohort or "",
    )


class SqlTeacherRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, teacher: Teacher) -> None:
        self._s.add(
            TeacherRow(
                teacher_ref=teacher.teacher_ref,
                organization_id=teacher.organization_id,
                email=teacher.email,
                display_name=teacher.display_name,
                passphrase_hash=teacher.passphrase_hash,
                status=teacher.status.value,
                failed_attempts=teacher.failed_attempts,
                created_at=teacher.created_at,
                cohort=teacher.cohort,
            )
        )

    def get(self, teacher_ref: str) -> Teacher | None:
        row = self._s.get(TeacherRow, teacher_ref)
        return _teacher(row) if row else None

    def by_email(self, email: str) -> Teacher | None:
        row = self._s.scalars(select(TeacherRow).where(TeacherRow.email == email)).first()
        return _teacher(row) if row else None

    def save(self, teacher: Teacher) -> None:
        row = self._s.get(TeacherRow, teacher.teacher_ref)
        if row is None:
            self.add(teacher)
            return
        row.display_name = teacher.display_name
        row.passphrase_hash = teacher.passphrase_hash
        row.status = teacher.status.value
        row.failed_attempts = teacher.failed_attempts
        # ``cohort`` is deliberately not written here: only ``set_cohort`` changes it.

    def set_cohort(self, teacher_ref: str, cohort: str) -> bool:
        """Set a teacher's cohort (the demo seeder's non-HTTP path). True if it changed."""
        row = self._s.get(TeacherRow, teacher_ref)
        if row is None or row.cohort == cohort:
            return False
        row.cohort = cohort
        return True


def _classroom(row: ClassroomRow) -> Classroom:
    return Classroom(
        class_id=row.class_id,
        organization_id=row.organization_id,
        teacher_ref=row.teacher_ref,
        name=row.name,
        join_code=row.join_code,
        created_at=row.created_at,
    )


class SqlClassroomRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, classroom: Classroom) -> None:
        self._s.add(
            ClassroomRow(
                class_id=classroom.class_id,
                organization_id=classroom.organization_id,
                teacher_ref=classroom.teacher_ref,
                name=classroom.name,
                join_code=classroom.join_code,
                created_at=classroom.created_at,
            )
        )

    def get(self, organization_id: str, class_id: str) -> Classroom | None:
        row = self._s.scalars(
            select(ClassroomRow).where(
                ClassroomRow.organization_id == organization_id, ClassroomRow.class_id == class_id
            )
        ).first()
        return _classroom(row) if row else None

    def for_teacher(self, organization_id: str, teacher_ref: str) -> list[Classroom]:
        rows = self._s.scalars(
            select(ClassroomRow)
            .where(
                ClassroomRow.organization_id == organization_id,
                ClassroomRow.teacher_ref == teacher_ref,
            )
            .order_by(ClassroomRow.created_at, ClassroomRow.class_id)
        )
        return [_classroom(r) for r in rows]

    def by_join_code(self, join_code: str) -> Classroom | None:
        row = self._s.scalars(
            select(ClassroomRow).where(ClassroomRow.join_code == join_code)
        ).first()
        return _classroom(row) if row else None


def _enrolment(row: EnrolmentRow) -> Enrolment:
    return Enrolment(
        class_id=row.class_id,
        organization_id=row.organization_id,
        student_ref=row.student_ref,
        approved_by=row.approved_by,
        joined_at=row.joined_at,
    )


class SqlEnrolmentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, enrolment: Enrolment) -> None:
        self._s.add(
            EnrolmentRow(
                class_id=enrolment.class_id,
                organization_id=enrolment.organization_id,
                student_ref=enrolment.student_ref,
                approved_by=enrolment.approved_by,
                joined_at=enrolment.joined_at,
            )
        )

    def get(self, organization_id: str, class_id: str, student_ref: str) -> Enrolment | None:
        row = self._s.scalars(
            select(EnrolmentRow).where(
                EnrolmentRow.organization_id == organization_id,
                EnrolmentRow.class_id == class_id,
                EnrolmentRow.student_ref == student_ref,
            )
        ).first()
        return _enrolment(row) if row else None

    def for_class(self, organization_id: str, class_id: str) -> list[Enrolment]:
        rows = self._s.scalars(
            select(EnrolmentRow)
            .where(
                EnrolmentRow.organization_id == organization_id,
                EnrolmentRow.class_id == class_id,
            )
            .order_by(EnrolmentRow.joined_at, EnrolmentRow.student_ref)
        )
        return [_enrolment(r) for r in rows]

    def for_student(self, student_ref: str) -> list[Enrolment]:
        rows = self._s.scalars(
            select(EnrolmentRow)
            .where(EnrolmentRow.student_ref == student_ref)
            .order_by(EnrolmentRow.joined_at, EnrolmentRow.class_id)
        )
        return [_enrolment(r) for r in rows]

    def remove(self, organization_id: str, class_id: str, student_ref: str) -> bool:
        row = self._s.scalars(
            select(EnrolmentRow).where(
                EnrolmentRow.organization_id == organization_id,
                EnrolmentRow.class_id == class_id,
                EnrolmentRow.student_ref == student_ref,
            )
        ).first()
        if row is None:
            return False
        self._s.delete(row)
        return True


def _assignment(row: AssignmentRow) -> Assignment:
    return Assignment(
        assignment_id=row.assignment_id,
        class_id=row.class_id,
        organization_id=row.organization_id,
        objective_code=row.objective_code,
        due_at=row.due_at,
        assigned_by=row.assigned_by,
        created_at=row.created_at,
    )


class SqlAssignmentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, assignment: Assignment) -> None:
        self._s.add(
            AssignmentRow(
                assignment_id=assignment.assignment_id,
                class_id=assignment.class_id,
                organization_id=assignment.organization_id,
                objective_code=assignment.objective_code,
                due_at=assignment.due_at,
                assigned_by=assignment.assigned_by,
                created_at=assignment.created_at,
            )
        )

    def get(self, organization_id: str, assignment_id: str) -> Assignment | None:
        row = self._s.scalars(
            select(AssignmentRow).where(
                AssignmentRow.organization_id == organization_id,
                AssignmentRow.assignment_id == assignment_id,
            )
        ).first()
        return _assignment(row) if row else None

    def for_class(self, organization_id: str, class_id: str) -> list[Assignment]:
        rows = self._s.scalars(
            select(AssignmentRow)
            .where(
                AssignmentRow.organization_id == organization_id,
                AssignmentRow.class_id == class_id,
            )
            .order_by(AssignmentRow.created_at, AssignmentRow.assignment_id)
        )
        return [_assignment(r) for r in rows]


def _submission(row: SubmissionRow) -> Submission:
    return Submission(
        submission_id=row.submission_id,
        organization_id=row.organization_id,
        class_id=row.class_id,
        assignment_id=row.assignment_id,
        objective_code=row.objective_code,
        item_ref=row.item_ref,
        student_ref=row.student_ref,
        text=row.text,
        status=SubmissionStatus(row.status),
        submitted_at=row.submitted_at,
        created_at=row.created_at,
        attempt=row.attempt,
        max_score=row.max_score,
        outcome=MarkOutcome(row.outcome) if row.outcome else None,
        score=row.score,
        feedback=row.feedback,
        returned_at=row.returned_at,
        marked_at=row.marked_at,
        reviewed_by=row.reviewed_by,
        version=row.version,
        source=SubmissionSource(row.source),
    )


def _write(row: SubmissionRow, sub: Submission) -> None:
    row.text = sub.text
    row.status = sub.status.value
    row.attempt = sub.attempt
    row.max_score = sub.max_score
    row.outcome = sub.outcome.value if sub.outcome else None
    row.score = sub.score
    row.feedback = sub.feedback
    row.submitted_at = sub.submitted_at
    row.returned_at = sub.returned_at
    row.marked_at = sub.marked_at
    row.reviewed_by = sub.reviewed_by


class SqlSubmissionRepository:
    """Every read is tenant-scoped, except ``for_student`` (the learner's own work)."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def add(self, submission: Submission) -> None:
        row = SubmissionRow(
            submission_id=submission.submission_id,
            organization_id=submission.organization_id,
            class_id=submission.class_id,
            assignment_id=submission.assignment_id,
            objective_code=submission.objective_code,
            item_ref=submission.item_ref,
            student_ref=submission.student_ref,
            created_at=submission.created_at,
            source=submission.source.value,
        )
        _write(row, submission)
        self._s.add(row)

    def get(self, organization_id: str, submission_id: str) -> Submission | None:
        row = self._s.scalars(
            select(SubmissionRow).where(
                SubmissionRow.organization_id == organization_id,
                SubmissionRow.submission_id == submission_id,
            )
        ).first()
        return _submission(row) if row else None

    def by_id(self, submission_id: str) -> Submission | None:
        row = self._s.get(SubmissionRow, submission_id)
        return _submission(row) if row else None

    def find(self, assignment_id: str, item_ref: str, student_ref: str) -> Submission | None:
        row = self._s.scalars(
            select(SubmissionRow).where(
                SubmissionRow.assignment_id == assignment_id,
                SubmissionRow.item_ref == item_ref,
                SubmissionRow.student_ref == student_ref,
            )
        ).first()
        return _submission(row) if row else None

    def find_self_paced(
        self, objective_code: str, item_ref: str, student_ref: str
    ) -> Submission | None:
        row = self._s.scalars(
            select(SubmissionRow).where(
                SubmissionRow.source == SubmissionSource.SELF_PACED.value,
                SubmissionRow.objective_code == objective_code,
                SubmissionRow.item_ref == item_ref,
                SubmissionRow.student_ref == student_ref,
            )
        ).first()
        return _submission(row) if row else None

    def for_student(self, student_ref: str) -> list[Submission]:
        rows = self._s.scalars(
            select(SubmissionRow)
            .where(SubmissionRow.student_ref == student_ref)
            .order_by(SubmissionRow.submitted_at, SubmissionRow.submission_id)
        )
        return [_submission(r) for r in rows]

    def for_class(
        self, organization_id: str, class_id: str, status: SubmissionStatus
    ) -> list[Submission]:
        rows = self._s.scalars(
            select(SubmissionRow)
            .where(
                SubmissionRow.organization_id == organization_id,
                SubmissionRow.class_id == class_id,
                SubmissionRow.status == status.value,
            )
            .order_by(SubmissionRow.submitted_at, SubmissionRow.submission_id)
        )
        return [_submission(r) for r in rows]

    def save(self, submission: Submission) -> None:
        """Write the changed state. The row's ``version`` guards against a concurrent change: the
        loser gets ``ConcurrencyConflictError`` here or at commit (HTTP 409)."""
        row = self._s.get(SubmissionRow, submission.submission_id)
        if row is None:
            self.add(submission)
            return
        if row.version != submission.version:
            raise ConcurrencyConflictError("submission changed since it was read")
        _write(row, submission)
