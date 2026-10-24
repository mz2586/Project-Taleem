"""SQL unit of work for the reporting context (request-scoped session; rollback on error)."""

from __future__ import annotations

import time
from collections.abc import Callable
from types import TracebackType

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from .....platform.concurrency import ConcurrencyConflictError
from .repository import SqlReportCardRepository, SqlReportingAudit, SqlReportingOutbox


class SqlReportingUnitOfWork:
    cards: SqlReportCardRepository
    audit: SqlReportingAudit
    outbox: SqlReportingOutbox

    def __init__(
        self, session_factory: sessionmaker[Session], clock: Callable[[], float] = time.time
    ) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._session: Session | None = None

    def __enter__(self) -> SqlReportingUnitOfWork:
        self._session = self._session_factory()
        self.cards = SqlReportCardRepository(self._session)
        self.audit = SqlReportingAudit(self._session)
        self.outbox = SqlReportingOutbox(self._session, self._clock)
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
        except IntegrityError as exc:
            # Two teachers issuing the same learner's card for one period at once, or two
            # corrections of one card: the unique indexes let one win; the loser is a 409.
            self._session.rollback()
            raise ConcurrencyConflictError(type(exc).__name__) from exc
