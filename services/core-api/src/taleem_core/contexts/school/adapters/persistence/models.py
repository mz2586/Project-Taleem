"""ORM models for the school schema (see alembic 0008_school).

Every child table repeats ``organization_id`` so a tenant-scoped query never depends on a join.
``enrolment`` holds only a pseudonymous ``student_ref`` — a child's name stays in identity.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import SCHOOL_SCHEMA, SchoolBase


class OrganizationRow(SchoolBase):
    __tablename__ = "organization"
    __table_args__ = ({"schema": SCHOOL_SCHEMA},)

    organization_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    country: Mapped[str] = mapped_column(String(2), nullable=False)
    curriculum_pack_id: Mapped[str] = mapped_column(String(64), nullable=False)
    default_locale: Mapped[str] = mapped_column(String(8), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class TeacherRow(SchoolBase):
    __tablename__ = "teacher_account"
    __table_args__ = (
        Index("ix_teacher_org", "organization_id"),
        {"schema": SCHOOL_SCHEMA},
    )

    teacher_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHOOL_SCHEMA}.organization.organization_id", ondelete="CASCADE"),
        nullable=False,
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(60), nullable=False)
    passphrase_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    failed_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class ClassroomRow(SchoolBase):
    __tablename__ = "classroom"
    __table_args__ = (
        Index("ix_classroom_org_teacher", "organization_id", "teacher_ref"),
        {"schema": SCHOOL_SCHEMA},
    )

    class_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHOOL_SCHEMA}.organization.organization_id", ondelete="CASCADE"),
        nullable=False,
    )
    teacher_ref: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHOOL_SCHEMA}.teacher_account.teacher_ref", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    join_code: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class EnrolmentRow(SchoolBase):
    __tablename__ = "enrolment"
    __table_args__ = (
        Index("ix_enrolment_org_class", "organization_id", "class_id"),
        {"schema": SCHOOL_SCHEMA},
    )

    class_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHOOL_SCHEMA}.classroom.class_id", ondelete="CASCADE"),
        primary_key=True,
    )
    student_ref: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str] = mapped_column(String(64), nullable=False)
    joined_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class AssignmentRow(SchoolBase):
    __tablename__ = "assignment"
    __table_args__ = (
        Index("ix_assignment_org_class", "organization_id", "class_id"),
        {"schema": SCHOOL_SCHEMA},
    )

    assignment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    class_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHOOL_SCHEMA}.classroom.class_id", ondelete="CASCADE"),
        nullable=False,
    )
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    objective_code: Mapped[str] = mapped_column(String(64), nullable=False)
    due_at: Mapped[float] = mapped_column(Float, nullable=False)
    assigned_by: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)


class SchoolAuditRow(SchoolBase):
    """Append-only record of class-membership changes (see alembic 0011_school_audit).

    Pseudonymous refs only — never a learner's or an adult's name. ``subject_ref`` is the learner's
    ``student_ref``; the privacy context erases these rows with the learner.
    """

    __tablename__ = "enrolment_audit"
    __table_args__ = (
        Index("ix_school_audit_subject", "subject_ref"),
        Index("ix_school_audit_org_at", "organization_id", "at"),
        {"schema": SCHOOL_SCHEMA},
    )

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    subject_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    class_id: Mapped[str] = mapped_column(String(64), nullable=False)
    at: Mapped[float] = mapped_column(Float, nullable=False)
    # The submission_id for submission.* actions (alembic 0013); '' for enrolment actions.
    object_ref: Mapped[str] = mapped_column(String(64), nullable=False, default="")


class SubmissionRow(SchoolBase):
    """A learner's written answer to one item of an assignment (see alembic 0013_homework).

    Child data: the ``text`` is the child's own words. Pseudonymous ``student_ref`` only. One row
    per (assignment, item, learner); ``version`` is the optimistic lock (two teachers marking at
    once: one gets a 409). The privacy context exports and erases these rows with the learner.
    """

    __tablename__ = "submission"
    __table_args__ = (
        UniqueConstraint(
            "assignment_id", "item_ref", "student_ref", name="uq_submission_item_learner"
        ),
        Index("ix_submission_org_class_status", "organization_id", "class_id", "status"),
        Index("ix_submission_student", "student_ref"),
        {"schema": SCHOOL_SCHEMA},
    )

    submission_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    organization_id: Mapped[str] = mapped_column(String(64), nullable=False)
    class_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHOOL_SCHEMA}.classroom.class_id", ondelete="CASCADE"),
        nullable=False,
    )
    assignment_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey(f"{SCHOOL_SCHEMA}.assignment.assignment_id", ondelete="CASCADE"),
        nullable=False,
    )
    objective_code: Mapped[str] = mapped_column(String(64), nullable=False)
    item_ref: Mapped[str] = mapped_column(String(128), nullable=False)
    student_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_at: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[float] = mapped_column(Float, nullable=False)
    returned_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    marked_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__ = {"version_id_col": version}
