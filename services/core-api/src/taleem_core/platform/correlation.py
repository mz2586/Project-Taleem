"""Request correlation / trace propagation (pure-stdlib).

A correlation id is attached to every request and threaded through logs, metrics, and
error responses (docs/39-logging.md OBS-01, docs/10-api-design.md §4 traceId).
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# A correlation id is echoed into a response header and into structured logs, so a client-supplied
# id must be constrained to a safe, printable set — no CR/LF (HTTP response splitting / log
# injection), no control chars. Anything outside this alphabet means we mint our own id instead.
_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def new_correlation_id() -> str:
    return uuid.uuid4().hex


def set_correlation_id(value: str) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def ensure_correlation_id(incoming: str | None) -> str:
    """Use an incoming id only if it is safe (printable, no CR/LF/control chars, <=128); else mint
    a new one. Prevents response-header injection and log injection from a hostile client header."""
    candidate = incoming.strip() if incoming else ""
    value = candidate if _SAFE_CORRELATION_ID.match(candidate) else new_correlation_id()
    set_correlation_id(value)
    return value
