"""Minimal metrics registry (pure-stdlib) with Prometheus text exposition.

Golden-signal instrumentation (docs/38-monitoring.md OBS-02). In production this is backed by
prometheus_client / OpenTelemetry; this stdlib registry keeps the domain testable and the
exposition format compatible.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field


def _fmt_labels(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{k}="{v}"' for k, v in sorted(labels.items()))
    return "{" + inner + "}"


@dataclass
class Registry:
    _counters: dict[tuple[str, tuple[tuple[str, str], ...]], float] = field(default_factory=dict)
    _hist_sums: dict[tuple[str, tuple[tuple[str, str], ...]], float] = field(default_factory=dict)
    _hist_counts: dict[tuple[str, tuple[tuple[str, str], ...]], int] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def inc(self, name: str, value: float = 1.0, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._counters[key] = self._counters.get(key, 0.0) + value

    def observe(self, name: str, value: float, **labels: str) -> None:
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._hist_sums[key] = self._hist_sums.get(key, 0.0) + value
            self._hist_counts[key] = self._hist_counts.get(key, 0) + 1

    def counter_value(self, name: str, **labels: str) -> float:
        return self._counters.get((name, tuple(sorted(labels.items()))), 0.0)

    def render(self) -> str:
        """Render Prometheus text exposition format."""
        lines: list[str] = []
        for (name, labels), val in sorted(self._counters.items()):
            lines.append(f"{name}{_fmt_labels(dict(labels))} {val}")
        for (name, labels), s in sorted(self._hist_sums.items()):
            lbl = _fmt_labels(dict(labels))
            lines.append(f"{name}_sum{lbl} {s}")
            lines.append(f"{name}_count{lbl} {self._hist_counts.get((name, labels), 0)}")
        return "\n".join(lines) + "\n"


_REGISTRY = Registry()


def registry() -> Registry:
    return _REGISTRY
