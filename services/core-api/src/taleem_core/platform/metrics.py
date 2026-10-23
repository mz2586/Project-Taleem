"""Minimal metrics registry (pure-stdlib) with Prometheus text exposition.

Golden-signal instrumentation (docs/38-monitoring.md OBS-02). In production this is backed by
prometheus_client / OpenTelemetry; this stdlib registry keeps the domain testable and the
exposition format compatible.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

# Latency buckets (seconds) for ``observe_histogram``. 0.3 and 0.8 are the PERF-01 p95/p99 budgets
# (docs/01-product/04-non-functional-requirements.md), so a budget alert reads an exact bucket edge.
LATENCY_BUCKETS_SECONDS: tuple[float, ...] = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.1,
    0.25,
    0.3,
    0.5,
    0.8,
    1.0,
    2.5,
    5.0,
    10.0,
)


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
    _gauges: dict[tuple[str, tuple[tuple[str, str], ...]], float] = field(default_factory=dict)
    # Bucketed histograms: (name, labels) -> per-bucket counts (cumulative at render), sum, count.
    _buckets: dict[tuple[str, tuple[tuple[str, str], ...]], tuple[tuple[float, ...], list[int]]] = (
        field(default_factory=dict)
    )
    _bucket_sums: dict[tuple[str, tuple[tuple[str, str], ...]], float] = field(default_factory=dict)
    _bucket_counts: dict[tuple[str, tuple[tuple[str, str], ...]], int] = field(default_factory=dict)
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

    def set_gauge(self, name: str, value: float, **labels: str) -> None:
        """Set a gauge to its current value (e.g. pool connections in use, kill switch engaged)."""
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            self._gauges[key] = value

    def gauge_value(self, name: str, **labels: str) -> float | None:
        return self._gauges.get((name, tuple(sorted(labels.items()))))

    def observe_histogram(
        self,
        name: str,
        value: float,
        buckets: tuple[float, ...] = LATENCY_BUCKETS_SECONDS,
        **labels: str,
    ) -> None:
        """Record ``value`` into a Prometheus-style bucketed histogram (``_bucket{le}``/``_sum``/
        ``_count``), so p95/p99 can be computed with ``histogram_quantile``. Keep labels bounded."""
        key = (name, tuple(sorted(labels.items())))
        with self._lock:
            edges, counts = self._buckets.setdefault(key, (buckets, [0] * len(buckets)))
            for i, edge in enumerate(edges):
                if value <= edge:
                    counts[i] += 1
                    break
            self._bucket_sums[key] = self._bucket_sums.get(key, 0.0) + value
            self._bucket_counts[key] = self._bucket_counts.get(key, 0) + 1

    def series_count(self) -> int:
        """How many label sets the registry holds (a cardinality guard for tests)."""
        with self._lock:
            return (
                len(self._counters) + len(self._hist_sums) + len(self._gauges) + len(self._buckets)
            )

    def counter_value(self, name: str, **labels: str) -> float:
        return self._counters.get((name, tuple(sorted(labels.items()))), 0.0)

    def total(self, name: str) -> float:
        """Sum a counter across every label set (e.g. requests across all method/path labels)."""
        with self._lock:
            return sum(v for (n, _), v in self._counters.items() if n == name)

    def observed_mean(self, name: str) -> float:
        """Mean of an observed histogram across every label set (0.0 if never observed)."""
        with self._lock:
            s = sum(v for (n, _), v in self._hist_sums.items() if n == name)
            c = sum(cc for (n, _), cc in self._hist_counts.items() if n == name)
        return s / c if c else 0.0

    def render(self) -> str:
        """Render Prometheus text exposition format.

        Every map is snapshotted under the lock first: request threads keep writing while a scrape
        renders, and iterating a dict that another thread is growing can raise.
        """
        with self._lock:
            counters = sorted(self._counters.items())
            hist = sorted(self._hist_sums.items())
            hist_counts = dict(self._hist_counts)
            gauges = sorted(self._gauges.items())
            buckets = sorted((k, (e, list(c))) for k, (e, c) in self._buckets.items())
            sums, counts = dict(self._bucket_sums), dict(self._bucket_counts)
        lines: list[str] = []
        for (name, labels), val in counters:
            lines.append(f"{name}{_fmt_labels(dict(labels))} {val}")
        for (name, labels), total_ms in hist:
            lbl = _fmt_labels(dict(labels))
            lines.append(f"{name}_sum{lbl} {total_ms}")
            lines.append(f"{name}_count{lbl} {hist_counts.get((name, labels), 0)}")
        for (name, labels), val in gauges:
            lines.append(f"{name}{_fmt_labels(dict(labels))} {val}")
        for (name, labels), (edges, per_bucket) in buckets:
            base = dict(labels)
            running = 0
            for edge, n in zip(edges, per_bucket, strict=True):
                running += n
                lines.append(f"{name}_bucket{_fmt_labels({**base, 'le': repr(edge)})} {running}")
            observed = counts.get((name, labels), 0)
            lines.append(f"{name}_bucket{_fmt_labels({**base, 'le': '+Inf'})} {observed}")
            lines.append(f"{name}_sum{_fmt_labels(base)} {sums.get((name, labels), 0.0)}")
            lines.append(f"{name}_count{_fmt_labels(base)} {observed}")
        return "\n".join(lines) + "\n"


_REGISTRY = Registry()


def registry() -> Registry:
    return _REGISTRY
