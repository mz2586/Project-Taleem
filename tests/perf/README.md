# Performance tests: load, soak, spike

k6 scenarios against a **real** Core API: uvicorn backed by PostgreSQL 16, synthetic data only.
This is the engineering evidence for master-scope blocker #14 (load, soak, spike). It is not a
production capacity figure: there is no verified live environment, and **every number below comes
from a dev Codespace**.

## Running

```sh
make perf-load    # ramp learners 0 -> 60 over 2 min, hold 3 min, ramp down (plus 5 guardians, 3 teachers)
make perf-soak    # 10 learners steady for 12 min (plus 3 guardians, 2 teachers): leak check
make perf-spike   # 5 learners, sudden 10x burst to 50 in 10 s, hold 1 min, back to 5
```

Each target runs [`run.sh`](run.sh), which needs `TALEEM_DATABASE_URL` (or `CS_DATABASE_URL`)
pointing at a **disposable** PostgreSQL database and refuses `TALEEM_ENV=production`. It:

1. migrates the database and publishes the synthetic fixture lesson
   (`E2E-SYNTHETIC-FIXTURE-fractions`, the same one `make e2e` uses);
2. starts uvicorn through [`scripts/e2e/api_server.sh`](../../scripts/e2e/api_server.sh) (one
   worker, port `PERF_PORT`, default 8790);
3. seeds synthetic families and teachers through the public API with [`seed.py`](seed.py)
   (guardian registers, enrols a learner, grants consent, joins a class; an operator creates the
   school, teachers, classes and an assignment). Setup is not timed;
4. samples the uvicorn process (RSS, CPU), `/metrics` (series count, DB pool gauges, sync latency)
   and `pg_stat_activity` every 5 s with [`sampler.py`](sampler.py);
5. runs [`k6/taleem.js`](k6/taleem.js) and writes a markdown summary with
   [`summarize.py`](summarize.py).

Output goes to `PERF_OUT_DIR` (default `/tmp/taleem-perf/<profile>-<timestamp>`): `summary.md`,
`k6-summary.json`, `samples.csv`, `api.log`, and `seed.json`. **`seed.json` holds the synthetic
credentials**; delete it after review (the workflow deletes it before upload).

k6 is taken from `K6`, else `PATH`, else the pinned release `v1.0.0` is downloaded to `/tmp` and
checked against its sha256. Nothing is installed system-wide. The GitHub Actions workflow
[`perf.yml`](../../.github/workflows/perf.yml) is **manual only** (`workflow_dispatch`): these runs
are slow and noisy and never run on push.

| Variable | Default | Effect |
| --- | --- | --- |
| `PERF_LOAD_VUS` / `PERF_LOAD_RAMP_S` / `PERF_LOAD_HOLD_S` | 60 / 120 / 180 | Load shape |
| `PERF_SOAK_VUS` / `PERF_SOAK_DURATION` | 10 / `12m` | Soak shape |
| `PERF_SPIKE_BASE_VUS` | 5 | Spike base (the burst is 10x) |
| `PERF_FAMILIES` | 110 | Synthetic families seeded (must cover every VU) |
| `PERF_ACCURACY` | 0.6 | Share of answers a learner gets right |
| `PERF_ENFORCE` | 0 | `1` makes a missed budget fail the run (k6 exit 99) |

## What a virtual user does

- **Learner day** (one family per VU): sign in with family code + name + PIN → list offline
  packages → start a session → planner `:next` → `:teach` the fixture objective → answer each
  practice item (0.5-1.5 s think time) → `:end` → upload an offline batch of attempts to
  `/v1/sync/batch` (3 attempts, or 10 when the planner had nothing new) → read own progress. Each
  day takes at least 12 s.
- **Guardian**: sign in once, then read the dashboard, learner list, consent state and the child's
  classes, every ~5 s.
- **Teacher**: sign in once, then read class list, class detail and assignment progress, every ~5 s.

The fixture is a single lesson, so a learner who masters it gets "nothing new" from the planner on
later days; that day's practice then arrives through sync instead. The summary counts these days.

## Security controls were not lowered

