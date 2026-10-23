"""School audit log adapters (implement ``SchoolAuditLog``).

- ``SqlSchoolAuditLog`` — the deployed one: every class-membership change is a row in
  ``school.enrolment_audit`` (alembic 0011_school_audit; on SQLite the ORM creates it). Refs only.
- ``InMemorySchoolAuditLog`` — for unit tests of the service without a database.

Both may also emit a structured log line carrying the action and the organization only — never a
learner or adult ref, because logs must not hold child identifiers.
"""

from __future__ import annotations

from collections import deque
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ....platform.ids import uuid7
from ..domain.model import SchoolAuditEvent
from .persistence.models import SchoolAuditRow


class _Logger(Protocol):
    def info(self, message: str, **fields: object) -> None: ...


def _log(logger: _Logger | None, event: SchoolAuditEvent) -> None:
    if logger is not None:
        logger.info("school_audit", event=event.action, context=event.organization_id)


class SqlSchoolAuditLog:
    def __init__(
        self, session_factory: sessionmaker[Session], logger: _Logger | None = None
    ) -> None:
        self._sf = session_factory
        self._log = logger

    def record(self, event: SchoolAuditEvent) -> None:
        with self._sf() as s, s.begin():
            s.add(
                SchoolAuditRow(
                    event_id=f"sae_{uuid7()}",
                    action=event.action,
                    actor_ref=event.actor_ref,
                    actor_role=event.actor_role,
                    subject_ref=event.subject_ref,
                    organization_id=event.organization_id,
                    class_id=event.class_id,
                    at=event.at,
                )
            )
        _log(self._log, event)

    def events(self, subject_ref: str | None = None) -> list[SchoolAuditEvent]:
        stmt = select(SchoolAuditRow).order_by(SchoolAuditRow.at, SchoolAuditRow.event_id)
        if subject_ref is not None:
            stmt = stmt.where(SchoolAuditRow.subject_ref == subject_ref)
        with self._sf() as s:
            return [
                SchoolAuditEvent(
                    action=r.action,
                    actor_ref=r.actor_ref,
                    actor_role=r.actor_role,
                    subject_ref=r.subject_ref,
                    organization_id=r.organization_id,
                    class_id=r.class_id,
                    at=r.at,
                )
                for r in s.scalars(stmt)
            ]


class InMemorySchoolAuditLog:
    def __init__(self, logger: _Logger | None = None, *, limit: int = 10_000) -> None:
        self._events: deque[SchoolAuditEvent] = deque(maxlen=limit)
        self._log = logger

    def record(self, event: SchoolAuditEvent) -> None:
        self._events.append(event)
        _log(self._log, event)

    def events(self, subject_ref: str | None = None) -> list[SchoolAuditEvent]:
        return [e for e in self._events if subject_ref is None or e.subject_ref == subject_ref]
