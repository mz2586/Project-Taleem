"""Turn a k6 JSON summary + the resource-sampler CSV into a markdown evidence summary.

    python tests/perf/summarize.py --profile soak --k6 summary.json --samples samples.csv \
        --k6-exit 0 --out summary.md

Every number printed is labelled **dev Codespace**: a shared 4-vCPU development container running
uvicorn, PostgreSQL and the load generator on one host. It is evidence of behaviour (errors, leaks,
saturation, relative cost per endpoint), not a production capacity figure.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from typing import Any

GROUPS = (
    "auth_kdf",
    "learning",
    "sync",
    "progress",
    "packages",
    "guardian_reads",
    "teacher_reads",
)
# PERF-01, docs/01-product/04-non-functional-requirements.md: p95 < 300 ms, p99 < 800 ms.
DOCUMENTED = (300.0, 800.0, "PERF-01 (documented)")
# No documented budget covers the PBKDF2 sign-in routes; this is a PROPOSAL (tests/perf/README.md).
PROPOSED_KDF = (1500.0, 3000.0, "PROPOSED (no documented budget)")
WARMUP_S = 60.0


def _metric(data: dict[str, Any], name: str) -> dict[str, Any]:
    return dict(data.get("metrics", {}).get(name, {}).get("values", {}))


def _ms(v: Any) -> str:
    return "n/a" if v is None else f"{float(v):.0f}"


def _slope_per_10min(points: list[tuple[float, float]]) -> float | None:
    if len(points) < 3:
        return None
    n = len(points)
    mx = sum(p[0] for p in points) / n
    my = sum(p[1] for p in points) / n
    den = sum((p[0] - mx) ** 2 for p in points)
    if den == 0:
        return None
    return sum((p[0] - mx) * (p[1] - my) for p in points) / den * 600.0


def _mean(values: list[float]) -> float:
    vals = [v for v in values if not math.isnan(v)]
    return sum(vals) / len(vals) if vals else float("nan")


def resources(path: str) -> dict[str, Any]:
    rows: list[dict[str, float]] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for raw in csv.DictReader(fh):
                rows.append({k: float(v) if v != "" else float("nan") for k, v in raw.items()})
    except FileNotFoundError:
        return {}
    if not rows:
        return {}
    steady = [r for r in rows if r["t_s"] >= WARMUP_S] or rows
    rss = [r["rss_mb"] for r in rows if not math.isnan(r["rss_mb"])]
    sync = [(r["t_s"], r.get("sync_mean_ms", float("nan"))) for r in steady]
    sync = [(t, v) for t, v in sync if not math.isnan(v)]
    edge = max(1, len(sync) // 5)  # first vs last fifth of the steady state
    first = sum(v for _, v in sync[:edge]) / edge if sync else float("nan")
    last = sum(v for _, v in sync[-edge:]) / edge if sync else float("nan")
    return {
        "samples": len(rows),
        "duration_s": rows[-1]["t_s"],
        "rss_start_mb": steady[0]["rss_mb"],
        "rss_end_mb": steady[-1]["rss_mb"],
        "rss_max_mb": max(rss) if rss else float("nan"),
        "rss_slope_mb_per_10min": _slope_per_10min([(r["t_s"], r["rss_mb"]) for r in steady]),
        "series_start": int(steady[0]["metrics_series"]),
        "series_end": int(steady[-1]["metrics_series"]),
        "pool_checked_out_max": max(r["pool_checked_out"] for r in rows),
        "pool_capacity": max(r["pool_capacity"] for r in rows),
        "pg_connections_max": int(max(r["pg_connections"] for r in rows)),
        "pg_max_connections": int(rows[0]["pg_max_connections"]),
        "api_cpu_pct_mean": _mean([r.get("api_cpu_pct", float("nan")) for r in steady]),
        "api_cpu_pct_max": max((r.get("api_cpu_pct", 0.0) for r in rows), default=0.0),
        "load1_max": max((r.get("load1", 0.0) for r in rows), default=0.0),
        "sync_mean_ms_first_fifth": first,
        "sync_mean_ms_last_fifth": last,
    }


def summarize(profile: str, data: dict[str, Any], res: dict[str, Any], k6_exit: int) -> str:
    duration_s = float(data.get("state", {}).get("testRunDurationMs", 0.0)) / 1000.0
    reqs = _metric(data, "http_reqs")
    failed = _metric(data, "http_req_failed")
    checks = _metric(data, "checks")
    lines = [
        f"### Perf `{profile}` — dev Codespace (not production hardware)",
        "",
        "Environment: GitHub Codespace, 4 vCPU / 16 GB shared with other workloads; one uvicorn "
        "worker; PostgreSQL 16 on the same host; k6 on the same host. Production security "
        "settings: PBKDF2 600 000 iterations, sign-in limiter 10 / 60 s per client (unchanged).",
        "",
        f"- duration {duration_s:.0f} s; requests {int(reqs.get('count', 0))}; "
        f"throughput {float(reqs.get('rate', 0.0)):.1f} req/s; "
        f"iterations {int(_metric(data, 'iterations').get('count', 0))}",
        f"- HTTP error rate {100 * float(failed.get('rate', 0.0)):.3f}% "
        f"(budget < 0.1%, derived from AVAIL-01 99.9% — proposal); "
        f"checks passed {100 * float(checks.get('rate', 0.0)):.3f}%",
        f"- 429 rate-limited {int(_metric(data, 'taleem_rate_limited').get('count', 0))}; "
        f"5xx {int(_metric(data, 'taleem_server_errors').get('count', 0))}; "
        f"planner had nothing new (mastered) "
        f"{int(_metric(data, 'taleem_planner_nothing_to_learn').get('count', 0))}",
        f"- k6 threshold exit code {k6_exit} (0 = every budget threshold met; 99 = at least one missed)",
        "",
        "| Endpoint group | Requests | p50 ms | p95 ms | p99 ms | max ms | Errors | Budget p95/p99 | Verdict |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for g in GROUPS:
        d = _metric(data, f"http_req_duration{{grp:{g}}}")
        if not d or not d.get("count"):
            continue
        e = _metric(data, f"http_req_failed{{grp:{g}}}")
        p95, p99, source = PROPOSED_KDF if g == "auth_kdf" else DOCUMENTED
        met = float(d.get("p(95)", 0)) < p95 and float(d.get("p(99)", 0)) < p99
        lines.append(
            f"| {g} | {int(d.get('count', 0))} | {_ms(d.get('med'))} | {_ms(d.get('p(95)'))} | "
            f"{_ms(d.get('p(99)'))} | {_ms(d.get('max'))} | "
            f"{100 * float(e.get('rate', 0.0)):.2f}% | {p95:.0f}/{p99:.0f} {source} | "
            f"{'met' if met else 'MISSED'} |"
        )
    if res:
        slope = res["rss_slope_mb_per_10min"]
        lines += [
            "",
            f"Resources (sampled every 5 s, {res['samples']} samples; steady state after "
            f"{WARMUP_S:.0f} s):",
            "",
            f"- uvicorn RSS {res['rss_start_mb']:.1f} MB -> {res['rss_end_mb']:.1f} MB "
            f"(max {res['rss_max_mb']:.1f} MB); linear trend "
            f"{'n/a' if slope is None else f'{slope:+.2f} MB per 10 min'}",
            f"- /metrics series {res['series_start']} -> {res['series_end']}",
            f"- SQLAlchemy pools checked out: max {res['pool_checked_out_max']:.0f} of "
            f"{res['pool_capacity']:.0f} capacity",
            f"- PostgreSQL connections to this database: max {res['pg_connections_max']} "
            f"(server max_connections {res['pg_max_connections']})",
            f"- uvicorn CPU: mean {res['api_cpu_pct_mean']:.0f}% / max {res['api_cpu_pct_max']:.0f}% "
            f"of one core (one worker); host load average max {res['load1_max']:.1f} on 4 vCPU",
            f"- /v1/sync/batch mean server time: first fifth of steady state "
            f"{res['sync_mean_ms_first_fifth']:.1f} ms, last fifth "
            f"{res['sync_mean_ms_last_fifth']:.1f} ms (drift check as evidence accumulates)",
        ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="summarize a tests/perf run")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--k6", required=True)
    parser.add_argument("--samples", required=True)
    parser.add_argument("--k6-exit", type=int, default=0)
    parser.add_argument("--out", required=True)
    parser.add_argument("--json-out")
    args = parser.parse_args(argv)
    with open(args.k6, encoding="utf-8") as fh:
        data = json.load(fh)
    res = resources(args.samples)
    text = summarize(args.profile, data, res, args.k6_exit)
    with open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump({"profile": args.profile, "resources": res, "k6_exit": args.k6_exit}, fh)
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
