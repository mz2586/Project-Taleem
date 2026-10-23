"""School / organization pilot minimum — end to end on the composed app.

Covers the journey (operator creates organizations and teachers → teacher creates a class →
guardian joins their learner with the class code → teacher assigns a published lesson → learner
practises → teacher sees completion and mastery), tenant isolation on EVERY teacher route, the
deny-by-default PDP, guardian-approved enrolment rules, and live loss of visibility on consent
withdrawal.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.school.adapters.persistence.uow import SqlSchoolUnitOfWork
from taleem_core.contexts.school.domain.model import TeacherStatus
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.ids import uuid7
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE
from tests.test_sync_evidence import _attempt_delta, _publish_fractions

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)
_TEACHER_PASS = "a-teacher-passphrase"  # noqa: S105 (test fixture)
_PIN = "4813"
_ATTEST = "I agree to share my child's progress with this class teacher."


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _token(role: str, sub: str) -> str:
    return sign_hs256({"sub": sub, "role": role, "exp": int(time.time()) + 3600}, _SECRET)


_SYSTEM = _h(_token("system", "ops"))


@dataclass
class Family:
    guardian: dict[str, str]
    student_ref: str
    learner: dict[str, str]


@dataclass
class World:
    client: TestClient
    app: FastAPI
    org_a: str
    org_b: str
    teacher_a: dict[str, str]
    teacher_a2: dict[str, str]
    teacher_b: dict[str, str]
    class_a: dict[str, object]
    class_b: dict[str, object]
    family: Family


def _org(client: TestClient, name: str, country: str = "PK") -> str:
    r = client.post(
        "/v1/school/organizations",
        json={
            "name": name,
            "country": country,
            "curriculumPackId": "pk-g4-math",
            "defaultLocale": "ur",
        },
        headers=_SYSTEM,
    )
    assert r.status_code == 201, r.text
    return str(r.json()["organization_id"])


def _teacher(client: TestClient, org: str, email: str) -> dict[str, str]:
    r = client.post(
        f"/v1/school/organizations/{org}/teachers",
        json={"email": email, "displayName": "Ms Ayesha", "passphrase": _TEACHER_PASS},
        headers=_SYSTEM,
    )
    assert r.status_code == 201, r.text
    s = client.post(
        "/v1/school/teachers:signin", json={"email": email, "passphrase": _TEACHER_PASS}
    )
    assert s.status_code == 200, s.text
    assert s.json()["session"]["role"] == "teacher"
    return _h(s.json()["session"]["access_token"])


def _class(client: TestClient, teacher: dict[str, str], name: str) -> dict[str, object]:
    r = client.post("/v1/school/classes", json={"name": name}, headers=teacher)
    assert r.status_code == 201, r.text
    return dict(r.json())


def _family(client: TestClient, email: str, scopes: list[str] | None = None) -> Family:
    reg = client.post(
        "/v1/identity/guardians",
        json={"email": email, "passphrase": _PASSPHRASE, "displayName": "Fatima"},
    )
    assert reg.status_code == 201, reg.text
    guardian = _h(reg.json()["session"]["access_token"])
    learner = client.post(
        "/v1/identity/learners",
        json={"displayName": "Zara", "pin": _PIN, "gradeLevel": 4},
        headers=guardian,
    )
    ref = str(learner.json()["student_ref"])
    consent = client.post(
        "/v1/identity/consents",
        json={"studentRef": ref, "scopes": scopes or ["learning_data"], "attestation": "I agree."},
        headers=guardian,
    )
    assert consent.status_code == 200, consent.text
    signin = client.post(
        "/v1/identity/learners:signin",
        json={
            "familyCode": reg.json()["guardian"]["family_code"],
            "displayName": "Zara",
            "pin": _PIN,
        },
    )
    assert signin.status_code == 200, signin.text
    return Family(guardian, ref, _h(signin.json()["session"]["access_token"]))


def _join(client: TestClient, fam: Family, code: object) -> int:
    r = client.post(
        "/v1/school/classes:join",
        json={"classCode": code, "studentRef": fam.student_ref, "attestation": _ATTEST},
        headers=fam.guardian,
    )
    return r.status_code


@pytest.fixture
def world() -> World:
    app = create_app(Settings(database_url="", kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    _publish_fractions(app)
    client = TestClient(app)
    org_a, org_b = _org(client, "School A"), _org(client, "School B", "GB")
    teacher_a = _teacher(client, org_a, "a1@school-a.example")
    teacher_a2 = _teacher(client, org_a, "a2@school-a.example")
    teacher_b = _teacher(client, org_b, "b1@school-b.example")
    class_a = _class(client, teacher_a, "Grade 4 Blue")
    class_b = _class(client, teacher_b, "Year 5 Red")
    fam = _family(client, "parent@example.com")
    assert _join(client, fam, class_a["join_code"]) == 200
    return World(client, app, org_a, org_b, teacher_a, teacher_a2, teacher_b, class_a, class_b, fam)


def _assign(w: World, teacher: dict[str, str], class_id: object) -> dict[str, object]:
    r = w.client.post(
        f"/v1/school/classes/{class_id}/assignments",
        json={"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() + 86400},
        headers=teacher,
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def _learners(w: World, teacher: dict[str, str], class_id: object) -> list[str]:
    r = w.client.get(f"/v1/school/classes/{class_id}", headers=teacher)
    assert r.status_code == 200, r.text
    return [x["student_ref"] for x in r.json()["learners"]]


# ----------------------------------------------------------------------------- the journey


def test_teacher_sees_completion_and_mastery_for_a_sharing_learner(world: World) -> None:
    w = world
    assert _learners(w, w.teacher_a, w.class_a["class_id"]) == [w.family.student_ref]
    assignment = _assign(w, w.teacher_a, w.class_a["class_id"])
    url = (
        f"/v1/school/classes/{w.class_a['class_id']}/assignments/"
        f"{assignment['assignment_id']}/progress"
    )
    before = w.client.get(url, headers=w.teacher_a).json()["learners"][0]
    assert before["completed"] is False and before["attempts_since_assigned"] == 0

    sync = w.client.post(
        "/v1/sync/batch",
        json={
            "cursor": 0,
            "deltas": [
                _attempt_delta(
                    student=w.family.student_ref,
                    item_ref="p1-one-of-four",
                    option=0,
                    client_event_id=uuid7(),
                    evidence_id=uuid7(),
                    client_seq=1,
                )
            ],
        },
        headers=w.family.learner,
    )
    assert sync.status_code == 200, sync.text

    body = w.client.get(url, headers=w.teacher_a).json()
    row = body["learners"][0]
    assert row["student_ref"] == w.family.student_ref
    assert row["display_name"] == "Zara"
    assert row["completed"] is True and row["attempts_since_assigned"] == 1
    assert isinstance(row["mastery"], float) and row["mastery"] > 0
    assert body["overdue"] is False
    listed = w.client.get(
        f"/v1/school/classes/{w.class_a['class_id']}/assignments", headers=w.teacher_a
    )
    assert [a["assignment_id"] for a in listed.json()["assignments"]] == [
        assignment["assignment_id"]
    ]


def test_join_records_progress_sharing_consent(world: World) -> None:
    w = world
    state = w.client.get(f"/v1/identity/consents/{w.family.student_ref}", headers=w.family.guardian)
    assert "progress_sharing" in state.json()["granted_scopes"]
    assert any(h["method"] == "class_join" for h in state.json()["history"])
    assert _join(w.client, w.family, w.class_a["join_code"]) == 200  # idempotent re-join
    assert _learners(w, w.teacher_a, w.class_a["class_id"]) == [w.family.student_ref]


# ------------------------------------------------------------------------- tenant isolation


def _teacher_routes(
    w: World, class_id: object, assignment_id: object
) -> list[tuple[str, str, dict[str, object] | None]]:
    return [
        ("GET", f"/v1/school/classes/{class_id}", None),
        ("GET", f"/v1/school/classes/{class_id}/assignments", None),
        (
            "POST",
            f"/v1/school/classes/{class_id}/assignments",
            {"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() + 3600},
        ),
        ("GET", f"/v1/school/classes/{class_id}/assignments/{assignment_id}/progress", None),
    ]


@pytest.mark.parametrize("intruder", ["teacher_b", "teacher_a2"])
def test_another_teacher_can_never_read_or_act_on_a_class(world: World, intruder: str) -> None:
    """Other organization (teacher_b) AND same organization, other teacher (teacher_a2)."""
    w = world
    assignment = _assign(w, w.teacher_a, w.class_a["class_id"])
    token = getattr(w, intruder)
    for method, path, body in _teacher_routes(
        w, w.class_a["class_id"], assignment["assignment_id"]
    ):
        r = w.client.request(method, path, json=body, headers=token)
        assert r.status_code == 404, (intruder, method, path, r.status_code)
        assert w.family.student_ref not in r.text
    # And their own class list never includes it.
    listed = w.client.get("/v1/school/classes", headers=token).json()["classes"]
    assert w.class_a["class_id"] not in [c["class_id"] for c in listed]
    # Nothing was written by the refused POST.
    own = w.client.get(
        f"/v1/school/classes/{w.class_a['class_id']}/assignments", headers=w.teacher_a
    )
    assert len(own.json()["assignments"]) == 1


def test_an_assignment_id_from_another_class_is_not_found(world: World) -> None:
    w = world
    foreign = _assign(w, w.teacher_b, w.class_b["class_id"])
    r = w.client.get(
        f"/v1/school/classes/{w.class_a['class_id']}/assignments/{foreign['assignment_id']}/progress",
        headers=w.teacher_a,
    )
    assert r.status_code == 404


def test_organization_reads_are_tenant_scoped(world: World) -> None:
    w = world
    assert (
        w.client.get(f"/v1/school/organizations/{w.org_a}", headers=w.teacher_a).status_code == 200
    )
    assert (
        w.client.get(f"/v1/school/organizations/{w.org_b}", headers=w.teacher_a).status_code == 404
    )
    assert (
        w.client.get(f"/v1/school/organizations/{w.org_a}", headers=w.teacher_b).status_code == 404
    )
    me = w.client.get("/v1/school/me", headers=w.teacher_b).json()
    assert me["organization"]["organization_id"] == w.org_b
    assert w.client.get(f"/v1/school/organizations/{w.org_b}", headers=_SYSTEM).status_code == 200


def test_each_teacher_lists_only_their_own_classes(world: World) -> None:
    w = world
    for token, expected in ((w.teacher_a, w.class_a), (w.teacher_b, w.class_b)):
        classes = w.client.get("/v1/school/classes", headers=token).json()["classes"]
        assert [c["class_id"] for c in classes] == [expected["class_id"]]
    assert w.client.get("/v1/school/classes", headers=w.teacher_a2).json()["classes"] == []


# ------------------------------------------------------------------- live consent visibility


def test_withdrawing_progress_sharing_hides_the_learner_on_the_next_request(world: World) -> None:
    w = world
    assignment = _assign(w, w.teacher_a, w.class_a["class_id"])
    progress = (
        f"/v1/school/classes/{w.class_a['class_id']}/assignments/"
        f"{assignment['assignment_id']}/progress"
    )
    assert len(w.client.get(progress, headers=w.teacher_a).json()["learners"]) == 1

    r = w.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": w.family.student_ref, "scopes": ["progress_sharing"]},
        headers=w.family.guardian,
    )
    assert r.status_code == 200
    # Same teacher token, very next request: gone from both views, and no trace of the ref.
    assert _learners(w, w.teacher_a, w.class_a["class_id"]) == []
    body = w.client.get(progress, headers=w.teacher_a)
    assert body.json()["learners"] == [] and w.family.student_ref not in body.text

    # The child can still learn: only the sharing scope was withdrawn.
    today = w.client.get(
        f"/v1/learning/students/{w.family.student_ref}/today", headers=w.family.learner
    )
    assert today.status_code == 200

    # Re-granting restores visibility without re-joining.
    regrant = w.client.post(
        "/v1/identity/consents",
        json={
            "studentRef": w.family.student_ref,
            "scopes": ["learning_data", "progress_sharing"],
            "attestation": _ATTEST,
        },
        headers=w.family.guardian,
    )
    assert regrant.status_code == 200
    assert _learners(w, w.teacher_a, w.class_a["class_id"]) == [w.family.student_ref]


def test_full_withdrawal_also_hides_the_learner(world: World) -> None:
    w = world
    w.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": w.family.student_ref},
        headers=w.family.guardian,
    )
    assert _learners(w, w.teacher_a, w.class_a["class_id"]) == []


# ---------------------------------------------------------------------- enrolment rules


def test_a_guardian_cannot_enrol_someone_elses_learner(world: World) -> None:
    w = world
    other = _family(w.client, "other@example.com")
    r = w.client.post(
        "/v1/school/classes:join",
        json={
            "classCode": w.class_b["join_code"],
            "studentRef": w.family.student_ref,
            "attestation": _ATTEST,
        },
        headers=other.guardian,
    )
    assert r.status_code == 404
    assert _learners(w, w.teacher_b, w.class_b["class_id"]) == []


def test_an_unknown_or_malformed_class_code_is_not_found(world: World) -> None:
    w = world
    assert _join(w.client, w.family, "ZZZZ-ZZZZ") == 404
    assert _join(w.client, w.family, "not a code") == 404


def test_joining_never_restores_a_withdrawn_learning_consent(world: World) -> None:
    w = world
    w.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": w.family.student_ref},
        headers=w.family.guardian,
    )
    r = w.client.post(
        "/v1/school/classes:join",
        json={
            "classCode": w.class_b["join_code"],
            "studentRef": w.family.student_ref,
            "attestation": _ATTEST,
        },
        headers=w.family.guardian,
    )
    assert r.status_code == 409 and r.json()["code"] == "CONSENT_REQUIRED"
    state = w.client.get(f"/v1/identity/consents/{w.family.student_ref}", headers=w.family.guardian)
    assert state.json()["permits_sign_in"] is False  # still withdrawn


def test_an_attestation_is_required_to_join(world: World) -> None:
    w = world
    r = w.client.post(
        "/v1/school/classes:join",
        json={
            "classCode": w.class_b["join_code"],
            "studentRef": w.family.student_ref,
            "attestation": "",
        },
        headers=w.family.guardian,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------- PDP: deny by default


def test_roles_are_denied_by_default(world: World) -> None:
    w = world
    org_body = {"name": "X", "country": "PK", "curriculumPackId": "p", "defaultLocale": "ur"}
    student = w.family.learner
    cases = [
        (w.teacher_a, "POST", "/v1/school/organizations", org_body),  # teacher cannot create orgs
        (w.family.guardian, "POST", "/v1/school/organizations", org_body),
        (student, "POST", "/v1/school/classes", {"name": "x"}),  # learners have no school role
        (student, "GET", f"/v1/school/classes/{w.class_a['class_id']}", None),
        (w.family.guardian, "GET", f"/v1/school/classes/{w.class_a['class_id']}", None),
        (_SYSTEM, "GET", f"/v1/school/classes/{w.class_a['class_id']}", None),  # no operator reads
        (
            w.teacher_a,
            "POST",
            "/v1/school/classes:join",
            {"classCode": "AAAA-AAAA", "studentRef": "x", "attestation": "y"},
        ),
        (
            w.teacher_a,
            "POST",
            f"/v1/school/organizations/{w.org_a}/teachers",
            {"email": "z@x.example", "displayName": "Z", "passphrase": _TEACHER_PASS},
        ),
    ]
    for headers, method, path, body in cases:
        r = w.client.request(method, path, json=body, headers=headers)
        assert r.status_code == 403, (method, path, r.status_code)
    assert w.client.get("/v1/school/classes").status_code == 401


def test_a_teacher_token_opens_no_learning_route(world: World) -> None:
    w = world
    ref = w.family.student_ref
    for path in (f"/v1/learning/students/{ref}/today", f"/v1/learning/students/{ref}/knowledge"):
        assert w.client.get(path, headers=w.teacher_a).status_code == 403, path


def test_a_suspended_teacher_loses_access_on_the_next_request(world: World) -> None:
    w = world
    me = w.client.get("/v1/school/me", headers=w.teacher_a).json()["teacher"]["teacher_ref"]
    with SqlSchoolUnitOfWork(w.app.state.school_session_factory) as uow:
        teacher = uow.teachers.get(me)
        assert teacher is not None
        teacher.status = TeacherStatus.SUSPENDED
        uow.teachers.save(teacher)
        uow.commit()
    r = w.client.get(f"/v1/school/classes/{w.class_a['class_id']}", headers=w.teacher_a)
    assert r.status_code == 403 and r.json()["code"] == "TEACHER_INACTIVE"


# ---------------------------------------------------------------------- validation + sign-in


def test_assignment_rules(world: World) -> None:
    w = world
    url = f"/v1/school/classes/{w.class_a['class_id']}/assignments"
    unpublished = w.client.post(
        url, json={"objectiveCode": "NOT.PUBLISHED", "dueAt": time.time() + 60}, headers=w.teacher_a
    )
    assert unpublished.status_code == 422 and unpublished.json()["code"] == "LESSON_NOT_PUBLISHED"
    past = w.client.post(
        url, json={"objectiveCode": OBJECTIVE_CODE, "dueAt": time.time() - 60}, headers=w.teacher_a
    )
    assert past.status_code == 422


def test_teacher_sign_in_fails_uniformly(world: World) -> None:
    w = world
    wrong = w.client.post(
        "/v1/school/teachers:signin", json={"email": "a1@school-a.example", "passphrase": "x" * 12}
    )
    unknown = w.client.post(
        "/v1/school/teachers:signin", json={"email": "nobody@x.example", "passphrase": "x" * 12}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"]


def test_organization_and_teacher_validation(world: World) -> None:
    w = world
    bad = w.client.post(
        "/v1/school/organizations",
        json={"name": "X", "country": "pk1", "curriculumPackId": "p", "defaultLocale": "ur"},
        headers=_SYSTEM,
    )
    assert bad.status_code == 422
    dup = w.client.post(
        f"/v1/school/organizations/{w.org_a}/teachers",
        json={"email": "A1@school-a.example", "displayName": "Dup", "passphrase": _TEACHER_PASS},
        headers=_SYSTEM,
    )
    assert dup.status_code == 409
    weak = w.client.post(
        f"/v1/school/organizations/{w.org_a}/teachers",
        json={"email": "new@school-a.example", "displayName": "W", "passphrase": "short"},
        headers=_SYSTEM,
    )
    assert weak.status_code == 422
    missing = w.client.post(
        "/v1/school/organizations/org_missing/teachers",
        json={"email": "n@x.example", "displayName": "N", "passphrase": _TEACHER_PASS},
        headers=_SYSTEM,
    )
    assert missing.status_code == 404


# ------------------------------------------------------------- guardian per-class control


def _child_classes(w: World, fam: Family) -> list[dict[str, object]]:
    r = w.client.get(f"/v1/school/children/{fam.student_ref}/classes", headers=fam.guardian)
    assert r.status_code == 200, r.text
    return list(r.json()["classes"])


def _leave(w: World, fam: Family, class_id: object, headers: dict[str, str] | None = None) -> int:
    r = w.client.post(
        f"/v1/school/children/{fam.student_ref}/classes/{class_id}:leave",
        headers=headers or fam.guardian,
    )
    return r.status_code


def test_guardian_lists_their_childs_classes(world: World) -> None:
    w = world
    assert _join(w.client, w.family, w.class_b["join_code"]) == 200
    rows = _child_classes(w, w.family)
    assert [r["class_id"] for r in rows] == [w.class_a["class_id"], w.class_b["class_id"]]
    first = rows[0]
    assert first["class_name"] == "Grade 4 Blue"
    assert first["organization_name"] == "School A"
    assert first["teacher_display_name"] == "Ms Ayesha"
    assert first["teacher_can_see_progress"] is True
    assert "join_code" not in first  # a guardian never learns a code they did not enter


def test_leaving_one_class_cuts_off_only_that_teacher(world: World) -> None:
    w = world
    assert _join(w.client, w.family, w.class_b["join_code"]) == 200
    assert _learners(w, w.teacher_b, w.class_b["class_id"]) == [w.family.student_ref]

    assert _leave(w, w.family, w.class_a["class_id"]) == 200
    # Teacher A loses the child on the next request; teacher B keeps them.
    assert _learners(w, w.teacher_a, w.class_a["class_id"]) == []
    assert _learners(w, w.teacher_b, w.class_b["class_id"]) == [w.family.student_ref]
    assert [c["class_id"] for c in _child_classes(w, w.family)] == [w.class_b["class_id"]]
    # progress_sharing is untouched: leaving a class is not a consent withdrawal.
    state = w.client.get(f"/v1/identity/consents/{w.family.student_ref}", headers=w.family.guardian)
    assert "progress_sharing" in state.json()["granted_scopes"]
    # Audited: who, which learner, which class.
    events = [e for e in w.app.state.school_audit.events() if e.action == "enrolment.left"]
    assert len(events) == 1
    assert (events[0].subject_ref, events[0].class_id) == (
        w.family.student_ref,
        w.class_a["class_id"],
    )
    assert events[0].actor_role == "guardian"
    # Leaving again is a 404 (nothing to leave); re-joining with the code restores visibility.
    assert _leave(w, w.family, w.class_a["class_id"]) == 404
    assert _join(w.client, w.family, w.class_a["join_code"]) == 200
    assert _learners(w, w.teacher_a, w.class_a["class_id"]) == [w.family.student_ref]


def test_progress_sharing_stays_the_master_switch(world: World) -> None:
    w = world
    assert _join(w.client, w.family, w.class_b["join_code"]) == 200
    w.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": w.family.student_ref, "scopes": ["progress_sharing"]},
        headers=w.family.guardian,
    )
    assert _learners(w, w.teacher_a, w.class_a["class_id"]) == []
    assert _learners(w, w.teacher_b, w.class_b["class_id"]) == []
    rows = _child_classes(w, w.family)
    assert len(rows) == 2 and all(r["teacher_can_see_progress"] is False for r in rows)


def test_guardian_b_cannot_list_or_leave_guardian_as_childs_classes(world: World) -> None:
    w = world
    other = _family(w.client, "other@example.com")
    ref = w.family.student_ref
    listed = w.client.get(f"/v1/school/children/{ref}/classes", headers=other.guardian)
    assert listed.status_code == 404 and str(w.class_a["class_id"]) not in listed.text
    assert _leave(w, w.family, w.class_a["class_id"], headers=other.guardian) == 404
    assert _learners(w, w.teacher_a, w.class_a["class_id"]) == [ref]  # nothing changed
    # Other roles are denied outright.
    for headers in (w.teacher_a, w.family.learner, _SYSTEM):
        r = w.client.get(f"/v1/school/children/{ref}/classes", headers=headers)
        assert r.status_code == 403
        assert _leave(w, w.family, w.class_a["class_id"], headers=headers) == 403


def test_leaving_a_class_the_child_is_not_in_is_not_found(world: World) -> None:
    w = world
    assert _leave(w, w.family, w.class_b["class_id"]) == 404


# ------------------------------------------------------------------ teacher lesson catalog


def test_teacher_lesson_catalog_is_titles_only_and_pack_scoped(world: World) -> None:
    w = world
    # The fixture lesson is authored against PK-NCP; neither fixture org uses that pack.
    assert w.client.get("/v1/school/lessons", headers=w.teacher_a).json()["lessons"] == []

    r = w.client.post(
        "/v1/school/organizations",
        json={
            "name": "PK School",
            "country": "PK",
            "curriculumPackId": "PK-NCP",
            "defaultLocale": "ur",
        },
        headers=_SYSTEM,
    )
    assert r.status_code == 201, r.text
    teacher = _teacher(w.client, str(r.json()["organization_id"]), "pk@school.example")
    lessons = w.client.get("/v1/school/lessons", headers=teacher).json()["lessons"]
    assert [x["objective_code"] for x in lessons] == [OBJECTIVE_CODE]
    assert set(lessons[0]) == {"objective_code", "title"}  # nothing beyond the title
    assert lessons[0]["title"].get("en")
    for role_headers in (w.family.guardian, w.family.learner):
        assert w.client.get("/v1/school/lessons", headers=role_headers).status_code == 403


# ------------------------------------------------------------- learner_count + teacher state


def _counts(w: World) -> dict[str, int]:
    classes = w.client.get("/v1/school/classes", headers=w.teacher_a).json()["classes"]
    return {c["class_id"]: c["learner_count"] for c in classes}


def test_class_list_counts_only_visible_learners(world: World) -> None:
    w = world
    second = _family(w.client, "second@example.com")
    assert _join(w.client, second, w.class_a["join_code"]) == 200
    assert _counts(w)[str(w.class_a["class_id"])] == 2
    w.client.post(
        "/v1/identity/consents:withdraw",
        json={"studentRef": second.student_ref, "scopes": ["progress_sharing"]},
        headers=second.guardian,
    )
    assert _counts(w)[str(w.class_a["class_id"])] == 1  # the hidden learner is not even counted


def test_locked_teacher_is_told_only_after_authentication(world: World) -> None:
    w = world
    me = w.client.get("/v1/school/me", headers=w.teacher_a2).json()["teacher"]["teacher_ref"]
    with SqlSchoolUnitOfWork(w.app.state.school_session_factory) as uow:
        t = uow.teachers.get(me)
        assert t is not None
        t.status = TeacherStatus.LOCKED  # the state 10 failed sign-ins produce (domain-tested)
        uow.teachers.save(t)
        uow.commit()
    # Sign-in stays uniform: a locked account with the RIGHT passphrase looks like an unknown one.
    locked = w.client.post(
        "/v1/school/teachers:signin",
        json={"email": "a2@school-a.example", "passphrase": _TEACHER_PASS},
    )
    unknown = w.client.post(
        "/v1/school/teachers:signin",
        json={"email": "nobody@x.example", "passphrase": _TEACHER_PASS},
    )
    assert locked.status_code == unknown.status_code == 401
    assert locked.json()["detail"] == unknown.json()["detail"]
    assert "code" not in locked.json() or locked.json()["code"] == unknown.json()["code"]
    # With a still-valid token, the state is named.
    r = w.client.get("/v1/school/classes", headers=w.teacher_a2)
    assert r.status_code == 403 and r.json()["code"] == "TEACHER_LOCKED"
