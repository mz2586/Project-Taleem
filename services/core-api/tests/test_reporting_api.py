"""Report cards (REPORT_CARD_CONTRACT.md), end to end on the composed app.

The primary path is system issuance: Taleem issues a learner's card for a closed period with no
class or teacher (the scheduler CLI, or the guardian's ``:generate``). A teacher may also preview
and issue cards for their own class. Also: figures reconcile with the stored evidence, the
no-evidence card, supersede-not-edit, acknowledge once, hash re-verification, relationship-scoped
reads, the learner consent gate + kill switch, refs-only audit, outbox, privacy export/erasure.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from taleem_core.contexts.learning.adapters.persistence.models import AssessmentEvidenceRow
from taleem_core.contexts.reporting.adapters.persistence.models import (
    ReportCardAuditRow,
    ReportCardOutboxRow,
    ReportCardRow,
)
from taleem_core.contexts.reporting.issue_due import main as issue_due_main
from taleem_core.contexts.reporting.issue_due import month_period
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.ids import uuid7
from taleem_core.vertical_slice.fractions_lesson import LESSON_KEY, OBJECTIVE_CODE
from tests.test_homework_api import publish_written_lesson
from tests.test_school_api import _SECRET, Family, _class, _family, _h, _join, _org, _teacher
from tests.test_school_api import _token as _school_token
from tests.test_sync_evidence import _attempt_delta

COMMENT = "Zara explains fractions with real food — keep it up."


@dataclass
class R:
    client: TestClient
    app: FastAPI
    teacher_a: dict[str, str]
    teacher_b: dict[str, str]
    class_a: str
    class_b: str
    fam: Family  # in class A
    loner: Family  # in no class at all
    start: int


@pytest.fixture
def r() -> R:
    return make_world()


def make_world() -> R:
    """The composed app with the written fractions lesson published, two schools, a family in
    class A and a learner in no class (also used by ``test_evidence_lesson_version.py``)."""
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    publish_written_lesson(app)
    client = TestClient(app)
    org_a, org_b = _org(client, "School A"), _org(client, "School B", "GB")
    ta = _teacher(client, org_a, "a1@school-a.example")
    tb = _teacher(client, org_b, "b1@school-b.example")
    class_a = _class(client, ta, "Grade 4 Blue")
    class_b = _class(client, tb, "Year 5 Red")
    fam = _family(client, "parent@example.com")
    loner = _family(client, "loner@example.com")
    assert _join(client, fam, class_a["join_code"]) == 200
    start = int(time.time()) - 3600
    return R(
        client, app, ta, tb, str(class_a["class_id"]), str(class_b["class_id"]), fam, loner, start
    )


def _closed_now() -> int:
    """A period end strictly after everything recorded so far, and not in the future."""
    time.sleep(1.02 - (time.time() % 1))
    return int(time.time())


def _attempts(r: R, fam: Family, n: int = 2, lesson_version: int | None = 1) -> None:
    """Offline attempts on the published lesson (its package was built from v1)."""
    deltas = [
        _attempt_delta(
            student=fam.student_ref,
            item_ref="p1-one-of-four",
            option=i % 2,
            client_event_id=uuid7(),
            evidence_id=uuid7(),
            client_seq=i + 1,
            lesson_version=lesson_version,
        )
        for i in range(n)
    ]
    sync = r.client.post(
        "/v1/sync/batch", json={"cursor": 0, "deltas": deltas}, headers=fam.learner
    )
    assert sync.status_code == 200, sync.text


def _marked_homework(r: R, outcome: str = "met") -> str:
    a = r.client.post(
        f"/v1/school/classes/{r.class_a}/assignments",
        json={"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() + 86400},
        headers=r.teacher_a,
    ).json()["assignment_id"]
    sub = r.client.post(
        f"/v1/school/learners/{r.fam.student_ref}/homework/{a}/items/hw-short:submit",
        json={"text": "one of four equal parts"},
        headers=r.fam.learner,
    ).json()["submission"]["submission_id"]
    marked = r.client.post(
        f"/v1/school/submissions/{sub}:mark", json={"outcome": outcome}, headers=r.teacher_a
    )
    assert marked.status_code == 200, marked.text
    return str(sub)


def _generate(r: R, fam: Family, end: int, start: int | None = None, headers: Any = None) -> Any:
    return r.client.post(
        f"/v1/reporting/children/{fam.student_ref}/report-cards:generate",
        json={"period_start": r.start if start is None else start, "period_end": end},
        headers=headers or fam.guardian,
    )


def _issue(r: R, end: int, path: str = "", teacher: Any = None, **extra: Any) -> Any:
    return r.client.post(
        f"/v1/reporting/classes/{r.class_a}/report-cards{path}",
        json={"period_start": r.start, "period_end": end, **extra},
        headers=teacher or r.teacher_a,
    )


def _rows(r: R) -> dict[str, int]:
    with r.app.state.reporting_session_factory() as s:
        return {
            m.__tablename__: int(s.scalar(select(func.count()).select_from(m)) or 0)
            for m in (ReportCardRow, ReportCardAuditRow, ReportCardOutboxRow)
        }


def _evidence_in(r: R, ref: str, start: int, end: int) -> tuple[int, int]:
    with r.app.state.learning_session_factory() as s:
        rows = s.scalars(
            select(AssessmentEvidenceRow).where(AssessmentEvidenceRow.student_ref == ref)
        ).all()
    auto = [
        e
        for e in rows
        if start <= e.occurred_at < end
        and e.context != "diagnostic"
        and not e.id.startswith("sub_")
    ]
    return len(auto), sum(1 for e in auto if e.outcome == "correct")


# ------------------------------------------------------------------ system issuance (primary)


def test_system_issues_a_card_for_a_learner_in_no_class(r: R) -> None:
    _attempts(r, r.loner, 3)
    end = _closed_now()
    made = _generate(r, r.loner, end)
    assert made.status_code == 201, made.text
    card = made.json()
    assert card["issued_by"] == "system" and card["issued_by_name"] == "Taleem"
    assert card["class_id"] is None and card["class_name"] is None and card["comment"] is None
    assert card["student_ref"] == r.loner.student_ref and card["learner_display_name"] == "Zara"
    assert card["period_start"] == r.start and card["period_end"] == end
    assert card["has_evidence"] is True and card["hash_verified"] is True
    assert card["status"] == "issued" and card["superseded_by"] is None
    assert card["acknowledged_at"] is None and len(card["content_hash"]) == 64
    (subject,) = card["subjects"]
    (obj,) = subject["objectives"]
    attempts, correct = _evidence_in(r, r.loner.student_ref, r.start, end)
    assert (obj["attempts"], obj["correct"]) == (attempts, correct) == (3, correct)
    assert obj["mastery"] in ("mastered", "developing")
    assert obj["lesson_id"] == LESSON_KEY and obj["lesson_version"] == 1
    assert obj["lesson_versions"] == [1] and obj["version_source"] == "evidence"
    assert card["curriculum_pack"] == "PK-NCP"
    assert set(subject["subject_name"]) == {"ur", "en"}

    # At most one system card per learner per identical period; another period is fine.
    again = _generate(r, r.loner, end)
    assert again.status_code == 409 and again.json()["code"] == "REPORT_CARD_EXISTS"
    assert _generate(r, r.loner, end, start=r.start - 60).status_code == 201
    listed = r.client.get(
        f"/v1/reporting/children/{r.loner.student_ref}/report-cards", headers=r.loner.guardian
    )
    assert [c["period_start"] for c in listed.json()["report_cards"]] == [r.start - 60, r.start]


def test_guardian_generate_is_scoped_validated_and_consent_gated(r: R) -> None:
    end = _closed_now()
    other = _family(r.client, "other@example.com")
    assert _generate(r, r.loner, end, headers=other.guardian).status_code == 404
    assert _generate(r, r.loner, end, headers=r.loner.learner).status_code == 403
    assert _generate(r, r.loner, end, headers=r.teacher_a).status_code == 403
    assert _generate(r, r.loner, end + 3600).status_code == 422  # not a closed period
    assert _generate(r, r.loner, end, start=end).status_code == 422  # start < end
    withdrawn = r.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": r.loner.student_ref},
        headers=r.loner.guardian,
    )
    assert withdrawn.status_code == 200
    refused = _generate(r, r.loner, end)
    assert refused.status_code == 403 and refused.json()["code"] == "LEARNER_NOT_ELIGIBLE"
    assert _rows(r)["report_card"] == 0


def test_a_card_with_no_evidence_says_so_and_shows_no_zeros(r: R) -> None:
    card = _generate(r, r.loner, _closed_now()).json()
    assert card["has_evidence"] is False and card["notice"] == "no_evidence_in_period"
    assert card["totals"] is None and card["subjects"] == []


def test_scheduler_cli_issues_every_eligible_learner_once(r: R) -> None:
    _attempts(r, r.fam, 1)
    end = _closed_now()
    out: list[str] = []
    argv = ["--start", str(r.start), "--end", str(end)]
    assert issue_due_main(argv, app_factory=lambda: r.app, out=out.append) == 0
    first = json.loads(out[-1])
    assert first["issued"] == 2 and first["already_issued"] == 0  # in a class or not
    assert issue_due_main(argv, app_factory=lambda: r.app, out=out.append) == 0
    again = json.loads(out[-1])
    assert again["issued"] == 0 and again["already_issued"] == 2
    future = ["--start", str(end), "--end", str(end + 999_999)]
    assert issue_due_main(future, app_factory=lambda: r.app, out=out.append) == 2
    assert month_period("2026-02") == (1769904000, 1772323200)
    with pytest.raises(SystemExit):
        issue_due_main(["--period", "Feb"], app_factory=lambda: r.app, out=out.append)
    with pytest.raises(SystemExit):
        issue_due_main([], app_factory=lambda: r.app, out=out.append)


# --------------------------------------------------------------------- teacher (optional)


def test_preview_stores_nothing_and_skips_with_reasons(r: R) -> None:
    _attempts(r, r.fam)
    end = _closed_now()
    before = _rows(r)
    pv = _issue(
        r,
        end,
        ":preview",
        student_refs=[r.fam.student_ref, r.loner.student_ref],
        comments={r.fam.student_ref: COMMENT},
    )
    assert pv.status_code == 200, pv.text
    body = pv.json()
    assert body["stored"] is False and _rows(r) == before == dict.fromkeys(before, 0)
    (card,) = body["report_cards"]
    assert card["card_id"] is None and card["status"] == "preview"
    assert card["comment"] == COMMENT and card["issued_by_name"] == "Ms Ayesha"
    assert card["class_name"] == "Grade 4 Blue" and len(card["content_hash"]) == 64
    assert body["skipped"] == [
        {"student_ref": r.loner.student_ref, "learner_display_name": None, "reason": "not_in_class"}
    ]


def test_teacher_issue_reconciles_audits_notifies_and_acknowledges_once(r: R) -> None:
    _attempts(r, r.fam, 3)
    sub = _marked_homework(r, "met")
    end = _closed_now()
    issued = _issue(r, end, comments={r.fam.student_ref: COMMENT})
    assert issued.status_code == 201, issued.text
    (card,) = issued.json()["report_cards"]
    assert issued.json()["skipped"] == []
    assert card["issued_by"] != "system" and card["comment"] == COMMENT
    obj = card["subjects"][0]["objectives"][0]
    attempts, correct = _evidence_in(r, r.fam.student_ref, r.start, end)
    # The homework mark's evidence is counted under homework, never as an auto-scored attempt.
    assert (obj["attempts"], obj["correct"]) == (attempts, correct) and attempts == 3
    assert (obj["homework_met"], obj["homework_not_yet"]) == (1, 0)
    assert card["totals"]["attempts"] == 3 and card["totals"]["homework_met"] == 1

    with r.app.state.reporting_session_factory() as s:
        events = s.scalars(select(ReportCardOutboxRow)).all()
        audit = s.scalars(select(ReportCardAuditRow)).all()
    assert [e.event_type for e in events] == ["ReportCardIssued"]
    assert events[0].payload["card_id"] == card["card_id"] and sub not in json.dumps(
        events[0].payload
    )
    assert [a.action for a in audit] == ["report_card.issued"]
    dump = json.dumps(
        [{c: getattr(a, c) for c in ("action", "actor_ref", "card_id")} for a in audit]
    )
    assert COMMENT not in dump and "Zara" not in dump

    notes_url = f"/v1/reporting/children/{r.fam.student_ref}/notifications"
    notes = r.client.get(notes_url, headers=r.fam.guardian).json()
    assert notes["unread"] == 1 and notes["notifications"][0]["card_id"] == card["card_id"]
    ack_url = f"/v1/reporting/report-cards/{card['card_id']}:acknowledge"
    assert r.client.post(ack_url, headers=r.loner.guardian).status_code == 404
    ack = r.client.post(ack_url, headers=r.fam.guardian)
    assert ack.status_code == 200 and ack.json()["acknowledged_at"] > 0
    second = r.client.post(ack_url, headers=r.fam.guardian)
    assert second.status_code == 409 and second.json()["code"] == "ALREADY_ACKNOWLEDGED"
    assert r.client.get(notes_url, headers=r.fam.guardian).json()["unread"] == 0
    read = r.client.get(f"/v1/reporting/report-cards/{card['card_id']}", headers=r.fam.guardian)
    assert read.json()["acknowledged_at"] == ack.json()["acknowledged_at"]
    with r.app.state.reporting_session_factory() as s:
        actions = s.scalars(select(ReportCardAuditRow.action)).all()
    assert sorted(actions) == ["report_card.acknowledged", "report_card.issued"]


def test_supersede_chain_and_conflicts(r: R) -> None:
    end = _closed_now()
    first = _issue(r, end).json()["report_cards"][0]
    skipped = _issue(r, end).json()
    assert skipped["report_cards"] == []
    assert skipped["skipped"][0]["reason"] == "already_issued"
    assert skipped["skipped"][0]["card_id"] == first["card_id"]
    fix = _issue(
        r,
        end,
        supersedes={r.fam.student_ref: first["card_id"]},
        comments={r.fam.student_ref: COMMENT},
    )
    assert fix.status_code == 201, fix.text
    second = fix.json()["report_cards"][0]
    assert second["supersedes"] == first["card_id"]
    stale = _issue(r, end, supersedes={r.fam.student_ref: first["card_id"]})
    assert stale.status_code == 409 and stale.json()["code"] == "ALREADY_SUPERSEDED"
    wrong = _issue(r, end, supersedes={r.fam.student_ref: "rpc_nope"})
    assert wrong.status_code == 422
    outsider = _issue(r, end, supersedes={r.loner.student_ref: first["card_id"]})
    assert outsider.status_code == 422
    cards = r.client.get(
        f"/v1/reporting/children/{r.fam.student_ref}/report-cards", headers=r.fam.guardian
    ).json()["report_cards"]
    assert [(c["card_id"], c["status"]) for c in cards] == [
        (second["card_id"], "issued"),
        (first["card_id"], "superseded"),
    ]
    assert cards[1]["superseded_by"] == second["card_id"] and cards[1]["comment"] is None
    notes = r.client.get(
        f"/v1/reporting/children/{r.fam.student_ref}/notifications", headers=r.fam.guardian
    ).json()
    assert [n["card_id"] for n in notes["notifications"]] == [second["card_id"]]
    listed = r.client.get(f"/v1/reporting/classes/{r.class_a}/report-cards", headers=r.teacher_a)
    assert len(listed.json()["report_cards"]) == 2


def test_issue_validation(r: R) -> None:
    end = _closed_now()
    assert _issue(r, end + 3600).status_code == 422
    assert _issue(r, end, comments={r.fam.student_ref: "x" * 1001}).status_code == 422
    assert _issue(r, end, comments={"stu_ghost": "hi"}, student_refs=[]).status_code == 422
    assert _issue(r, end, supersedes={"stu_ghost": "rpc_x"}).status_code == 422
    assert _issue(r, end, student_refs=["x" * 65]).status_code == 422
    assert _issue(r, end, unknown=1).status_code == 422
    assert _rows(r)["report_card"] == 0


def test_withdrawn_sharing_skips_the_learner(r: R) -> None:
    r.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": r.fam.student_ref, "scopes": ["progress_sharing"]},
        headers=r.fam.guardian,
    )
    body = _issue(r, _closed_now()).json()
    assert body["report_cards"] == []
    assert body["skipped"] == [
        {
            "student_ref": r.fam.student_ref,
            "learner_display_name": None,
            "reason": "consent_withdrawn",
        }
    ]


# ------------------------------------------------------------------------------ reads


def test_reads_are_relationship_scoped(r: R) -> None:
    end = _closed_now()
    card = _issue(r, end).json()["report_cards"][0]
    url = f"/v1/reporting/report-cards/{card['card_id']}"
    assert r.client.get(url, headers=r.fam.guardian).status_code == 200
    assert r.client.get(url, headers=r.teacher_a).status_code == 200
    assert r.client.get(url, headers=r.loner.guardian).status_code == 404
    assert r.client.get(url, headers=r.teacher_b).status_code == 404
    assert r.client.get(url, headers=r.fam.learner).status_code == 403
    assert (
        r.client.get("/v1/reporting/report-cards/rpc_none", headers=r.fam.guardian).status_code
        == 404
    )
    other_kid = f"/v1/reporting/children/{r.fam.student_ref}/report-cards"
    assert r.client.get(other_kid, headers=r.loner.guardian).status_code == 404
    pv = _issue(r, end, ":preview", teacher=r.teacher_b)
    assert pv.status_code == 404
    assert (
        r.client.get(
            f"/v1/reporting/classes/{r.class_a}/report-cards", headers=r.teacher_b
        ).status_code
        == 404
    )
    system = _h(_school_token("system", "ops"))
    assert r.client.get(url, headers=system).status_code == 403

    # The learner route: the learner themself, or a teacher of one of their classes.
    mine = f"/v1/reporting/learners/{r.fam.student_ref}/report-cards"
    own = r.client.get(mine, headers=r.fam.learner)
    assert own.status_code == 200 and own.json()["report_cards"][0]["card_id"] == card["card_id"]
    assert r.client.get(mine, headers=r.loner.learner).status_code == 403
    taught = r.client.get(mine, headers=r.teacher_a)
    assert [c["card_id"] for c in taught.json()["report_cards"]] == [card["card_id"]]
    assert r.client.get(mine, headers=r.teacher_b).status_code == 404
    assert r.client.get(mine, headers=r.fam.guardian).status_code == 403

    # A system card is not a class card: the teacher does not see it.
    _generate(r, r.fam, end)
    assert len(r.client.get(mine, headers=r.teacher_a).json()["report_cards"]) == 1
    assert len(r.client.get(mine, headers=r.fam.learner).json()["report_cards"]) == 2


def test_learner_route_is_consent_gated_and_halted_by_the_kill_switch(r: R) -> None:
    mine = f"/v1/reporting/learners/{r.fam.student_ref}/report-cards"
    assert r.client.get(mine, headers=r.fam.learner).status_code == 200
    system = _h(_school_token("system", "ops"))
    engaged = r.client.post("/v1/ops/kill-switch:engage", json={"reason": "drill"}, headers=system)
    assert engaged.status_code == 200
    assert r.client.get(mine, headers=r.fam.learner).status_code == 503
    r.client.post("/v1/ops/kill-switch:disengage", headers=system)
    r.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": r.fam.student_ref},
        headers=r.fam.guardian,
    )
    assert r.client.get(mine, headers=r.fam.learner).status_code == 403


def test_a_tampered_card_fails_re_verification(r: R) -> None:
    card = _generate(r, r.loner, _closed_now()).json()
    with r.app.state.reporting_session_factory() as s, s.begin():
        stored = s.get(ReportCardRow, card["card_id"])
        assert stored is not None
        forged = json.loads(stored.body)
        forged["has_evidence"] = True
        s.execute(
            update(ReportCardRow)
            .where(ReportCardRow.card_id == card["card_id"])
            .values(body=json.dumps(forged, sort_keys=True, separators=(",", ":")))
        )
    read = r.client.get(
        f"/v1/reporting/report-cards/{card['card_id']}", headers=r.loner.guardian
    ).json()
    assert read["hash_verified"] is False and read["content_hash"] == card["content_hash"]


def test_privacy_export_and_erasure_cover_report_cards(r: R) -> None:
    _attempts(r, r.fam, 1)
    end = _closed_now()
    card = _issue(r, end, comments={r.fam.student_ref: COMMENT}).json()["report_cards"][0]
    _generate(r, r.loner, end)
    ref = r.fam.student_ref
    export = r.client.get(f"/v1/privacy/learners/{ref}/export", headers=r.fam.guardian)
    assert export.status_code == 200, export.text
    section = export.json()["sections"]["reporting"]
    assert [c["card_id"] for c in section["report_cards"]] == [card["card_id"]]
    assert section["report_cards"][0]["body"]["comment"] == COMMENT
    assert section["report_cards"][0]["hash_verified"] is True
    assert len(section["report_card_audit"]) == 1 and len(section["report_card_events"]) == 1
    assert r.loner.student_ref not in json.dumps(section)

    token = r.client.post(
        f"/v1/privacy/learners/{ref}/erasure-requests", headers=r.fam.guardian
    ).json()["confirmation_token"]
    done = r.client.post(
        f"/v1/privacy/learners/{ref}/erasure:confirm",
        json={"confirmationToken": token},
        headers=r.fam.guardian,
    )
    assert done.status_code == 200, done.text
    assert done.json()["erased"]["reporting"] == {
        "report_card": 1,
        "report_card_audit": 1,
        "report_card_outbox": 1,
    }
    assert _rows(r) == {"report_card": 1, "report_card_audit": 1, "report_card_outbox": 1}
