"""Lightweight observability helpers for application services (CTO H9).

Context code (services/repositories) previously emitted no telemetry — only the HTTP middleware did.
These helpers let application services record domain metrics and correlation-tagged structured logs
without each service re-plumbing the logger/registry. Correlation is read from the request-scoped
context variable set by the HTTP edge, so business events are tied to the originating request.

The HTTP and saturation helpers at the bottom feed the alert rules in
``infra/monitoring/alerts.yml``; keep their series names and labels stable.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .correlation import get_correlation_id
from .logging import StructuredLogger
from .metrics import registry

_log = StructuredLogger("taleem.domain", "INFO")

UNMATCHED_ROUTE = "<unmatched>"
HALTED_ROUTE = "<halted>"


def record_event(name: str, **labels: str) -> None:
    """Increment a domain metric counter (golden-signal instrumentation)."""
    registry().inc(name, 1.0, **labels)


def log_event(message: str, **fields: object) -> None:
    """Emit a structured log line tagged with the current correlation id (if any)."""
    cid = get_correlation_id()
    if cid is not None:
        fields = {"correlation_id": cid, **fields}
    _log.info(message, **fields)


def route_label(scope: Mapping[str, Any]) -> str:
    """The matched route *template* (``/v1/learning/sessions/{session_id}:answer``), never the raw
    path. A raw path carries ids, so labelling by it grows one series per session and learner for
    the life of the process. Unrouted requests (404s, scanners) share one label."""
    template = getattr(scope.get("route"), "path", None)
    return template if isinstance(template, str) and template else UNMATCHED_ROUTE


def record_problem(status: int, code: str) -> None:
    """Count a Problem Details response by status and stable app code (bounded: codes are
    constants). The consent-refusal alert reads ``code="CONSENT_REQUIRED"`` from this series."""
    registry().inc("taleem_problem_responses_total", status=str(status), code=code)


def record_db_pool(pool_name: str, engine: Any) -> None:
    """Publish a SQLAlchemy ``QueuePool``'s usage as gauges ``taleem_db_pool_checked_out`` and
    ``taleem_db_pool_capacity`` (``size + max_overflow``), labelled ``pool``.

    Pools without a fixed capacity (SQLite's ``StaticPool`` in dev and tests) publish nothing.
    """
    pool = getattr(engine, "pool", None)
    size = getattr(pool, "size", None)
    checked_out = getattr(pool, "checkedout", None)
    max_overflow = getattr(pool, "_max_overflow", None)
    if not (callable(size) and callable(checked_out) and isinstance(max_overflow, int)):
        return
    capacity = size() + max(0, max_overflow)
    registry().set_gauge("taleem_db_pool_checked_out", float(checked_out()), pool=pool_name)
    registry().set_gauge("taleem_db_pool_capacity", float(capacity), pool=pool_name)
