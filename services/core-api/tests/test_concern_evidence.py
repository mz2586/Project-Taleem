"""The immutable evidence behind a concern (``safeguarding.concern_evidence``, alembic 0018).

A concern raised from a homework submission — by the disclosure screen or by a teacher from a
marking row — stores the flagged text (with attempt, submitted_at, item, objective, sha256) in the
same transaction as the concern. A resubmission changes the submission, never the snapshot, so the
lead's context read always shows what was flagged, plus the current text only when it differs.
Only a ``safeguarding_lead`` reads it; no other surface, export, log line or audit row carries it.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from taleem_core.contexts.privacy.adapters.safeguarding_data import SafeguardingLearnerData
from taleem_core.contexts.privacy.domain.policy import RetainedSet
from taleem_core.contexts.safeguarding.adapters.persistence.models import (
    ConcernAuditRow,
    ConcernEvidenceRow,
    ConcernRow,
)
from taleem_core.contexts.safeguarding.adapters.persistence.uow import SqlSafeguardingUnitOfWork
from taleem_core.contexts.safeguarding.application.service import NO_SNAPSHOT_NOTICE
from taleem_core.contexts.safeguarding.domain.model import ConcernEvidence, text_digest
from taleem_core.contexts.school.adapters.persistence.models import SchoolAuditRow
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from tests.test_homework_api import (
    W,
    w,  # noqa: F401 - fixture
)
from tests.test_homework_api import _queue as _teacher_queue
from tests.test_homework_api import _submit as _assigned_submit
from tests.test_safeguarding_api import _lead, _operator, _token
from tests.test_school_api import _SECRET, _family
from tests.test_self_paced_homework import S, _hw, _submit, publish, study

_WORDS = "My uncle hits me when nobody is home."
_LATER = "Ammi cut the roti into 4 parts"


@pytest.fixture
def s() -> S:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app)
    client = TestClient(app)
    fam = _family(client, "solo@example.com")
    study(app, fam.student_ref)
    return S(client, app, fam)


def _evidence_rows(app: FastAPI) -> list[dict[str, Any]]:
    with app.state.safeguarding_session_factory() as session:
        rows = session.scalars(select(ConcernEvidenceRow).order_by(ConcernEvidenceRow.created_at))
        return [
            {c.name: getattr(r, c.name) for c in ConcernEvidenceRow.__table__.columns} for r in rows
        ]


def _flag(s: S, text: str = _WORDS) -> tuple[str, str]:
    r = _submit(s, "hw-short", text)
    assert r.status_code == 200, r.text
    sid = str(r.json()["submission"]["submission_id"])
    with s.app.state.safeguarding_session_factory() as session:
        (concern,) = session.scalars(
            select(ConcernRow).where(ConcernRow.context_submission_id == sid)
        )
    return str(concern.concern_id), sid


def _context(client: TestClient, headers: dict[str, str], concern_id: str) -> Any:
    return client.get(f"/v1/safeguarding/concerns/{concern_id}/context", headers=headers)


# ------------------------------------------------------------------------------- capture


def test_a_flagged_disclosure_stores_one_snapshot_with_the_concern(s: S) -> None:
    concern_id, sid = _flag(s)
    (row,) = _evidence_rows(s.app)
    assert row["concern_id"] == concern_id and row["submission_id"] == sid
    assert row["text"] == _WORDS and row["attempt"] == 1 and row["item_ref"] == "hw-short"
    assert row["objective_code"] and isinstance(row["submitted_at"], float)
    assert row["text_sha256"] == hashlib.sha256(_WORDS.encode("utf-8")).hexdigest()
    assert row["created_at"] >= row["submitted_at"]


def test_an_ordinary_answer_stores_no_snapshot(s: S) -> None:
    assert _submit(s, "hw-short", _LATER).status_code == 200
    assert _evidence_rows(s.app) == []


def test_a_resubmission_leaves_the_snapshot_unchanged_and_current_differs(s: S) -> None:
    concern_id, _ = _flag(s)
    (before,) = _evidence_rows(s.app)
    assert _submit(s, "hw-short", _LATER).status_code == 200
    assert _evidence_rows(s.app) == [before]  # byte-for-byte, and still exactly one
    body = _context(s.client, _lead(s.client)["auth"], concern_id).json()
    assert body["flagged"]["text"] == _WORDS and body["flagged"]["attempt"] == 1
    assert body["flagged"]["text_sha256"] == before["text_sha256"]
    assert body["current"]["text"] == _LATER and body["current"]["attempt"] == 2
    assert body["resubmitted_since_raised"] is True


def test_resubmitting_the_same_words_is_reported_without_a_current_copy(s: S) -> None:
    concern_id, _ = _flag(s)
    assert _submit(s, "hw-short", _WORDS).status_code == 200
    body = _context(s.client, _lead(s.client)["auth"], concern_id).json()
    assert body["current"] is None and body["resubmitted_since_raised"] is True
    assert body["flagged"]["attempt"] == 1


def test_one_snapshot_per_concern_even_when_the_screen_runs_again(s: S) -> None:
    concern_id, sid = _flag(s)
    svc = s.app.state.safeguarding_service
    for _ in range(2):
        assert svc.screen_submission(
            student_ref=s.fam.student_ref,
            submission_id=sid,
            text=_WORDS,
            attempt=1,
            submitted_at=1.0,
            item_ref="hw-short",
            objective_code="X",
        )
    assert [r["concern_id"] for r in _evidence_rows(s.app)] == [concern_id]
    # The store itself refuses a second snapshot for the same concern (primary key).
    dup = ConcernEvidence.capture(
        concern_id=concern_id,
        submission_id=sid,
        text="other words",
        attempt=1,
        submitted_at=1.0,
        item_ref="hw-short",
        objective_code="X",
        now=2.0,
    )
    sf = s.app.state.safeguarding_session_factory
    with pytest.raises(IntegrityError), SqlSafeguardingUnitOfWork(sf) as uow:
        uow.evidence.add(dup)
        uow.commit()
    assert _evidence_rows(s.app)[0]["text"] == _WORDS


def test_the_screen_snapshots_the_text_it_matched_not_a_later_one(s: S) -> None:
    """A resubmission racing the screen cannot replace the evidence: the screened text travels
    with its metadata from the school context."""
    r = _submit(s, "hw-short", _LATER)
    sid = str(r.json()["submission"]["submission_id"])
    raised = s.app.state.safeguarding_service.screen_submission(
        student_ref=s.fam.student_ref,
        submission_id=sid,
        text=_WORDS,
        attempt=7,
        submitted_at=123.0,
        item_ref="hw-short",
        objective_code="OBJ",
    )
    assert raised is True
    (row,) = _evidence_rows(s.app)
    assert (row["text"], row["attempt"], row["submitted_at"]) == (_WORDS, 7, 123.0)


def test_a_teacher_concern_from_a_submission_snapshots_the_answer(w: W) -> None:  # noqa: F811
    first = "The man at the shop touched me."
    r = _assigned_submit(w, "hw-long", first)
    sub = r.json()["submission"]["submission_id"]
    raised = w.client.post(
        f"/v1/school/submissions/{sub}:concern",
        json={"category": "felt_unsafe", "text": "Please read the answer."},
        headers=w.teacher_a,
    )
    assert raised.status_code == 201, raised.text
    with w.app.state.safeguarding_session_factory() as session:
        teacher_concern = session.scalars(
            select(ConcernRow).where(ConcernRow.raised_by_role == "teacher")
        ).one()
        snaps = list(session.scalars(select(ConcernEvidenceRow)))
    by_concern = {e.concern_id: e for e in snaps}
    snap = by_concern[teacher_concern.concern_id]
    assert snap.text == first and snap.attempt == 1 and snap.text_sha256 == text_digest(first)
    # The teacher returns the work; the child rewrites it. The snapshot stands.
    back = w.client.post(
        f"/v1/school/submissions/{sub}:return", json={"feedback": "Try again"}, headers=w.teacher_a
    )
    assert back.status_code == 200
    assert _assigned_submit(w, "hw-long", "Halves are equal parts.").status_code == 200
    body = _context(w.client, _lead(w.client)["auth"], teacher_concern.concern_id).json()
    assert body["flagged"]["text"] == first
    assert body["current"]["text"] == "Halves are equal parts."
    # The teacher's own marking queue shows only the current answer, never the evidence.
    queue = _teacher_queue(w).json()
    assert first not in json.dumps(queue) and "flagged" not in json.dumps(queue)
    assert (
        "touched"
        not in w.client.get(
            f"/v1/school/learners/{w.fam.student_ref}/homework", headers=w.fam.learner
        ).text
    )


# --------------------------------------------------------------------------------- access


def test_only_the_lead_reads_the_snapshot(s: S) -> None:
    concern_id, _ = _flag(s)
    assert _submit(s, "hw-short", _LATER).status_code == 200
    denied = {
        "student": s.fam.learner,
        "guardian": s.fam.guardian,
        "teacher": _token("teacher", "tch_1"),
        "mentor": _token("mentor", "mnt_1"),
        "operator": _operator(),
        "safety_officer": _token("safety_officer", "stf_x"),
        "subject_author": _token("subject_author", "stf_z"),
    }
    for role, headers in denied.items():
        r = _context(s.client, headers, concern_id)
        assert r.status_code == 403, role
        assert "uncle" not in r.text
        detail = s.client.get(f"/v1/safeguarding/concerns/{concern_id}", headers=headers)
        assert detail.status_code == 403 and "uncle" not in detail.text
    lead = _lead(s.client)
    assert _context(s.client, lead["auth"], concern_id).json()["flagged"]["text"] == _WORDS
    # The lead's queue and concern detail do not inline the evidence: it is read on demand only.
    queue = s.client.get("/v1/safeguarding/queue", headers=lead["auth"]).text
    detail = s.client.get(f"/v1/safeguarding/concerns/{concern_id}", headers=lead["auth"]).text
    assert "uncle" not in queue and "uncle" not in detail
    # Learner and guardian surfaces never carry it (the current submission is the later text).
    assert "uncle" not in _hw(s).text
    mine = s.client.get("/v1/safeguarding/my-concerns", headers=s.fam.guardian)
    assert mine.status_code == 200 and "uncle" not in mine.text


def test_no_text_in_any_log_line_or_audit_row(
    s: S, caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    concern_id, _ = _flag(s)
    assert _submit(s, "hw-short", _LATER).status_code == 200
    lead = _lead(s.client)
    assert _context(s.client, lead["auth"], concern_id).status_code == 200
    out, err = capfd.readouterr()
    emitted = out + err + caplog.text
    for fragment in ("uncle", "hits me", "nobody is home", text_digest(_WORDS)):
        assert fragment not in emitted, fragment
    with s.app.state.safeguarding_session_factory() as session:
        audit = [
            {"action": a.action, "detail": a.detail}
            for a in session.scalars(select(ConcernAuditRow))
        ]
    with s.app.state.school_session_factory() as session:
        school_audit = [
            {c.name: getattr(r, c.name) for c in SchoolAuditRow.__table__.columns}
            for r in session.scalars(select(SchoolAuditRow))
        ]
    dumped = json.dumps(audit, default=str) + json.dumps(school_audit, default=str)
    assert "uncle" not in dumped and text_digest(_WORDS) not in dumped
    assert {"concern.raised", "concern.context_viewed"} <= {a["action"] for a in audit}


# ------------------------------------------------------------------- concerns before 0018


def test_a_concern_without_a_snapshot_says_so_and_shows_only_the_latest_text(s: S) -> None:
    concern_id, _ = _flag(s)
    with s.app.state.safeguarding_session_factory() as session, session.begin():
        session.delete(session.get(ConcernEvidenceRow, concern_id))  # SQLite has no trigger
    body = _context(s.client, _lead(s.client)["auth"], concern_id).json()
    assert body["flagged"] is None and body["snapshot"] is False
    assert body["current"]["text"] == _WORDS and body["notice"] == NO_SNAPSHOT_NOTICE
    with s.app.state.safeguarding_session_factory() as session, session.begin():
        row = session.get(ConcernRow, concern_id)
        assert row is not None
        row.subject_ref = "stu_someone_else"
    assert _context(s.client, _lead(s.client)["auth"], concern_id).status_code == 404


# -------------------------------------------------------------------------------- privacy


def _erase(s: S) -> dict[str, Any]:
    ref = s.fam.student_ref
    req = s.client.post(f"/v1/privacy/learners/{ref}/erasure-requests", headers=s.fam.guardian)
    assert req.status_code == 202, req.text
    done = s.client.post(
        f"/v1/privacy/learners/{ref}/erasure:confirm",
        json={"confirmationToken": req.json()["confirmation_token"]},
        headers=s.fam.guardian,
    )
    assert done.status_code == 200, done.text
    return dict(done.json())


def test_the_guardian_export_never_carries_the_evidence(s: S) -> None:
    _flag(s)
    assert _submit(s, "hw-short", _LATER).status_code == 200
    export = s.client.get(
        f"/v1/privacy/learners/{s.fam.student_ref}/export", headers=s.fam.guardian
    )
    assert export.status_code == 200, export.text
    bundle = json.dumps(export.json())
    assert "uncle" not in bundle and text_digest(_WORDS) not in bundle
    section = export.json()["sections"]["safeguarding"]
    assert section["concerns_raised_by_guardian"] == [] and section["withheld"]


def test_the_guardian_export_withholds_a_flagged_answer_that_was_never_resubmitted(s: S) -> None:
    """The child's current homework text IS the disclosure: it must not reach the guardian,
    and the export must not reveal that anything was flagged (the notice is always present)."""
    _flag(s)
    export = s.client.get(
        f"/v1/privacy/learners/{s.fam.student_ref}/export", headers=s.fam.guardian
    )
    assert export.status_code == 200, export.text
    bundle = json.dumps(export.json())
    assert "uncle" not in bundle and text_digest(_WORDS) not in bundle
    school = export.json()["sections"]["school"]
    assert school["withheld"] and "safeguarding" in school["withheld"][0]


def test_the_school_withholding_notice_is_present_even_when_nothing_is_flagged(s: S) -> None:
    export = s.client.get(
        f"/v1/privacy/learners/{s.fam.student_ref}/export", headers=s.fam.guardian
    )
    assert export.status_code == 200, export.text
    assert export.json()["sections"]["school"]["withheld"]  # constant: reveals nothing


def test_erasure_retains_the_snapshot_with_its_pseudonymised_concern(s: S) -> None:
    concern_id, _ = _flag(s)
    (before,) = _evidence_rows(s.app)
    receipt = _erase(s)
    assert receipt["verified"] is True
    assert _evidence_rows(s.app) == [before]  # kept unchanged; it names no learner
    with s.app.state.safeguarding_session_factory() as session:
        concern = session.get(ConcernRow, concern_id)
        assert concern is not None and concern.subject_ref == receipt["tombstone_ref"]
    # The submission is gone; the lead still reads the evidence.
    body = _context(s.client, _lead(s.client)["auth"], concern_id).json()
    assert body["flagged"]["text"] == _WORDS and body["current"] is None
    assert body["submission"]["available"] is False


def test_erasure_in_erase_mode_deletes_the_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TALEEM_PRIVACY_SAFEGUARDING_CONCERNS", "erase")
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish(app)
    client = TestClient(app)
    fam = _family(client, "erase@example.com")
    study(app, fam.student_ref)
    s = S(client, app, fam)
    _flag(s)
    assert len(_evidence_rows(app)) == 1
    _erase(s)
    assert _evidence_rows(app) == []


def test_pseudonymisation_rewrites_a_ref_inside_the_snapshot_and_rehashes(s: S) -> None:
    ref = s.fam.student_ref
    concern_id, _ = _flag(s, f"{_WORDS} I am {ref}.")
    port = SafeguardingLearnerData(s.app.state.safeguarding_session_factory)
    assert port.remaining(ref)["concern_evidence"] == 1
    retained = RetainedSet()
    counts = port.erase(ref, retained)
    assert counts["concern_evidence"] == 1
    (row,) = _evidence_rows(s.app)
    tomb = retained.tombstone_ref(ref)
    assert ref not in row["text"] and tomb in row["text"]
    assert row["text_sha256"] == text_digest(row["text"]) and row["concern_id"] == concern_id
    assert port.remaining(ref)["concern_evidence"] == 0


def test_the_completeness_gate_knows_the_table(s: S) -> None:
    assert "safeguarding.concern_evidence" in s.app.state.privacy_service.covered_tables()
