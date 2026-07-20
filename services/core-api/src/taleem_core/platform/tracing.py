"""Distributed-tracing abstraction (pure-stdlib no-op + OTel hook point).

Provides a `span` context manager with a stable API so application code is instrumented once;
the real backend is OpenTelemetry (docs/38-monitoring.md OBS-03). The no-op keeps the domain
testable and the service runnable without a collector.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from dataclasses import dataclass, field

from .correlation import get_correlation_id
from .metrics import registry


@dataclass
class Span:
    name: str
    start: float
    attributes: dict[str, str] = field(default_factory=dict)
    trace_id: str | None = None

    def set(self, key: str, value: str) -> None:
        self.attributes[key] = value


@contextlib.contextmanager
def span(name: str, **attributes: str) -> Iterator[Span]:
    s = Span(name=name, start=time.perf_counter(), attributes=dict(attributes),
             trace_id=get_correlation_id())
    try:
        yield s
    finally:
        duration_ms = (time.perf_counter() - s.start) * 1000.0
        registry().observe("taleem_span_duration_ms", duration_ms, span=name)
