"""Metric emissions that the alert rules in ``infra/monitoring/alerts.yml`` depend on.

Each test pins one series an alert reads, so a rename here breaks a test before it silently breaks
an alert: bucketed latency (p95/p99 budget), route-template labels (bounded cardinality — raw paths
grew one series per session id), Problem codes (consent-refusal spike), sync outcomes (rejection
spike), the kill-switch gauge, DB pool saturation gauges, and 5xx counting for unhandled errors.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.main import create_app
from taleem_core.platform import metrics as metrics_module
from taleem_core.platform import observability as obs
from taleem_core.platform.config import Settings
from taleem_core.platform.ids import uuid7
from taleem_core.platform.metrics import LATENCY_BUCKETS_SECONDS, Registry, registry
from tests.test_sync_evidence import _attempt_delta, _publish_fractions

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)


def _h(role: str, sub: str) -> dict[str, str]:
    token = sign_hs256({"sub": sub, "role": role, "exp": int(time.time()) + 3600}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    # The registry is process-global; these tests deliberately emit 5xx and refusals, so give each
    # its own registry instead of leaking counts into other tests' golden-signal assertions.
    monkeypatch.setattr(metrics_module, "_REGISTRY", Registry())


def _app():  # type: ignore[no-untyped-def]
    return create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))


# ----------------------------------------------------------------------------- registry


def test_bucketed_histogram_renders_cumulative_buckets() -> None:
    r = Registry()
    for v in (0.004, 0.2, 0.2, 0.9, 42.0):
        r.observe_histogram("lat_seconds", v, route="/x")
    text = r.render()
    assert 'lat_seconds_bucket{le="0.005",route="/x"} 1' in text
    assert 'lat_seconds_bucket{le="0.25",route="/x"} 3' in text
    assert 'lat_seconds_bucket{le="0.8",route="/x"} 3' in text
    assert 'lat_seconds_bucket{le="1.0",route="/x"} 4' in text
    assert 'lat_seconds_bucket{le="10.0",route="/x"} 4' in text  # 42 s only lands in +Inf
    assert 'lat_seconds_bucket{le="+Inf",route="/x"} 5' in text
    assert 'lat_seconds_count{route="/x"} 5' in text
    assert 0.3 in LATENCY_BUCKETS_SECONDS and 0.8 in LATENCY_BUCKETS_SECONDS  # PERF-01 edges


def test_gauge_is_set_not_summed() -> None:
    r = Registry()
    r.set_gauge("g", 3.0, pool="a")
    r.set_gauge("g", 1.0, pool="a")
    assert r.gauge_value("g", pool="a") == 1.0
    assert r.gauge_value("g", pool="missing") is None
    assert 'g{pool="a"} 1.0' in r.render()
    assert r.series_count() == 1


def test_db_pool_gauges_for_a_queue_pool_only(tmp_path: Path) -> None:
    queue_engine = create_engine(f"sqlite:///{tmp_path / 'pool.db'}")  # QueuePool: 5 + 10 overflow
    with queue_engine.connect():
        obs.record_db_pool("test_queue", queue_engine)
        assert registry().gauge_value("taleem_db_pool_checked_out", pool="test_queue") == 1.0
    assert registry().gauge_value("taleem_db_pool_capacity", pool="test_queue") == 15.0
    obs.record_db_pool("test_queue", queue_engine)
    assert registry().gauge_value("taleem_db_pool_checked_out", pool="test_queue") == 0.0
    queue_engine.dispose()

    static_engine = create_engine("sqlite://")  # in-memory -> SingletonThreadPool, no capacity
    obs.record_db_pool("test_static", static_engine)
    assert registry().gauge_value("taleem_db_pool_capacity", pool="test_static") is None


# ----------------------------------------------------------------------------- HTTP edge


def test_requests_are_labelled_by_route_template_not_raw_path() -> None:
    c = TestClient(_app())
    guardian = _h("guardian", "g-template")
    raw = [f"stu-template-{uuid7()}" for _ in range(3)]
    for ref in raw:
        c.get(f"/v1/guardian/children/{ref}", headers=guardian)
    c.get(f"/no-such-route-{uuid7()}")
    text = c.get("/metrics").text
    assert not any(ref in text for ref in raw)  # no id ever becomes a label value
    template = "/v1/guardian/children/{student_ref}"
    assert f'path="{template}"' in text
    assert f'route="{template}"' in text  # bucketed twin
    assert 'path="<unmatched>"' in text
    assert "taleem_http_request_duration_seconds_bucket" in text


def test_series_do_not_grow_with_distinct_ids() -> None:
    c = TestClient(_app())
    guardian = _h("guardian", "g-growth")
    c.get(f"/v1/guardian/children/{uuid7()}", headers=guardian)
    before = registry().series_count()
    for _ in range(25):
        c.get(f"/v1/guardian/children/{uuid7()}", headers=guardian)
    assert registry().series_count() == before


def test_consent_refusal_is_counted_by_problem_code() -> None:
    c = TestClient(_app())
    reg = c.post(
        "/v1/identity/guardians",
        json={
            "email": f"m-{uuid7()}@example.invalid",
            "passphrase": _PASSPHRASE,
            "displayName": "Synthetic",
        },
    )
    assert reg.status_code == 201, reg.text
    guardian = {"Authorization": f"Bearer {reg.json()['session']['access_token']}"}
    learner = c.post(
        "/v1/identity/learners",
        json={"displayName": "Synthetic Kid", "pin": "4813", "gradeLevel": 4},
        headers=guardian,
    )
    assert learner.status_code == 201, learner.text
    key = {"status": "403", "code": "CONSENT_REQUIRED"}
    before = registry().counter_value("taleem_problem_responses_total", **key)
    signin = c.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": reg.json()["guardian"]["family_code"],
            "displayName": "Synthetic Kid",
            "pin": "4813",
        },
    )
    assert signin.status_code == 403 and signin.json()["code"] == "CONSENT_REQUIRED"

    # A refused sync batch is counted twice over: as a Problem and as a refused batch.
    refused_before = registry().counter_value(
        "taleem_sync_batches_refused_total", code="CONSENT_REQUIRED"
    )
    ref = str(learner.json()["student_ref"])
    delta = _attempt_delta(
        student=ref,
        item_ref="p1-one-of-four",
        option=0,
        client_event_id=uuid7(),
        evidence_id=uuid7(),
        client_seq=1,
    )
    sync = c.post(
        "/v1/sync/batch", json={"cursor": 0, "deltas": [delta]}, headers=_h("student", ref)
    )
    assert sync.status_code == 403
    assert registry().counter_value("taleem_problem_responses_total", **key) == before + 2
    assert (
        registry().counter_value("taleem_sync_batches_refused_total", code="CONSENT_REQUIRED")
        == refused_before + 1
    )


def test_sync_delta_outcomes_are_counted() -> None:
    app = _app()
    _publish_fractions(app)
    c = TestClient(app)
    student = "alert-metrics-stu"
    delta = _attempt_delta(
        student=student,
        item_ref="p1-one-of-four",
        option=0,
        client_event_id=uuid7(),
        evidence_id=uuid7(),
        client_seq=1,
    )
    applied = registry().counter_value("taleem_sync_deltas_total", status="applied")
    duplicate = registry().counter_value("taleem_sync_deltas_total", status="duplicate")
    for _ in range(2):  # the replay is a duplicate
        r = c.post(
            "/v1/sync/batch", json={"cursor": 0, "deltas": [delta]}, headers=_h("student", student)
        )
        assert r.status_code == 200, r.text
    assert registry().counter_value("taleem_sync_deltas_total", status="applied") == applied + 1
    assert registry().counter_value("taleem_sync_deltas_total", status="duplicate") == duplicate + 1


def test_kill_switch_gauge_follows_the_switch() -> None:
    c = TestClient(_app())
    system = _h("system", "ops")
    first = c.get("/metrics").text
    assert "taleem_kill_switch_engaged 0.0" in first
    assert "taleem_ready 1.0" in first
    assert (
        c.post("/v1/ops/kill-switch:engage", json={"reason": "drill"}, headers=system).status_code
        == 200
    )
    halted = c.post("/v1/learning/sessions", json={"student_ref": "x"}, headers=_h("student", "x"))
    assert halted.status_code == 503
    text = c.get("/metrics").text
    assert "taleem_kill_switch_engaged 1.0" in text
    assert 'path="<halted>"' in text
    c.post("/v1/ops/kill-switch:disengage", headers=system)
    assert "taleem_kill_switch_engaged 0.0" in c.get("/metrics").text


def test_unhandled_error_counts_as_a_server_error() -> None:
    app = _app()

    @app.get("/boom-for-metrics")
    def boom() -> None:
        raise RuntimeError("synthetic failure")

    c = TestClient(app, raise_server_exceptions=False)
    before = registry().counter_value("taleem_errors_total", kind="server")
    assert c.get("/boom-for-metrics").status_code == 500
    assert registry().counter_value("taleem_errors_total", kind="server") == before + 1
    text = c.get("/metrics").text
    assert 'route="/boom-for-metrics"' in text
