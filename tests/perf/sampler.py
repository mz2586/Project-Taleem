"""Sample server-side resource usage while a k6 run is in progress (dev Codespace evidence).

Every ``--interval`` seconds, appends one CSV row:

    t_s, rss_mb, metrics_series, pool_checked_out, pool_capacity, pg_connections, pg_max_connections

* ``rss_mb``           uvicorn process resident set size, from /proc/<pid>/status (Linux) — the
                       leak check over a soak.
* ``metrics_series``   lines in GET /metrics — the metric-cardinality check (a registry that grows
                       with traffic is a memory leak by another name).
* ``pool_*``           sum of ``taleem_db_pool_checked_out`` / ``taleem_db_pool_capacity`` over the
                       API's SQLAlchemy pools (the gauges the saturation alert reads).
* ``pg_connections``   rows in pg_stat_activity for this database (every client, not just the API).
* ``sync_mean_ms``     mean /v1/sync/batch server time over the interval (from the cumulative
                       ``taleem_request_duration_ms`` sum/count) — shows drift as evidence grows.
* ``api_cpu_pct``      uvicorn process CPU over the interval (100 = one core; the GIL caps pure
                       Python work near 100 for a single worker).
* ``load1``            host 1-minute load average (the Codespace is shared; context for outliers).

Runs until killed (run.sh stops it). Read-only against the API and the database.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import time
from pathlib import Path

import httpx
import psycopg

_GAUGE = re.compile(r'^(taleem_db_pool_checked_out|taleem_db_pool_capacity)\{[^}]*\} ([0-9.]+)$')
_SYNC = re.compile(r'^taleem_request_duration_ms_(sum|count)\{path="/v1/sync/batch"\} ([0-9.e+]+)$')


def rss_mb(pid: int) -> float:
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if line.startswith("VmRSS:"):
            return int(line.split()[1]) / 1024.0
    return float("nan")


def cpu_seconds(pid: int) -> float:
    fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")


def load1() -> float:
    return float(Path("/proc/loadavg").read_text().split()[0])


def libpq_url(url: str) -> str:
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def main() -> int:
    parser = argparse.ArgumentParser(description="resource sampler for tests/perf")
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--interval", type=float, default=5.0)
    args = parser.parse_args()
    db = libpq_url(os.environ["TALEEM_DATABASE_URL"])
    started = time.monotonic()
    with (
        open(args.out, "w", newline="", encoding="utf-8") as fh,
        httpx.Client(base_url=args.base_url, timeout=10.0) as client,
        psycopg.connect(db, autocommit=True) as conn,
    ):
        writer = csv.writer(fh)
        writer.writerow(
            ["t_s", "rss_mb", "metrics_series", "pool_checked_out", "pool_capacity",
             "pg_connections", "pg_max_connections", "sync_mean_ms", "api_cpu_pct", "load1"]
        )
        max_conn = int(conn.execute("SHOW max_connections").fetchone()[0])  # type: ignore[index]
        prev_sum = prev_count = 0.0
        prev_cpu, prev_t = cpu_seconds(args.pid), time.monotonic()
        while True:
            try:
                text = client.get("/metrics").text
                lines = [ln for ln in text.splitlines() if ln and not ln.startswith("#")]
                used = cap = 0.0
                sync_sum = sync_count = 0.0
                for ln in lines:
                    sm = _SYNC.match(ln)
                    if sm:
                        if sm.group(1) == "sum":
                            sync_sum = float(sm.group(2))
                        else:
                            sync_count = float(sm.group(2))
                    m = _GAUGE.match(ln)
                    if m:
                        if m.group(1).endswith("checked_out"):
                            used += float(m.group(2))
                        else:
                            cap += float(m.group(2))
                pg = conn.execute(
                    "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
                ).fetchone()[0]  # type: ignore[index]
                done = sync_count - prev_count
                sync_mean = round((sync_sum - prev_sum) / done, 1) if done > 0 else ""
                prev_sum, prev_count = sync_sum, sync_count
                cpu, now = cpu_seconds(args.pid), time.monotonic()
                cpu_pct = round(100.0 * (cpu - prev_cpu) / max(now - prev_t, 1e-6), 1)
                prev_cpu, prev_t = cpu, now
                writer.writerow(
                    [round(time.monotonic() - started, 1), round(rss_mb(args.pid), 1), len(lines),
                     used, cap, pg, max_conn, sync_mean, cpu_pct, load1()]
                )
                fh.flush()
            except (httpx.HTTPError, OSError, psycopg.Error):
                pass  # a missed sample is not a failed run; gaps show in the CSV
            time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
