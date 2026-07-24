"""Unit of Work for the learning context — one transaction per learning operation.

Exposes the StudentKnowledge repository and an EventPublisher (outbox), committed atomically so an
event can never exist without the state change that produced it (LEARNING_DOMAIN_MODEL §7).
"""

from __future__ import annotations

from collections.abc import Sequence
from types import TracebackType

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from .....platform.ids import uuid7
from ...application.concurrency import ConcurrencyConflictError
from ...domain.events import LearningEvent
from .models import LearningOutboxRow
from .repository import SqlAlchemyStudentKnowledgeRepository


class _OutboxPublisher:
    def __init__(self, session: Session) -> None:
        self._session = session

    def publish(self, events: Sequence[LearningEvent]) -> None:
        for event in events:
            self._session.add(
                LearningOutboxRow(
                    id=uuid7(),
                    aggregate_type=event.aggregate_type,
                    aggregate_id=event.aggregate_id,
                    event_type=event.event_type,
                    payload=event.payload,
                    occurred_at=event.occurred_at,
                )
            )


class LearningUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> LearningUnitOfWork:
        self._session = self._session_factory()
        self.knowledge = SqlAlchemyStudentKnowledgeRepository(self._session)
        self.events = _OutboxPublisher(self._session)
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

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("LearningUnitOfWork used outside its context manager")
        return self._session

    def commit(self) -> None:
        try:
            self.session.commit()
        except StaleDataError as exc:
            # Optimistic-lock loser: a concurrent writer bumped version_id_col. Retryable.
            self.session.rollback()
            raise ConcurrencyConflictError(str(exc)) from exc
        except OperationalError as exc:
            # SQLite serializes writers with a lock ("database is locked"); treat as retryable too.
            if "database is locked" in str(exc).lower():
                self.session.rollback()
                raise ConcurrencyConflictError(str(exc)) from exc
            raise

    def rollback(self) -> None:
        self.session.rollback()
