"""School audit log adapter.

Interim, per-process implementation: every class-membership change is kept in a bounded in-memory
ring (readable by tests and ops tooling) and emitted as a structured log line that carries the
action and the organization only — never a learner or adult ref, because logs must not hold child
identifiers. A durable ``school.audit_event`` table is a follow-up migration (it needs a revision
after the identity staff-accounts migration).
"""

from __future__ import annotations

from collections import deque
from typing import Protocol

from ..domain.model import SchoolAuditEvent


class _Logger(Protocol):
    def info(self, message: str, **fields: object) -> None: ...


class InMemorySchoolAuditLog:
    def __init__(self, logger: _Logger | None = None, *, limit: int = 10_000) -> None:
        self._events: deque[SchoolAuditEvent] = deque(maxlen=limit)
        self._log = logger

    def record(self, event: SchoolAuditEvent) -> None:
        self._events.append(event)
        if self._log is not None:
            self._log.info("school_audit", event=event.action, context=event.organization_id)

    def events(self) -> list[SchoolAuditEvent]:
        return list(self._events)