- PBKDF2-SHA256 stays at **600 000 iterations** (`MIN_KDF_ITERATIONS`; config refuses less).
- The shared sign-in limiter stays at **10 attempts per client per 60 s**.
- Each VU presents its own address from the RFC 5737 documentation ranges as `X-Real-IP`, and the
  server trusts that header (`TALEEM_CLIENT_IP_HEADER=x-real-ip`), as a Vercel deployment does.
  Learner days are paced to at most 5 sign-ins per minute per address, so every run reports 429s
  and expects **0**. Because the limiter persists in PostgreSQL, `run.sh` waits two windows after a
  previous run instead of loosening it.

Every scenario therefore ran with production-like security settings; no test-only setting exists.

## Budgets

| Budget | Source |
| --- | --- |
| API p95 < 300 ms, p99 < 800 ms (excl. AI calls) | **Documented**: PERF-01, [docs/01-product/04-non-functional-requirements.md](../../docs/01-product/04-non-functional-requirements.md) |
| Sign-in (PBKDF2 routes) p95 < 1.5 s, p99 < 3 s | **Proposal**. No document covers credential routes; at 600 000 iterations one verification is ~0.2-0.4 s of CPU even when idle. |
| HTTP error rate < 0.1% | **Proposal**, derived from AVAIL-01 (99.9% availability). |
| 0 rate-limited (429) responses | Harness correctness (pacing above). |
| Soak: flat `/metrics` series, RSS trend < 5 MB per 10 min after warm-up | **Proposal** for the leak check. |

## Results — dev Codespace, 2026-10-23

Environment for every row: GitHub Codespace, 4 vCPU / 16 GB, **shared with other agents' work**
(host load average up to 5.4); one uvicorn worker; PostgreSQL 16 and k6 on the same host;
production security settings. Latencies are client-observed (k6) in ms.

### Load: 0 → 60 learners (+5 guardians, +3 teachers), 5 min 39 s

4 577 requests, 13.5 req/s, 0 errors, 0 × 429, 0 × 5xx. uvicorn CPU mean 147% of one core.

| Group | p50 | p95 | p99 | Budget p95/p99 | Verdict |
| --- | ---: | ---: | ---: | --- | --- |
| auth_kdf | 2 514 | 4 984 | 6 333 | 1 500/3 000 (proposal) | missed |
| learning | 2 807 | 6 494 | 7 901 | 300/800 (PERF-01) | missed |
| sync | 6 357 | 11 792 | 12 730 | 300/800 | missed |
| progress | 2 884 | 6 310 | 7 868 | 300/800 | missed |
| packages | 4 008 | 7 322 | 8 667 | 300/800 | missed |
| guardian_reads | 1 761 | 4 841 | 6 138 | 300/800 | missed |
| teacher_reads | 8 522 | 18 486 | 19 859 | 300/800 | missed |

DB: pools max 32 of 60 checked out; PostgreSQL connections max 40 of 100.

### Soak: 10 learners (+3 guardians, +2 teachers) for 12 min

6 309 requests, 8.7 req/s, 0 errors, 0 × 429, 0 × 5xx. uvicorn CPU mean 90% of one core.

| Group | p50 | p95 | p99 | Budget p95/p99 | Verdict |
| --- | ---: | ---: | ---: | --- | --- |
| auth_kdf | 315 | 1 084 | 1 535 | 1 500/3 000 (proposal) | met |
| learning | 262 | 945 | 1 177 | 300/800 (PERF-01) | missed |
| sync | 2 262 | 3 004 | 3 252 | 300/800 | missed |
| progress | 28 | 365 | 465 | 300/800 | missed (p95) |
| packages | 751 | 1 411 | 2 089 | 300/800 | missed |
| guardian_reads | 51 | 800 | 1 332 | 300/800 | missed |
| teacher_reads | 496 | 5 536 | 6 823 | 300/800 | missed |

Leak check: `/metrics` series **546 → 546** (flat); RSS 106.3 → 115.0 MB, trend **+6.9 MB per
10 min** (just over the 5 MB proposal; see findings). DB: pools max 13 of 60; PostgreSQL connections
max 24 of 100. Sync mean server time 1 451 ms in the first fifth of the steady state, 2 259 ms in the
last fifth.

