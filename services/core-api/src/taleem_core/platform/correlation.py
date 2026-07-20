"""Request correlation / trace propagation (pure-stdlib).

A correlation id is attached to every request and threaded through logs, metrics, and
error responses (docs/39-logging.md OBS-01, docs/10-api-design.md §4 traceId).
"""

from __future__ import annotations

import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def ensure_correlation_id(incoming: str | None) -> str:
    """Use an incoming id if present and sane, else mint a new one; bind it to the context."""
    value = incoming.strip() if incoming and incoming.strip() else new_correlation_id()
    # Defensive: cap length to avoid log-injection of huge ids.
    value = value[:128]
    set_correlation_id(value)
    return value
