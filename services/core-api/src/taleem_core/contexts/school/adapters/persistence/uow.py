"""SQL unit of work for the school context (request-scoped session; rollback on error)."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from .....platform.concurrency import ConcurrencyConflictError
from .repository import (
    SqlAssignmentRepository,
    SqlClassroomRepository,
    SqlEnrolmentRepository,
    SqlOrganizationRepository,
    SqlSubmissionRepository,
    SqlTeacherRepository,
)


class SqlSchoolUnitOfWork:
    organizations: SqlOrganizationRepository
    teachers: SqlTeacherRepository
    classrooms: SqlClassroomRepository
    enrolments: SqlEnrolmentRepository
    assignments: SqlAssignmentRepository
    submissions: SqlSubmissionRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlSchoolUnitOfWork:
        self._session = self._session_factory()
        self.organizations = SqlOrganizationRepository(self._session)
        self.teachers = SqlTeacherRepository(self._session)
        self.classrooms = SqlClassroomRepository(self._session)
        self.enrolments = SqlEnrolmentRepository(self._session)
        self.assignments = SqlAssignmentRepository(self._session)
        self.submissions = SqlSubmissionRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None and self._session is not None:
                self._session.rollback()
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        try:
            self._session.commit()
        except (IntegrityError, StaleDataError) as exc:
            # A unique key or optimistic-lock race (two first submissions of one item, two
            # teachers marking at once): the loser is a conflict, never a 500.
            self._session.rollback()
            raise ConcurrencyConflictError(str(type(exc).__name__)) from exc