### Spike: 5 → 50 learners in 10 s, hold 1 min, back to 5 (+2 guardians, +2 teachers)

1 983 requests, 9.6 req/s, 0 errors, 0 × 429, 0 × 5xx. No request failed during the burst; latency
absorbed it (queueing), and sync time dropped back to ~430 ms once the burst drained.

| Group | p50 | p95 | p99 | Budget p95/p99 | Verdict |
| --- | ---: | ---: | ---: | --- | --- |
| auth_kdf | 1 709 | 4 409 | 5 118 | 1 500/3 000 (proposal) | missed |
| learning | 1 576 | 4 926 | 6 543 | 300/800 (PERF-01) | missed |
| sync | 2 808 | 9 495 | 9 922 | 300/800 | missed |
| progress | 1 024 | 5 016 | 5 724 | 300/800 | missed |
| packages | 2 929 | 6 431 | 6 679 | 300/800 | missed |
| guardian_reads | 27 | 2 845 | 4 756 | 300/800 | missed |
| teacher_reads | 380 | 11 208 | 13 208 | 300/800 | missed |

DB: pools max 31 of 60; PostgreSQL connections max 35 of 100.

### Light load reference: 3 learners (+5 guardians, +3 teachers), 2 min

Every group met its budget: learning p95 50 ms, sync 101 ms, progress 11 ms, packages 237 ms,
guardian reads 86 ms, teacher reads 138 ms, sign-in 788 ms. This was a shorter smoke run of the same
harness (3-attempt sync batches), recorded to show the budgets hold when the process is not
saturated.

## Findings

1. **Fixed: unbounded metric cardinality (a memory leak).** Request metrics were labelled by the raw
   URL path, which carries session and learner ids, so every new session added series for the life
   of the process. A 5-minute soak of the code before the fix (10 learners) grew `/metrics` from 523
   to 1 740 series with an RSS trend of +18.5 MB per 10 min. With route-template labels the 12-minute
   soak stayed at 546 series and +6.9 MB per 10 min. The residual growth is unexplained after 12
   minutes; a multi-hour soak is needed before calling the process leak-free.
2. **One uvicorn worker saturates at roughly 9-14 req/s of this mix**, about 10 concurrent learners.
   uvicorn CPU sat at 85-150% of one core: pure-Python work is GIL-bound, so a single process cannot
   use the 4 vCPU. Above that point latency grows by queueing while errors stay at 0. Capacity has
   to come from more processes or instances (`--workers`, more replicas, or serverless
   concurrency), and the budgets must be re-measured on the chosen hosting.
3. **Offline sync is the most expensive call and slows as evidence accumulates.**
   `SyncEvidenceConsumer` loads a learner's whole knowledge aggregate, including every recorded
   evidence row, and saves it again, once per delta. Its cost therefore grows with a learner's
   lifetime attempts: in the soak, mean sync time rose from 1.45 s to 2.26 s over 12 minutes at
   constant load. This needs a fix in the learning context (an indexed evidence-id lookup and one
   aggregate load per batch) before real learners accumulate months of history.
4. **`GET /v1/offline/packages` costs ~220-250 ms even at light load** with one published lesson.
   `OfflinePackageService.list_packages` rebuilds and Ed25519-signs every manifest on every call,
   so the cost grows with the catalogue. Caching signed manifests per lesson version would remove it.
5. **Teacher class reads are the slowest reads under load** (p95 5.5 s in the soak).
   They aggregate progress across every learner in the class. The query pattern needs a profile
   before classes reach real sizes.
6. **The kill-switch check reads the database on every request**, `/health` and `/metrics` included,
   because `kill_switch.engaged` is evaluated before `is_child_facing(path)` in the HTTP
   middleware. Swapping the two operands would take one query off every non-child-facing request.
   Not changed here, because the middleware ordering belongs to the ops context.

Budget summary: the documented PERF-01 budget (p95 < 300 ms) is **met only below saturation** (the
light-load run) and **missed in every load, soak and spike run** on this one-worker dev Codespace.
Error-rate and rate-limit budgets were met in every run (0 errors, 0 × 429, 0 × 5xx).
