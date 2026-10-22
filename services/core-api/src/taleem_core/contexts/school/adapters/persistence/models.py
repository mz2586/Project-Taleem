"""ORM models for the school schema (see alembic 0008_school).

Every child table repeats ``organization_id`` so a tenant-scoped query never depends on a join.
``enrolment`` holds only a pseudonymous ``student_ref`` — a child's name stays in identity.
"""

from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Index, Integer, String
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
