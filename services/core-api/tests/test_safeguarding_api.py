"""Safeguarding concerns over the real app: raising, visibility rules, triage, audit, kill switch.

The visibility rules under test (service docstring, doc 59):

- a child gets a receipt only — no id, nothing to list later;
- a guardian raises only about their own learner and lists only concerns they raised; a concern a
  child raised — about anyone, including that guardian — never reaches any guardian (list, export);
- free text, notes and audit reach a ``safeguarding_lead`` and nobody else: teachers, mentors,
  operators and every Studio role are denied;
- raising still works when the kill switch is engaged and when the learner's consent is withdrawn.

PostgreSQL-gated variants (the same journey on a migrated database, CHECK constraints, and the
0012 up/down/up) are at the end.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.safeguarding.adapters.persistence.models import (
    ConcernAuditRow,
    ConcernRow,
)
from taleem_core.contexts.safeguarding.domain.model import SLA_DECISION
from taleem_core.main import create_app
from taleem_core.platform import metrics as metrics_module
from taleem_core.platform.config import Settings
from taleem_core.platform.kill_switch import is_child_facing
from taleem_core.platform.metrics import Registry

from .test_privacy import _family

_DEV_SECRET = "dev-only-not-secret"  # noqa: S105 (dev stub)
_LEAD_PASSPHRASE = "a-safeguarding-passphrase"  # noqa: S105 (test fixture)
_CHILD_WORDS = "my uncle at home shouts at me"


def _token(role: str, sub: str) -> dict[str, str]:
    tok = sign_hs256({"sub": sub, "role": role, "exp": int(time.time()) + 600}, _DEV_SECRET)
    return {"Authorization": f"Bearer {tok}"}


def _operator() -> dict[str, str]:
    return _token("system", "operator-1")


def _app(**overrides: Any) -> FastAPI:
    options: dict[str, Any] = {
        "database_url": "",
        "kdf_iterations": 1_000,
        "client_ip_header": "x-real-ip",
        "jwt_dev_secret": _DEV_SECRET,
        **overrides,
    }
    return create_app(Settings(**options))


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(metrics_module, "_REGISTRY", Registry())


@pytest.fixture
def app() -> FastAPI:
    return _app()


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def _lead(client: TestClient, email: str | None = None) -> dict[str, Any]:
    """An operator-provisioned safeguarding lead, signed in through staff sign-in."""
    email = email or f"lead-{uuid.uuid4().hex[:8]}@example.com"
    created = client.post(
        "/v1/identity/staff",
        json={
            "email": email,
            "passphrase": _LEAD_PASSPHRASE,
            "displayName": "Safeguarding lead",
            "role": "safeguarding_lead",
        },
        headers=_operator(),
    )
    assert created.status_code == 201, created.text
    signed = client.post(
        "/v1/identity/staff:signin",
        json={"email": email, "passphrase": _LEAD_PASSPHRASE},
        headers={"X-Real-IP": f"198.51.100.{uuid.uuid4().int % 250}"},
    )
    assert signed.status_code == 200, signed.text
    body = signed.json()
    assert body["session"]["role"] == "safeguarding_lead"
    return {
        "ref": created.json()["staff_ref"],
        "auth": {"Authorization": f"Bearer {body['session']['access_token']}"},
    }


def _child_raise(client: TestClient, fam: dict[str, Any], **body: Any) -> Any:
    payload: dict[str, Any] = {"category": "felt_unsafe", **body}
    return client.post("/v1/safeguarding/concerns", json=payload, headers=fam["learner_auth"])


def _guardian_raise(client: TestClient, fam: dict[str, Any], **body: Any) -> Any:
    payload: dict[str, Any] = {"category": "bullying", "studentRef": fam["ref"], **body}
    return client.post("/v1/safeguarding/concerns", json=payload, headers=fam["auth"])


def _queue(client: TestClient, lead: dict[str, Any], **params: str) -> dict[str, Any]:
    response = client.get("/v1/safeguarding/queue", params=params, headers=lead["auth"])
    assert response.status_code == 200, response.text
    return dict(response.json())


# ---------------------------------------------------------------------------------- raising


def test_a_child_raises_by_tapping_only_and_gets_a_receipt_without_an_id(
    client: TestClient,
) -> None:
    fam = _family(client, "Ayesha")
    response = _child_raise(client, fam, context={"screen": "/student/today"})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["received"] is True
    assert "concern_id" not in body and fam["ref"] not in json.dumps(body)
    # Honest: a person will read it; no response time is promised (FD-06).
    assert "grown-up" in body["notice"] and "minute" not in body["notice"]


def test_a_child_cannot_raise_about_another_learner(client: TestClient) -> None:
    fam, other = _family(client, "Ayesha"), _family(client, "Bilal")
    refused = _child_raise(client, fam, studentRef=other["ref"])
    assert refused.status_code == 403
    assert _child_raise(client, fam, studentRef=fam["ref"]).status_code == 201


def test_input_is_bounded_and_context_is_sanitised(app: FastAPI, client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    assert _child_raise(client, fam, category="nope").status_code == 422
    assert _child_raise(client, fam, text="x" * 501).status_code == 422
    assert _child_raise(client, fam, context={"lessonId": "<b>"}).status_code == 422
    assert _child_raise(client, fam, unknown="field").status_code == 422
    ok = _child_raise(
        client,
        fam,
        text="  someone\x07 was mean  ",
        context={"screen": f"/student/progress?ref={fam['ref']}", "lessonId": "L-1"},
    )
    assert ok.status_code == 201, ok.text
    with app.state.safeguarding_session_factory() as s:
        row = s.scalars(select(ConcernRow)).one()
    assert (row.free_text, row.context_screen, row.context_lesson_id) == (
        "someone was mean",
        "",  # a screen carrying a query string is dropped, never stored verbatim
        "L-1",
    )
    assert row.subject_ref == fam["ref"] and row.raised_by_role == "student"


def test_raising_is_rate_limited_per_subject(client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    for _ in range(20):
        assert _child_raise(client, fam, category="other").status_code == 201
    assert _child_raise(client, fam, category="other").status_code == 429
    other = _family(client, "Bilal")
    assert _child_raise(client, other).status_code == 201  # another subject is unaffected


# ------------------------------------------------------------------------- visibility rules


def test_a_guardian_raises_only_about_their_own_learner_and_lists_only_their_own(
    client: TestClient,
) -> None:
    fam, other = _family(client, "Ayesha"), _family(client, "Bilal")
    raised = _guardian_raise(client, fam, text="older pupils take her lunch")
    assert raised.status_code == 201, raised.text
    view = raised.json()
    assert view["status"] == "received" and view["text"] == "older pupils take her lunch"
    # Another family's learner is a 404, never a 403 that would confirm the ref exists.
    assert _guardian_raise(client, other, studentRef=fam["ref"]).status_code == 404
    mine = client.get("/v1/safeguarding/my-concerns", headers=fam["auth"]).json()["concerns"]
    assert [c["concern_id"] for c in mine] == [view["concern_id"]]
    theirs = client.get("/v1/safeguarding/my-concerns", headers=other["auth"]).json()["concerns"]
    assert theirs == []


def test_a_concern_a_child_raised_never_reaches_their_guardian(client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    control = _family(client, "Bilal")  # a family where the child raised nothing
    assert _child_raise(client, fam, text=_CHILD_WORDS).status_code == 201

    # Not in the guardian's list ...
    mine = client.get("/v1/safeguarding/my-concerns", headers=fam["auth"])
    assert mine.status_code == 200 and mine.json()["concerns"] == []
    # ... not in the guardian's export of the child's data ...
    exported = client.get(f"/v1/privacy/learners/{fam['ref']}/export", headers=fam["auth"])
    assert exported.status_code == 200, exported.text
    bundle = json.dumps(exported.json())
    assert _CHILD_WORDS not in bundle and "felt_unsafe" not in bundle
    section = exported.json()["sections"]["safeguarding"]
    # ... and the export looks exactly as it does for a child who raised nothing.
    baseline = client.get(
        f"/v1/privacy/learners/{control['ref']}/export", headers=control["auth"]
    ).json()["sections"]["safeguarding"]
    assert section == baseline
    assert section["concerns_raised_by_guardian"] == []
    # ... nor in the guardian portal.
    portal = client.get(f"/v1/guardian/children/{fam['ref']}", headers=fam["auth"])
    assert _CHILD_WORDS not in portal.text


def test_only_a_safeguarding_lead_reaches_the_queue_or_free_text(client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    _child_raise(client, fam, text=_CHILD_WORDS)
    lead = _lead(client)
    concern_id = _queue(client, lead)["concerns"][0]["concern_id"]
    denied = {
        "student": fam["learner_auth"],
        "guardian": fam["auth"],
        "teacher": _token("teacher", "tch_1"),
        "mentor": _token("mentor", "mnt_1"),
        "system": _operator(),
        "safety_officer": _token("safety_officer", "stf_x"),
        "curriculum_architect": _token("curriculum_architect", "stf_y"),
    }
    for role, headers in denied.items():
        for method, path in (
            ("GET", "/v1/safeguarding/queue"),
            ("GET", f"/v1/safeguarding/concerns/{concern_id}"),
            ("POST", f"/v1/safeguarding/concerns/{concern_id}:acknowledge"),
        ):
            response = client.request(method, path, headers=headers)
            assert response.status_code == 403, (role, path, response.status_code)
            assert _CHILD_WORDS not in response.text
    for role in ("mentor", "system", "safety_officer"):
        raised = client.post(
            "/v1/safeguarding/concerns", json={"category": "other"}, headers=denied[role]
        )
        assert raised.status_code == 403, role
    # A teacher may raise only about a learner in their own class (test_homework_api.py); a token
    # with no teacher account, naming nobody, is not found.
    raised = client.post(
        "/v1/safeguarding/concerns", json={"category": "other"}, headers=denied["teacher"]
    )
    assert raised.status_code == 404
    assert client.get("/v1/safeguarding/queue").status_code == 401
    # A guardian has no route to the lead's views either way.
    assert client.get("/v1/safeguarding/my-concerns", headers=lead["auth"]).status_code == 403


def test_the_lead_role_reaches_nothing_but_safeguarding(client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    lead = _lead(client)
    for path in (
        "/v1/studio/lessons",
        f"/v1/learning/students/{fam['ref']}/knowledge",
        f"/v1/guardian/children/{fam['ref']}",
        f"/v1/privacy/learners/{fam['ref']}/export",
        "/v1/identity/staff",
        "/v1/ops/status",
    ):
        assert client.get(path, headers=lead["auth"]).status_code == 403, path
    assert client.get("/v1/identity/staff/me", headers=lead["auth"]).status_code == 200


# ---------------------------------------------------------------------------------- triage


def test_queue_orders_by_priority_then_age_and_states_the_sla_is_unset(
    client: TestClient,
) -> None:
    fam = _family(client, "Ayesha")
    _child_raise(client, fam, category="other")  # T3, oldest
    _child_raise(client, fam, category="bullying")  # T2
    _child_raise(client, fam, category="very_sad")  # T1
    _child_raise(client, fam, category="felt_unsafe")  # T1, newest
    queue = _queue(client, _lead(client))
    assert [c["priority"] for c in queue["concerns"]] == ["T1", "T1", "T2", "T3"]
    t1 = queue["concerns"][:2]
    assert t1[0]["created_at"] <= t1[1]["created_at"]  # oldest first within a tier
    assert all(c["age_seconds"] >= 0 for c in queue["concerns"])
    # SLA: UNSET by default, said so, and nothing is ever "overdue" against an invented number.
    assert queue["sla"]["configured"] is False and queue["sla"]["notice"] == SLA_DECISION
    assert all(c["overdue"] is None for c in queue["concerns"])
    assert "text" not in queue["concerns"][0]  # free text only in the (audited) detail view


def test_a_configured_sla_flags_overdue_concerns() -> None:
    app = _app(safeguarding_ack_sla_json='{"T1": 0.001}')
    client = TestClient(app)
    fam = _family(client, "Ayesha")
    _child_raise(client, fam, category="felt_unsafe")
    _child_raise(client, fam, category="other")
    time.sleep(0.01)
    queue = _queue(client, _lead(client))
    by_tier = {c["priority"]: c["overdue"] for c in queue["concerns"]}
    assert by_tier == {"T1": True, "T3": None}  # T3 has no threshold: unknown, not "fine"
    assert queue["sla"]["notice"] == SLA_DECISION  # still not fully decided
    metrics = client.get("/metrics").text
    assert 'taleem_safeguarding_concerns_overdue{priority="T1"} 1.0' in metrics


def test_full_triage_lifecycle_is_audited_by_actor(app: FastAPI, client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    _child_raise(client, fam, text=_CHILD_WORDS, context={"screen": "student/today"})
    lead = _lead(client)
    concern_id = _queue(client, lead)["concerns"][0]["concern_id"]
    base = f"/v1/safeguarding/concerns/{concern_id}"

    detail = client.get(base, headers=lead["auth"]).json()
    assert detail["text"] == _CHILD_WORDS and detail["household_caution"] is True
    assert detail["guardian_informed"] is False and detail["contacted"] == []

    acked = client.post(f"{base}:acknowledge", headers=lead["auth"])
    assert acked.status_code == 200 and acked.json()["status"] == "acknowledged"
    noted = client.post(
        f"{base}/notes", json={"body": "Spoke to the mentor."}, headers=lead["auth"]
    )
    assert noted.status_code == 201 and noted.json()["notes"][0]["author_ref"] == lead["ref"]
    # Referral before escalation is refused; escalation needs a reason and contacts nobody.
    early = client.post(
        f"{base}:resolve", json={"outcome": "referred_externally"}, headers=lead["auth"]
    )
    assert early.status_code == 409 and early.json()["code"] == "CONCERN_NOT_ESCALATED"
    no_reason = client.post(f"{base}:escalate", json={"reason": ""}, headers=lead["auth"])
    assert no_reason.status_code == 422
    escalated = client.post(
        f"{base}:escalate", json={"reason": "Possible harm at home."}, headers=lead["auth"]
    )
    body = escalated.json()
    assert body["status"] == "escalated" and body["external_referral_needed"] is True
    assert body["contacted"] == [] and "contacts nobody" in body["contact_notice"]
    resolved = client.post(
        f"{base}:resolve",
        json={"outcome": "referred_externally", "note": "Referred by phone (outside Taleem)."},
        headers=lead["auth"],
    )
    assert resolved.status_code == 200 and resolved.json()["outcome"] == "referred_externally"
    again = client.post(f"{base}:resolve", json={"outcome": "duplicate"}, headers=lead["auth"])
    assert again.status_code == 409
    bad = client.post(f"{base}:resolve", json={"outcome": "nope"}, headers=lead["auth"])
    assert bad.status_code in (409, 422)

    # Every action is audited with the actor's subject; the audit carries no free text.
    with app.state.safeguarding_session_factory() as s:
        audit = s.scalars(
            select(ConcernAuditRow)
            .where(ConcernAuditRow.concern_id == concern_id)
            .order_by(ConcernAuditRow.at, ConcernAuditRow.event_id)
        ).all()
    actions = [(a.action, a.actor_ref, a.actor_role) for a in audit]
    assert actions[0] == ("concern.raised", fam["ref"], "student")
    lead_actions = [
        a for a, ref, role in actions[1:] if ref == lead["ref"] and role == "safeguarding_lead"
    ]
    assert lead_actions == [
        "concern.viewed",
        "concern.acknowledged",
        "concern.note_added",
        "concern.escalated",
        "concern.resolved",
    ]
    assert all(_CHILD_WORDS not in json.dumps(a.detail) for a in audit)
    # Resolved concerns leave the open queue and appear on request.
    assert _queue(client, lead)["concerns"] == []
    assert [c["status"] for c in _queue(client, lead, includeResolved="true")["concerns"]] == [
        "resolved"
    ]


def test_a_guardian_sees_only_a_coarse_status_for_their_own_concern(client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    concern_id = _guardian_raise(client, fam).json()["concern_id"]
    lead = _lead(client)
    client.post(
        f"/v1/safeguarding/concerns/{concern_id}:escalate",
        json={"reason": "Needs the school's safeguarding officer."},
        headers=lead["auth"],
    )
    mine = client.get("/v1/safeguarding/my-concerns", headers=fam["auth"]).json()["concerns"]
    assert mine[0]["status"] == "in_review"  # never "escalated", notes, or outcome
    assert "Needs the school" not in json.dumps(mine) and "escalat" not in json.dumps(mine)
    detail = client.get(f"/v1/safeguarding/concerns/{concern_id}", headers=lead["auth"]).json()
    assert detail["household_caution"] is False  # raised by the guardian themselves


def test_a_suspended_lead_is_refused_at_once(client: TestClient) -> None:
    lead = _lead(client)
    assert client.get("/v1/safeguarding/queue", headers=lead["auth"]).status_code == 200
    suspended = client.post(f"/v1/identity/staff/{lead['ref']}:suspend", headers=_operator())
    assert suspended.status_code == 200
    refused = client.get("/v1/safeguarding/queue", headers=lead["auth"])
    assert refused.status_code == 403 and refused.json()["code"] == "STAFF_INACTIVE"


# ------------------------------------------------------------------- the channel stays open


def test_raising_still_works_with_the_kill_switch_engaged(client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    assert not is_child_facing("/v1/safeguarding/concerns")
    engaged = client.post(
        "/v1/ops/kill-switch:engage", json={"reason": "drill"}, headers=_operator()
    )
    assert engaged.status_code == 200 and engaged.json()["engaged"] is True
    halted = client.post(
        "/v1/learning/sessions", json={"student_ref": fam["ref"]}, headers=fam["learner_auth"]
    )
    assert halted.status_code == 503  # learning is halted ...
    assert _child_raise(client, fam).status_code == 201  # ... the safety channel is not
    assert _guardian_raise(client, fam).status_code == 201
    lead = _lead(client)
    assert len(_queue(client, lead)["concerns"]) == 2  # and the lead can still triage


def test_raising_still_works_after_consent_is_withdrawn(client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    withdrawn = client.post(
        "/v1/identity/consents:withdraw", json={"studentRef": fam["ref"]}, headers=fam["auth"]
    )
    assert withdrawn.status_code == 200, withdrawn.text
    learning = client.get(
        f"/v1/learning/students/{fam['ref']}/knowledge", headers=fam["learner_auth"]
    )
    assert learning.status_code == 403  # the learner gate closes learning ...
    assert _child_raise(client, fam).status_code == 201  # ... not the safety channel


# ---------------------------------------------------------------------------------- metrics


def test_metrics_count_new_and_unacknowledged_concerns(client: TestClient) -> None:
    fam = _family(client, "Ayesha")
    _child_raise(client, fam, text=_CHILD_WORDS)
    _guardian_raise(client, fam)
    text = client.get("/metrics").text
    assert 'taleem_safeguarding_concerns_unacknowledged{priority="T1"} 1.0' in text
    assert 'taleem_safeguarding_concerns_unacknowledged{priority="T2"} 1.0' in text
    assert 'taleem_safeguarding_concerns_unacknowledged{priority="T3"} 0.0' in text
    assert 'taleem_safeguarding_concerns_overdue{priority="T1"} 0.0' in text
    assert "taleem_safeguarding_sla_configured 0.0" in text
    raised = 'taleem_safeguarding_concerns_raised_total{priority="T1",raised_by="student"} 1.0'
    assert raised in text
    # Metrics and their labels never carry a ref or a word the child wrote.
    assert fam["ref"] not in text and _CHILD_WORDS not in text


def test_a_failed_queue_read_is_counted_and_the_scrape_still_renders(
    app: FastAPI, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken() -> dict[str, dict[str, float]]:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(app.state.safeguarding_service, "gauges", broken)
    scraped = client.get("/metrics")
    assert scraped.status_code == 200
    assert "taleem_safeguarding_gauge_errors_total 1.0" in scraped.text
    assert "taleem_safeguarding_sla_configured 0.0" in scraped.text


# ------------------------------------------------------------------------ PostgreSQL-gated

PG_URL = os.environ.get("CS_DATABASE_URL")
_pg_only = pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")


def _alembic() -> Any:
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    return cfg


def _dispose(app: FastAPI) -> None:
    for name in (
        "identity_session_factory",
        "learning_session_factory",
        "studio_session_factory",
        "ops_session_factory",
    ):
        factory = getattr(app.state, name, None)
        if factory is not None:
            factory.kw["bind"].dispose()


@_pg_only
def test_visibility_triage_and_kill_switch_over_postgres() -> None:
    from alembic import command

    command.upgrade(_alembic(), "head")
    app = _app(database_url=PG_URL or "")
    try:
        # Its own client address: the PostgreSQL rate limiter is shared by every test in the run,
        # and the default "testclient" address would spend the registration budget of other tests.
        client = TestClient(app, headers={"X-Real-IP": f"198.51.100.{uuid.uuid4().hex[:8]}"})
        fam, other = _family(client, "Ayesha"), _family(client, "Bilal")
        client.post("/v1/ops/kill-switch:engage", json={"reason": "drill"}, headers=_operator())
        try:
            assert _child_raise(client, fam, text=_CHILD_WORDS).status_code == 201
            mine = _guardian_raise(client, fam).json()
        finally:
            client.post("/v1/ops/kill-switch:disengage", headers=_operator())
        assert _guardian_raise(client, other, studentRef=fam["ref"]).status_code == 404
        listed = client.get("/v1/safeguarding/my-concerns", headers=fam["auth"]).json()
        assert [c["concern_id"] for c in listed["concerns"]] == [mine["concern_id"]]
        assert _CHILD_WORDS not in json.dumps(listed)
        lead = _lead(client)
        queue = _queue(client, lead)["concerns"]
        ours = [c for c in queue if c["subject_ref"] == fam["ref"]]
        assert {c["raised_by_role"] for c in ours} == {"student", "guardian"}
        child = next(c for c in ours if c["raised_by_role"] == "student")
        base = f"/v1/safeguarding/concerns/{child['concern_id']}"
        assert client.get(base, headers=lead["auth"]).json()["text"] == _CHILD_WORDS
        assert client.post(f"{base}:acknowledge", headers=lead["auth"]).status_code == 200
        done = client.post(
            f"{base}:resolve", json={"outcome": "support_given"}, headers=lead["auth"]
        )
        assert done.status_code == 200
        with app.state.safeguarding_session_factory() as s:
            actions = [
                a.action
                for a in s.scalars(
                    select(ConcernAuditRow)
                    .where(ConcernAuditRow.concern_id == child["concern_id"])
                    .order_by(ConcernAuditRow.at)
                )
            ]
        assert actions == [
            "concern.raised",
            "concern.viewed",
            "concern.acknowledged",
            "concern.resolved",
        ]
        assert "taleem_safeguarding_concerns_unacknowledged" in client.get("/metrics").text
    finally:
        _dispose(app)


@_pg_only
def test_database_checks_refuse_invented_states() -> None:
    from alembic import command
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import IntegrityError

    command.upgrade(_alembic(), "head")
    engine = create_engine(PG_URL or "")
    insert = text(
        "INSERT INTO safeguarding.concern (concern_id, subject_ref, raised_by_ref, raised_by_role, "
        "category, priority, status, outcome, created_at, free_text) VALUES "
        "(:id, 'stu_x', 'stu_x', :role, :category, :priority, :status, :outcome, 1, :text)"
    )
    good = {
        "id": f"sgc_{uuid.uuid4().hex}",
        "role": "student",
        "category": "other",
        "priority": "T3",
        "status": "open",
        "outcome": None,
        "text": None,
    }
    try:
        for bad in (
            {"category": "made_up"},
            {"priority": "T0"},
            {"status": "deleted"},
            {"role": "mentor"},
            {"status": "resolved"},  # resolved needs an outcome
            {"outcome": "support_given"},  # an outcome needs resolved
            {"text": "x" * 501},
            {"id": "bad_prefix"},
        ):
            row = {**good, "id": f"sgc_{uuid.uuid4().hex}", **bad}
            with pytest.raises(IntegrityError), engine.begin() as conn:
                conn.execute(insert, row)
        with engine.begin() as conn:
            conn.execute(insert, good)
            conn.execute(
                text("DELETE FROM safeguarding.concern WHERE concern_id = :id"), {"id": good["id"]}
            )
        # The staff CHECK now admits the safeguarding lead (and still nothing outside the list).
        with engine.begin() as conn:
            ref = f"stf_{uuid.uuid4().hex}"
            conn.execute(
                text(
                    "INSERT INTO identity.staff_account "
                    "(staff_ref, email, passphrase_hash, display_name, role) "
                    "VALUES (:ref, :email, 'x', 'X', 'safeguarding_lead')"
                ),
                {"ref": ref, "email": f"{uuid.uuid4().hex}@example.com"},
            )
            conn.execute(
                text("DELETE FROM identity.staff_account WHERE staff_ref = :ref"), {"ref": ref}
            )
    finally:
        engine.dispose()
