"""The flagged homework behind a concern: ``GET /v1/safeguarding/concerns/{id}/context``.

A system concern raised by the homework disclosure screen (HOMEWORK_AND_MARKING_CONTRACT §6) names
a submission. Only a ``safeguarding_lead`` reads what the child wrote, on demand; every read is a
``concern.context_viewed`` audit row naming the reader, the concern and the submission, never the
text. The read works with the kill switch engaged and after the learner's consent is withdrawn.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from taleem_core.contexts.safeguarding.adapters.persistence.models import (
    ConcernAuditRow,
    ConcernRow,
)
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.kill_switch import is_child_facing
from tests.test_safeguarding_api import _lead, _operator, _token
from tests.test_school_api import _SECRET, _family
from tests.test_self_paced_homework import S, _submit, publish, study

_WORDS = "My uncle hits me when nobody is home."


@pytest.fixture
def s() -> S:
    """An AI-led learner (no class) who has studied the fractions lesson."""
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app)
    client = TestClient(app)
    fam = _family(client, "solo@example.com")
    study(app, fam.student_ref)
    return S(client, app, fam)


def _flag(s: S, text: str = _WORDS, item: str = "hw-short") -> tuple[str, str]:
    r = _submit(s, item, text)
    assert r.status_code == 200, r.text
    sid = str(r.json()["submission"]["submission_id"])
    with s.app.state.safeguarding_session_factory() as session:
        (concern,) = session.scalars(
            select(ConcernRow).where(ConcernRow.context_submission_id == sid)
        )
    return str(concern.concern_id), sid


def _audit(app: FastAPI, concern_id: str) -> list[ConcernAuditRow]:
    with app.state.safeguarding_session_factory() as session:
        return list(
            session.scalars(
                select(ConcernAuditRow)
                .where(ConcernAuditRow.concern_id == concern_id)
                .order_by(ConcernAuditRow.at)
            )
        )


def _context(s: S, lead: dict[str, Any], concern_id: str) -> Any:
    return s.client.get(f"/v1/safeguarding/concerns/{concern_id}/context", headers=lead["auth"])


def test_the_lead_reads_what_the_child_wrote_and_each_read_is_audited_without_text(s: S) -> None:
    concern_id, sid = _flag(s)
    lead = _lead(s.client)
    r = _context(s, lead, concern_id)
    assert r.status_code == 200, r.text
    body = r.json()
    sub = body["submission"]
    assert body["concern_id"] == concern_id and sub["submission_id"] == sid
    assert sub["text"] == _WORDS and sub["source"] == "self_paced"
    assert sub["item_ref"] == "hw-short" and sub["attempt"] == 1
    assert isinstance(sub["submitted_at"], float)
    assert sub["item_prompt"] and sub["lesson_title"]
    ids = {m["phrase_id"]: m for m in body["matched_phrases"]}
    assert ids["en-01"]["phrase"] == "hits me" and ids["en-01"]["category"] == "felt_unsafe"
    assert body["resubmitted_since_raised"] is False and body["read_recorded"] is True
    assert _context(s, lead, concern_id).status_code == 200
    reads = [a for a in _audit(s.app, concern_id) if a.action == "concern.context_viewed"]
    assert len(reads) == 2  # one row per read
    for row in reads:
        assert row.actor_ref == lead["ref"] and row.actor_role == "safeguarding_lead"
        assert row.detail == {"submission_id": sid}
        assert "hits me" not in json.dumps(row.detail) and "uncle" not in json.dumps(row.detail)
    # The lead's concern detail now shows the reads in the audit trail, still without text.
    detail = s.client.get(f"/v1/safeguarding/concerns/{concern_id}", headers=lead["auth"])
    audit = [a for a in detail.json()["audit"] if a["action"] == "concern.context_viewed"]
    assert len(audit) == 2 and "uncle" not in json.dumps(audit)


def test_only_the_safeguarding_lead_gets_the_context(s: S) -> None:
    concern_id, _ = _flag(s)
    denied = {
        "student": s.fam.learner,
        "guardian": s.fam.guardian,
        "teacher": _token("teacher", "tch_1"),
        "mentor": _token("mentor", "mnt_1"),
        "system": _operator(),
        "safety_officer": _token("safety_officer", "stf_x"),
        "curriculum_architect": _token("curriculum_architect", "stf_y"),
        "subject_author": _token("subject_author", "stf_z"),
    }
    path = f"/v1/safeguarding/concerns/{concern_id}/context"
    for role, headers in denied.items():
        r = s.client.get(path, headers=headers)
        assert r.status_code == 403, (role, r.status_code)
        assert "uncle" not in r.text
    assert s.client.get(path).status_code == 401
    assert [a for a in _audit(s.app, concern_id) if a.action == "concern.context_viewed"] == []
    # A child-raised concern stays invisible to the guardian, and so does the system concern.
    mine = s.client.get("/v1/safeguarding/my-concerns", headers=s.fam.guardian)
    assert mine.status_code == 200 and mine.json()["concerns"] == []
    assert _context(s, _lead(s.client), concern_id).status_code == 200


def test_unknown_and_contextless_concerns_are_not_found_and_not_audited(s: S) -> None:
    lead = _lead(s.client)
    assert _context(s, lead, "cn_does_not_exist").status_code == 404
    raised = s.client.post(
        "/v1/safeguarding/concerns",
        json={"category": "felt_unsafe", "text": "someone at home"},
        headers=s.fam.learner,
    )
    assert raised.status_code == 201
    queue = s.client.get("/v1/safeguarding/queue", headers=lead["auth"]).json()["concerns"]
    (child,) = [c for c in queue if c["raised_by_role"] == "student"]
    r = _context(s, lead, child["concern_id"])
    assert r.status_code == 404 and "someone at home" not in r.text
    actions = {a.action for a in _audit(s.app, child["concern_id"])}
    assert "concern.context_viewed" not in actions


def test_a_concern_whose_submission_is_another_learners_is_not_found(s: S) -> None:
    concern_id, _ = _flag(s)
    with s.app.state.safeguarding_session_factory() as session, session.begin():
        row = session.get(ConcernRow, concern_id)
        assert row is not None
        row.subject_ref = "stu_someone_else"
    assert _context(s, _lead(s.client), concern_id).status_code == 404


def test_a_resubmission_is_flagged_and_matching_is_recomputed(s: S) -> None:
    concern_id, _ = _flag(s)
    assert _submit(s, "hw-short", "Ammi cut the roti into 4 parts").status_code == 200
    body = _context(s, _lead(s.client), concern_id).json()
    assert body["submission"]["attempt"] == 2
    assert body["resubmitted_since_raised"] is True and body["matched_phrases"] == []


def test_the_lead_reads_the_context_with_the_kill_switch_engaged(s: S) -> None:
    concern_id, _ = _flag(s)
    assert not is_child_facing(f"/v1/safeguarding/concerns/{concern_id}/context")
    engaged = s.client.post(
        "/v1/ops/kill-switch:engage", json={"reason": "drill"}, headers=_operator()
    )
    assert engaged.status_code == 200
    r = _context(s, _lead(s.client), concern_id)
    assert r.status_code == 200 and r.json()["submission"]["text"] == _WORDS


def test_the_lead_reads_the_context_after_consent_is_withdrawn(s: S) -> None:
    concern_id, _ = _flag(s)
    withdrawn = s.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": s.fam.student_ref},
        headers=s.fam.guardian,
    )
    assert withdrawn.status_code == 200, withdrawn.text
    r = _context(s, _lead(s.client), concern_id)
    assert r.status_code == 200 and r.json()["submission"]["text"] == _WORDS
