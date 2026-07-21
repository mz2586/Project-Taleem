"""Lightweight observability helpers for application services (CTO H9).

Context code (services/repositories) previously emitted no telemetry — only the HTTP middleware did.
These helpers let application services record domain metrics and correlation-tagged structured logs
without each service re-plumbing the logger/registry. Correlation is read from the request-scoped
context variable set by the HTTP edge, so business events are tied to the originating request.
"""

from __future__ import annotations

from .correlation import get_correlation_id
from .logging import StructuredLogger
from .metrics import registry

_log = StructuredLogger("taleem.domain", "INFO")


def record_event(name: str, **labels: str) -> None:
    """Increment a domain metric counter (golden-signal instrumentation)."""
    registry().inc(name, 1.0, **labels)


def log_event(message: str, **fields: object) -> None:
    """Emit a structured log line tagged with the current correlation id (if any)."""
    cid = get_correlation_id()
    if cid is not None:
        fields = {"correlation_id": cid, **fields}
    _log.info(message, **fields)
