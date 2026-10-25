"""SQL unit of work for the safeguarding context: one session, one transaction, rollback on error.

A concern's change and its audit entry are written in the same transaction, so an action is never
recorded without its audit row (or the reverse).
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.orm import Session, sessionmaker

from .repository import (
    SqlAuditRepository,
    SqlConcernRepository,
    SqlEvidenceRepository,
    SqlNoteRepository,
)


class SqlSafeguardingUnitOfWork:
    concerns: SqlConcernRepository
    notes: SqlNoteRepository
    audit: SqlAuditRepository
    evidence: SqlEvidenceRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlSafeguardingUnitOfWork:
        self._session = self._session_factory()
        self.concerns = SqlConcernRepository(self._session)
        self.notes = SqlNoteRepository(self._session)
        self.audit = SqlAuditRepository(self._session)
        self.evidence = SqlEvidenceRepository(self._session)
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
