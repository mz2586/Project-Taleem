"""SQL unit of work for the school context (request-scoped session; rollback on error)."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from .repository import (
    SqlAssignmentRepository,
    SqlClassroomRepository,
    SqlEnrolmentRepository,
    SqlOrganizationRepository,
    SqlTeacherRepository,
)


class SqlSchoolUnitOfWork:
    organizations: SqlOrganizationRepository
    teachers: SqlTeacherRepository
    classrooms: SqlClassroomRepository
    enrolments: SqlEnrolmentRepository
    assignments: SqlAssignmentRepository

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
        self._session.commit()
