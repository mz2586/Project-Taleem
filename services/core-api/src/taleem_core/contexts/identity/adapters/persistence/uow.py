"""Unit of Work for the identity context — one transaction per identity operation.

Everything an identity use case touches commits together. That matters most on the failure paths: a
wrong PIN increments the learner's attempt counter *and* writes the audit row, and if either were to
land without the other the lockout would be unenforceable or the trail would be incomplete.

Committing more than once inside a single ``with`` block is intentional and supported (a failed
sign-in commits its counter, then raises), so ``commit`` re-opens cleanly rather than leaving the
session unusable.
"""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from .....platform.concurrency import ConcurrencyConflictError
from .repository import (
    SqlAuditRepository,
    SqlConsentRepository,
    SqlGuardianRepository,
    SqlLearnerRepository,
    SqlRefreshTokenRepository,
)


class SqlIdentityUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> SqlIdentityUnitOfWork:
        self._session = self._session_factory()
        self.guardians = SqlGuardianRepository(self._session)
        self.learners = SqlLearnerRepository(self._session)
        self.consents = SqlConsentRepository(self._session)
        self.audit = SqlAuditRepository(self._session)
        self.refresh_tokens = SqlRefreshTokenRepository(self._session)
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
            raise RuntimeError("SqlIdentityUnitOfWork used outside its context manager")
        return self._session

    def commit(self) -> None:
        try:
            self.session.commit()
        except StaleDataError as exc:
            # Optimistic-lock loser (two writers raced on the same account row). Retryable — the
            # app maps this to a 409 rather than a 500.
            self.session.rollback()
            raise ConcurrencyConflictError(str(exc)) from exc
        except OperationalError as exc:
            if "database is locked" in str(exc).lower():
                self.session.rollback()
                raise ConcurrencyConflictError(str(exc)) from exc
            raise

    def rollback(self) -> None:
        self.session.rollback()
