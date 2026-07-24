"""Unit of Work for the curriculum_studio persistence adapter.

One UoW == one database transaction == one session. It exposes the repository and publish port
bound to that session, and owns the two cross-cutting write concerns that must commit atomically
with every mutation:

- the **transactional outbox** (``emit_event``) — the only egress from this context;
- the **hash-chained audit log** (``record_audit``) — append-only, tamper-evident (architecture §7).

Because audit + outbox rows are written into the *same* session and committed by the *same*
``commit()``, an event or audit row can never exist without the fact it describes, and vice-versa.
The audit chain is serialized per-entity by the aggregate's optimistic lock (review F2): two
concurrent writers to one entity cannot both commit, so they cannot fork the chain.
"""

from __future__ import annotations

import hashlib
import json
from types import TracebackType
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from .....platform.concurrency import ConcurrencyConflictError
from .....platform.ids import uuid7
from .models import AuditLogRow, OutboxRow
from .repository import SqlAlchemyLessonRepository, SqlAlchemyPublishPort


def _canonical(*parts: Any) -> str:
    return json.dumps(parts, sort_keys=True, ensure_ascii=False, default=str)


class UnitOfWork:
    """Transactional scope. Use as a context manager; commit on success, rollback on error."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._last_hash: dict[str, str] = {}

    def __enter__(self) -> UnitOfWork:
        self._session = self._session_factory()
        self.lessons = SqlAlchemyLessonRepository(self._session, self)
        self.publish = SqlAlchemyPublishPort(self._session, self)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                self.rollback()
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork used outside its context manager")
        return self._session

    def commit(self) -> None:
        try:
            self.session.commit()
        except StaleDataError as exc:
            # Optimistic-lock loser (a concurrent writer bumped the aggregate's version). Retryable.
            self.rollback()
            raise ConcurrencyConflictError(str(exc)) from exc
        except OperationalError as exc:
            if "database is locked" in str(exc).lower():  # SQLite serializes writers with a lock
                self.rollback()
                raise ConcurrencyConflictError(str(exc)) from exc
            raise

    def rollback(self) -> None:
        self.session.rollback()
        self._last_hash.clear()

    # -- cross-cutting writes -------------------------------------------------------------

    def emit_event(
        self,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, Any],
        event_version: int = 1,
    ) -> None:
        """Enqueue a domain event in the outbox (delivered later by the relay)."""
        self.session.add(
            OutboxRow(
                id=uuid7(),
                aggregate_type=aggregate_type,
                aggregate_id=aggregate_id,
                event_type=event_type,
                event_version=event_version,
                payload=payload,
            )
        )

    def record_audit(
        self,
        *,
        entity_type: str,
        entity_id: str,
        action: str,
        actor_role: str = "",
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
        correlation_id: str = "",
    ) -> None:
        """Append a hash-chained audit row for a mutation (architecture §7)."""
        prev = self._last_hash.get(entity_id)
        if prev is None:
            prev = (
                self.session.execute(
                    select(AuditLogRow.row_hash)
                    .where(AuditLogRow.entity_id == entity_id)
                    .order_by(AuditLogRow.at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                or ""
            )
        row_hash = (
            "sha256:"
            + hashlib.sha256(
                _canonical(prev, entity_type, entity_id, action, actor_role, before, after).encode(
                    "utf-8"
                )
            ).hexdigest()
        )
        self.session.add(
            AuditLogRow(
                id=uuid7(),
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor_role=actor_role,
                before=before,
                after=after,
                correlation_id=correlation_id,
                prev_hash=prev,
                row_hash=row_hash,
            )
        )
        self._last_hash[entity_id] = row_hash
