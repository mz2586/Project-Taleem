"""The in-app demo cohort (docs/03-security-privacy/DEMO_COHORT_CONTRACT.md), end to end.

One temporary database plays the real deployment: a real family in a real class with a real
teacher and a real published lesson, plus the reserved demo guardian created EARLIER through the
real API (as in production). The seeder (``tools/demo_cohort``) then runs twice with
``TALEEM_ENV=production`` and no demo credentials — it must adopt that guardian, never change its
passphrase or PIN, and change nothing on the second run.

Then, through the composed app in-process:

- **every learner/teacher read path** shows a real reader no demo lesson or item: offline package
  index + package, session ``:next`` / ``:teach`` / ``:answer`` / ``:hint``, placement, the student
  read models, the AI teacher plan, homework, the teacher catalogue and assignment, report-card
  derivation, the guardian portal, and offline sync — even with a forged ``cohort: "demo"`` claim;
- a demo reader sees the demo lessons (the cohort comes from the account);
- demo accounts are ordinary accounts: no privileged role, own family only, no cross-cohort class;
- no HTTP route can set a cohort;
- ``--erase`` removes the demo cohort and leaves every real account and lesson alone.
"""

from __future__ import annotations

import shutil
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    create_db_engine,
    create_session_factory,
    unit_of_work,
)
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.workflow import WorkflowState
from taleem_core.contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
from taleem_core.contexts.identity.domain.credentials import SecretHasher
from taleem_core.contexts.learning.adapters.curriculum_read_model import CurriculumStudioReadModel
from taleem_core.main import create_app
from taleem_core.platform.cohort import DEMO, REAL, reading_as
from taleem_core.platform.config import Settings
from taleem_core.tools import demo_cohort as ds
from taleem_core.tools.e2e_journey import FIXTURE_LESSON_ID, seed_fixture_lesson
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE as REAL_OBJECTIVE

_SECRET = "demo-cohort-test-jwt-secret-0123456789abcdef"  # noqa: S105 (test fixture)
DEMO_PASS = "the owner's demo passphrase 8812"  # noqa: S105 (synthetic test fixture)
DEMO_PIN = "4826"
REAL_PASS = "a real parent passphrase 5521"  # noqa: S105 (synthetic test fixture)
REAL_PIN = "7391"
TEACHER_PASS = "a real teacher passphrase 2650"  # noqa: S105 (synthetic test fixture)
DEMO_TEACHER_PASS = "the demo teacher passphrase 3307"  # noqa: S105 (synthetic test fixture)
REAL_EMAIL = "real.parent@example.com"
ATTEST = "I agree to share my child's progress with this class teacher."
HASHER = SecretHasher(iterations=1_000)
PROD_ENV = {"TALEEM_ENV": "production"}


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


_SYSTEM = _h(sign_hs256({"sub": "ops", "role": "system", "exp": int(time.time()) + 3600}, _SECRET))


@dataclass
class Family:
    guardian: dict[str, str]
    family_code: str
    student_ref: str
    learner: dict[str, str]
    learner_token: str


@dataclass
class World:
    url: str
    app: FastAPI
    client: TestClient
    first: dict[str, int]
    second: dict[str, int]
    real: Family
    real_teacher: dict[str, str]
    real_class_code: str
    demo_guardian_ref: str
    signed_in: dict[str, Any] = field(default_factory=dict)


def _guardian_signin(c: TestClient, email: str, passphrase: str) -> dict[str, Any]:
    r = c.post("/v1/identity/guardians:signin", json={"email": email, "passphrase": passphrase})
    assert r.status_code == 200, r.text
    return dict(r.json())


def _learner_signin(c: TestClient, family_code: str, name: str, pin: str) -> dict[str, Any]:
    r = c.post(
        "/v1/identity/learners:signin",
        json={"familyCode": family_code, "displayName": name, "pin": pin, "deviceId": "dev-t"},
    )
    assert r.status_code == 200, r.text
    return dict(r.json())


def _register_family(
    c: TestClient, email: str, passphrase: str, name: str, pin: str, scopes: list[str]
) -> Family:
    reg = c.post(
        "/v1/identity/guardians",
        # A client sending ``cohort`` is ignored: no route can set it (asserted below).
        json={"email": email, "passphrase": passphrase, "displayName": "Parent", "cohort": DEMO},
    )
    assert reg.status_code == 201, reg.text
    guardian = _h(reg.json()["session"]["access_token"])
    enrol = c.post(
        "/v1/identity/learners",
        json={"displayName": name, "pin": pin, "gradeLevel": 4, "cohort": DEMO},
        headers=guardian,
    )
    assert enrol.status_code == 201, enrol.text
    ref = str(enrol.json()["student_ref"])
    consent = c.post(
        "/v1/identity/consents",
        json={"studentRef": ref, "scopes": scopes, "attestation": "I agree."},
        headers=guardian,
    )
    assert consent.status_code == 200, consent.text
    code = str(reg.json()["guardian"]["family_code"])
    token = str(_learner_signin(c, code, name, pin)["session"]["access_token"])
    return Family(guardian, code, ref, _h(token), token)


def _org_teacher_class(
    c: TestClient, email: str, passphrase: str
) -> tuple[dict[str, str], dict[str, Any]]:
    org = c.post(
        "/v1/school/organizations",
        json={
            "name": "A real school",
            "country": "PK",
            "curriculumPackId": "PK-NCP",
            "defaultLocale": "ur",
        },
        headers=_SYSTEM,
    )
    assert org.status_code == 201, org.text
    org_id = org.json()["organization_id"]
    made = c.post(
        f"/v1/school/organizations/{org_id}/teachers",
        json={"email": email, "displayName": "Ms Real", "passphrase": passphrase},
        headers=_SYSTEM,
    )
    assert made.status_code == 201, made.text
    teacher = _h(_teacher_token(c, email, passphrase))
    klass = c.post("/v1/school/classes", json={"name": "Real class 4"}, headers=teacher)
    assert klass.status_code == 201, klass.text
    return teacher, dict(klass.json())


def _teacher_token(c: TestClient, email: str, passphrase: str) -> str:
    s = c.post("/v1/school/teachers:signin", json={"email": email, "passphrase": passphrase})
    assert s.status_code == 200, s.text
    return str(s.json()["session"]["access_token"])


def _join(c: TestClient, guardian: dict[str, str], student_ref: str, code: object) -> int:
    r = c.post(
        "/v1/school/classes:join",
        json={"classCode": code, "studentRef": student_ref, "attestation": ATTEST},
        headers=guardian,
    )
    return r.status_code


@pytest.fixture(scope="module")
def world(tmp_path_factory: pytest.TempPathFactory) -> Iterator[World]:
    url = f"sqlite:///{tmp_path_factory.mktemp('cohort') / 'taleem.db'}"
    app = create_app(Settings(database_url=url, kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    with TestClient(app) as client:
        assert seed_fixture_lesson(app.state.studio_session_factory) == "seeded"  # a REAL lesson
        # The demo guardian as production has it: created earlier through the real API.
        demo = _register_family(
            client, ds.GUARDIAN_EMAIL, DEMO_PASS, ds.LEARNER_NAME, DEMO_PIN, ["learning_data"]
        )
        me = client.get("/v1/identity/me", headers=demo.guardian).json()
        guardian_ref = str(me["guardian"]["guardian_ref"])
        real = _register_family(
            client, REAL_EMAIL, REAL_PASS, "Zara", REAL_PIN, ["learning_data", "progress_sharing"]
        )
        teacher, klass = _org_teacher_class(client, "ms.real@example.com", TEACHER_PASS)
        assert _join(client, real.guardian, real.student_ref, klass["join_code"]) == 200
        secrets = ds.DemoSecrets(teacher_passphrase=DEMO_TEACHER_PASS)  # no guardian/learner creds
        first = ds.seed_demo(url, secrets, env=PROD_ENV, hasher=HASHER)
        second = ds.seed_demo(url, secrets, env=PROD_ENV, hasher=HASHER)
        yield World(
            url, app, client, first, second, real, teacher, str(klass["join_code"]), guardian_ref
        )


def _demo_learner(w: World) -> tuple[dict[str, Any], dict[str, Any]]:
    """The demo guardian's and learner's sign-ins (once per module: sign-in is rate limited)."""
    if not w.signed_in:
        g = _guardian_signin(w.client, ds.GUARDIAN_EMAIL, DEMO_PASS)
        w.signed_in["guardian"] = g
        w.signed_in["learner"] = _learner_signin(
            w.client, str(g["guardian"]["family_code"]), ds.LEARNER_NAME, DEMO_PIN
        )
    return w.signed_in["guardian"], w.signed_in["learner"]


def _demo_lessons(url: str) -> list[Any]:
    engine = create_db_engine(url)
    try:
        with reading_as(DEMO):
            return [
                v
                for v in CurriculumStudioReadModel(
                    create_session_factory(engine)
                ).published_lessons()
                if v.lesson_id.startswith(ds.DEMO_LESSON_PREFIX)
            ]
    finally:
        engine.dispose()


DEMO_CODES = set(ds.DEMO_OBJECTIVES)


def _no_demo(text: str) -> None:
    """Nothing demo in a response a real reader receives."""
    assert ds.DEMO_LESSON_PREFIX not in text
    assert "[DEMO" not in text
    leaked = [code for code in DEMO_CODES if code in text]
    assert not leaked, leaked


# --------------------------------------------------------------------------------- the seed


def test_seed_adopts_the_existing_guardian_and_is_idempotent(world: World) -> None:
    s = world.first
    assert s["guardians_adopted"] == 1 and s["guardians_created"] == 1  # A adopted, B created
    assert s["learners_created"] == 1  # only family B's learner
    assert s["lessons_published"] == 12
    assert s["accounts_flagged_demo"] == 5  # guardian + learner, x2 families, + the teacher
    assert s["sessions_completed"] == 15 and s["sessions_in_progress"] == 1
    assert s["misconceptions_confirmed"] >= 1 and s["misconceptions_cleared"] >= 1
    assert s["placement_answers"] > 0
    assert s["assignments_created"] == 6 and s["submissions"] == 5
    assert s["submissions_marked"] == 3 and s["submissions_returned"] == 1
    assert s["report_cards_issued"] == 3 and s["report_cards_acknowledged"] == 1
    created = {k: v for k, v in world.second.items() if v and k.endswith(("_created", "_issued"))}
    assert created == {}
    assert world.second["lessons_already_present"] == 12
    assert world.second["accounts_flagged_demo"] == 0
    assert "answers" not in world.second and "submissions" not in world.second


def test_adopted_credentials_are_unchanged_and_tokens_carry_the_claim(world: World) -> None:
    g, learner = _demo_learner(world)  # the ORIGINAL passphrase and PIN still work
    assert g["guardian"]["guardian_ref"] == world.demo_guardian_ref
    for token in (g["session"]["access_token"], learner["session"]["access_token"]):
        claims = _payload(token)
        assert claims["cohort"] == DEMO
        assert claims["role"] in ("guardian", "student")  # ordinary roles, nothing privileged
    real_claims = _payload(world.real.learner_token)
    assert "cohort" not in real_claims


def _payload(token: str) -> dict[str, Any]:
    import base64
    import json

    part = token.split(".")[1]
    return dict(json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))))


def test_demo_lessons_are_labelled_unreviewed_demo_drafts(world: World) -> None:
    engine = create_db_engine(world.url)
    try:
        with unit_of_work(create_session_factory(engine)) as uow:
            studio = CurriculumStudioService(uow.lessons, uow.publish, hierarchy=uow.hierarchy)
            demo = [x for x in studio.list() if x.metadata.audience == DEMO]
            real = studio.get(FIXTURE_LESSON_ID)
    finally:
        engine.dispose()
    assert len(demo) == 12 and real.metadata.audience == REAL
    assert {x.metadata.subject_key for x in demo} == {
        "math",
        "urdu",
        "english",
        "science",
        "social_studies",
        "islamiat_ethics",
    }
    for lesson in demo:
        assert lesson.lesson_id.startswith(ds.DEMO_LESSON_PREFIX)
        assert lesson.workflow.state is WorkflowState.PUBLISHED
        assert set(lesson.title.text) == {"ur", "en"}
        assert all(t.startswith("[DEMO · unreviewed AI draft]") for t in lesson.title.text.values())
        assert ds.DEMO_TAG in lesson.metadata.tags
        assert lesson.offline_package.startswith(ds.PLACEHOLDER)
        assert all(
            ref.startswith(ds.PLACEHOLDER) for ref in lesson.student_explanation.audio_ref.values()
        )
        notes = [t.note for t in lesson.workflow.history if t.action.value == "approve"]
        assert notes and set(notes) == {ds.SYNTHETIC_APPROVAL}
        assert ds.SYNTHETIC_APPROVAL in lesson.workflow.history[-1].note  # the publish step
    kinds = {i.kind for v in _demo_lessons(world.url) for i in v.practice_items}
    assert {"fill", "order", "match", "sort"} <= kinds


# --------------------------------------------------------------------------------- real readers


def test_real_learner_offline_index_and_packages_hold_no_demo_lesson(world: World) -> None:
    c, h = world.client, world.real.learner
    index = c.get("/v1/offline/packages", headers=h)
    assert index.status_code == 200, index.text
    ids = {p["lesson_id"] for p in index.json()["packages"]}
    assert FIXTURE_LESSON_ID in ids
    _no_demo(index.text)
    demo_id = _demo_lessons(world.url)[0].lesson_id
    assert c.get(f"/v1/offline/packages/{demo_id}", headers=h).status_code == 404
    # The same index for a demo reader does list them (and the cache does not cross cohorts).
    _, learner = _demo_learner(world)
    demo_index = c.get("/v1/offline/packages", headers=_h(learner["session"]["access_token"]))
    assert demo_id in {p["lesson_id"] for p in demo_index.json()["packages"]}
    again = c.get("/v1/offline/packages", headers=h)
    _no_demo(again.text)


def _session(c: TestClient, h: dict[str, str], ref: str) -> str:
    r = c.post("/v1/learning/sessions", headers=h, json={"student_ref": ref})
    assert r.status_code == 201, r.text
    return str(r.json()["session_id"])


def test_real_learner_cannot_be_taught_or_answer_a_demo_lesson(world: World) -> None:
    c, h, ref = world.client, world.real.learner, world.real.student_ref
    lesson = _demo_lessons(world.url)[0]
    item = lesson.practice_items[0]
    sid = _session(c, h, ref)
    nxt = c.post(f"/v1/learning/sessions/{sid}:next", headers=h, json={})
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()["objective_code"] not in DEMO_CODES
    code = lesson.objective_code
    assert (
        c.post(
            f"/v1/learning/sessions/{sid}:teach", headers=h, json={"objective_code": code}
        ).status_code
        == 404
    )
    answer = c.post(
        f"/v1/learning/sessions/{sid}:answer",
        headers=h,
        json={"objective_code": code, "item_ref": item.item_ref, "option": 0},
    )
    assert answer.status_code == 404
    hint = c.post(
        f"/v1/learning/sessions/{sid}:hint",
        headers=h,
        json={"objective_code": code, "item_ref": item.item_ref, "hint_level": 0},
    )
    assert hint.status_code == 404
    # The real lesson is still taught.
    teach = c.post(
        f"/v1/learning/sessions/{sid}:teach", headers=h, json={"objective_code": REAL_OBJECTIVE}
    )
    assert teach.status_code == 200, teach.text
    _no_demo(teach.text)


def test_a_forged_demo_claim_does_not_open_demo_content(world: World) -> None:
    c, ref = world.client, world.real.student_ref
    forged = _h(
        sign_hs256(
            {"sub": ref, "role": "student", "cohort": DEMO, "exp": int(time.time()) + 600},
            _SECRET,
        )
    )
    code = _demo_lessons(world.url)[0].objective_code
    sid = _session(c, forged, ref)
    teach = c.post(
        f"/v1/learning/sessions/{sid}:teach", headers=forged, json={"objective_code": code}
    )
    assert teach.status_code == 404  # the cohort is read from the account, never the claim
    _no_demo(c.get("/v1/offline/packages", headers=forged).text)


def test_real_learner_placement_offers_no_demo_item(world: World) -> None:
    c, h, ref = world.client, world.real.learner, world.real.student_ref
    r = c.get(f"/v1/learning/students/{ref}/placement", headers=h)
    assert r.status_code == 200, r.text
    _no_demo(r.text)
    demo_item = _demo_lessons(world.url)[0].practice_items[0].item_ref
    answered = c.post(
        f"/v1/learning/students/{ref}/placement:answer",
        headers=h,
        json={"item_ref": demo_item, "option": 0},
    )
    assert answered.status_code in (404, 409, 422), answered.text


@pytest.mark.parametrize(
    "path",
    [
        "today",
        "homework",
        "assessments",
        "reviews",
        "timetable",
        "notifications",
        "achievements",
        "history",
        "recommendations",
    ],
)
def test_real_learner_student_read_models_hold_no_demo_lesson(world: World, path: str) -> None:
    ref = world.real.student_ref
    r = world.client.get(f"/v1/learning/students/{ref}/{path}", headers=world.real.learner)
    assert r.status_code == 200, r.text
    _no_demo(r.text)


def test_real_learner_ai_teacher_plan_and_school_homework_hold_no_demo(world: World) -> None:
    c, h, ref = world.client, world.real.learner, world.real.student_ref
    plan = c.get(f"/v1/learning/students/{ref}/ai-teacher/plan", headers=h)
    assert plan.status_code == 200, plan.text
    _no_demo(plan.text)
    homework = c.get(f"/v1/school/learners/{ref}/homework", headers=h)
    assert homework.status_code == 200, homework.text
    _no_demo(homework.text)


def test_real_teacher_catalogue_and_assignment_exclude_demo_lessons(world: World) -> None:
    c, teacher = world.client, world.real_teacher
    catalogue = c.get("/v1/school/lessons", headers=teacher)
    assert catalogue.status_code == 200, catalogue.text
    codes = {x["objective_code"] for x in catalogue.json()["lessons"]}
    assert REAL_OBJECTIVE in codes and not codes & DEMO_CODES
    classes = c.get("/v1/school/classes", headers=teacher).json()["classes"]
    class_id = classes[0]["class_id"]
    made = c.post(
        f"/v1/school/classes/{class_id}/assignments",
        headers=teacher,
        json={"objective_code": ds.DEMO_OBJECTIVES[0], "due_at": time.time() + 86_400},
    )
    assert made.status_code == 422 and made.json()["code"] == "LESSON_NOT_PUBLISHED"
    # The demo teacher's catalogue does carry them (cohort read from the teacher account).
    demo_teacher = _h(_teacher_token(c, ds.TEACHER_EMAIL, DEMO_TEACHER_PASS))
    demo_codes = {
        x["objective_code"]
        for x in c.get("/v1/school/lessons", headers=demo_teacher).json()["lessons"]
    }
    assert demo_codes >= DEMO_CODES


def test_real_report_card_derivation_holds_no_demo_lesson(world: World) -> None:
    c, ref = world.client, world.real.student_ref
    r = c.post(
        f"/v1/reporting/children/{ref}/report-cards:generate",
        headers=world.real.guardian,
        json={"period_start": 0, "period_end": int(time.time()) - 1},
    )
    assert r.status_code == 201, r.text
    _no_demo(r.text)


def test_real_guardian_portal_holds_no_demo(world: World) -> None:
    c, g, ref = world.client, world.real.guardian, world.real.student_ref
    for path in ("/v1/guardian/dashboard", f"/v1/guardian/children/{ref}"):
        r = c.get(path, headers=g)
        assert r.status_code == 200, r.text
        _no_demo(r.text)


def test_real_learner_cannot_sync_an_attempt_against_a_demo_item(world: World) -> None:
    c, ref = world.client, world.real.student_ref
    lesson = _demo_lessons(world.url)[0]
    item = lesson.practice_items[0]
    delta = {
        "clientEventId": "demo-probe-1",
        "type": "attempt.submitted",
        "entityKey": f"student:{ref}|lesson:{lesson.lesson_id}",
        "payload": {
            "student_ref": ref,
            "objective_code": lesson.objective_code,
            "item_ref": item.item_ref,
            "option": 0,
            "evidence_id": "demo-probe-evidence-1",
            "context": "practice",
        },
    }
    r = c.post("/v1/sync/batch", headers=world.real.learner, json={"deltas": [delta]})
    assert r.status_code == 200, r.text
    assert r.json()["results"][0]["status"] != "applied"
    knowledge = c.get(f"/v1/learning/students/{ref}/knowledge", headers=world.real.learner)
    if knowledge.status_code == 200:  # 404 = no knowledge at all, which also holds
        assert lesson.objective_code not in knowledge.json()["objectives"]
    else:
        assert knowledge.status_code == 404


# --------------------------------------------------------------------------------- demo readers


def test_demo_learner_is_taught_a_demo_lesson_and_has_history(world: World) -> None:
    c = world.client
    _, learner = _demo_learner(world)
    h, ref = _h(learner["session"]["access_token"]), str(learner["learner"]["student_ref"])
    sid = _session(c, h, ref)
    assert c.post(f"/v1/learning/sessions/{sid}:next", headers=h, json={}).status_code == 200
    code = "ENG-G4-RD-02"
    teach = c.post(f"/v1/learning/sessions/{sid}:teach", headers=h, json={"objective_code": code})
    assert teach.status_code == 200, teach.text
    item = teach.json()["items"][0]
    answered = c.post(
        f"/v1/learning/sessions/{sid}:hint",
        headers=h,
        json={"objective_code": code, "item_ref": item["item_ref"], "hint_level": 0},
    )
    assert answered.status_code == 200, answered.text
    knowledge = c.get(f"/v1/learning/students/{ref}/knowledge", headers=h).json()["objectives"]
    states = {knowledge[s.objective]["state"] for s in ds.SESSIONS}
    assert "mastered" in states and len(states) > 1  # mastered and still-developing lessons
    homework = c.get(f"/v1/school/learners/{ref}/homework", headers=h)
    assert homework.status_code == 200, homework.text
    entries = homework.json()["assignments"]
    assigned = [a for a in entries if a["source"] == "assignment"]
    states_hw = sorted(i["state"] for a in assigned for i in a["items"][:1])
    assert states_hw == sorted(
        ["marked", "marked", "marked", "returned", "submitted", "not_started"]
    )
    # Studied lessons no class assigned are self-paced homework (HOMEWORK_AND_MARKING §6).
    self_paced = [a for a in entries if a["source"] == "self_paced"]
    assert all(a["due_at"] is None and a["assignment_id"] is None for a in self_paced)
    assert not {a["objective_code"] for a in self_paced} & {a["objective_code"] for a in assigned}


def test_demo_guardian_sees_only_their_own_learner_and_report_cards(world: World) -> None:
    c = world.client
    g, learner = _demo_learner(world)
    gh, ref = _h(g["session"]["access_token"]), str(learner["learner"]["student_ref"])
    listed = c.get("/v1/identity/learners", headers=gh).json()["learners"]
    assert [x["display_name"] for x in listed] == [ds.LEARNER_NAME]
    dashboard = c.get("/v1/guardian/dashboard", headers=gh)
    assert dashboard.status_code == 200 and world.real.student_ref not in dashboard.text
    for path in (
        f"/v1/guardian/children/{world.real.student_ref}",
        f"/v1/reporting/children/{world.real.student_ref}/report-cards",
    ):
        assert c.get(path, headers=gh).status_code in (403, 404)
    cards = c.get(f"/v1/reporting/children/{ref}/report-cards", headers=gh).json()["report_cards"]
    assert {(x["period_start"], x["period_end"]) for x in cards} == {
        ds.SEPTEMBER,
        ds.EARLY_OCTOBER,
    }
    assert sum(1 for x in cards if x["acknowledged_at"] is not None) == 1
    # Family B (also demo) sees nothing of family A.
    with SqlIdentityUnitOfWork(world.app.state.identity_session_factory) as uow:
        guardian_b = uow.guardians.by_email(ds.GUARDIAN_B_EMAIL)
    assert guardian_b is not None and guardian_b.cohort == DEMO
    hb = _h(
        sign_hs256(
            {"sub": guardian_b.guardian_ref, "role": "guardian", "exp": int(time.time()) + 600},
            _SECRET,
        )
    )
    assert c.get(f"/v1/reporting/children/{ref}/report-cards", headers=hb).status_code == 404
    assert c.get(f"/v1/guardian/children/{ref}", headers=hb).status_code in (403, 404)


def test_demo_accounts_hold_no_privileged_role(world: World) -> None:
    c = world.client
    g, learner = _demo_learner(world)
    for token in (g["session"]["access_token"], learner["session"]["access_token"]):
        h = _h(token)
        assert c.get("/v1/studio/lessons", headers=h).status_code in (401, 403)
        assert c.get("/v1/safeguarding/concerns", headers=h).status_code in (401, 403, 405)
        org = c.post(
            "/v1/school/organizations",
            headers=h,
            json={
                "name": "x",
                "country": "PK",
                "curriculumPackId": "PK-NCP",
                "defaultLocale": "ur",
            },
        )
        assert org.status_code == 403
        assert c.post("/v1/ops/kill-switch:engage", headers=h, json={}).status_code in (403, 404)
    with SqlIdentityUnitOfWork(world.app.state.identity_session_factory) as uow:
        assert all(s.email != ds.GUARDIAN_EMAIL for s in uow.staff.all())


def test_classes_never_mix_cohorts(world: World) -> None:
    c = world.client
    g, learner = _demo_learner(world)
    gh, demo_ref = _h(g["session"]["access_token"]), str(learner["learner"]["student_ref"])
    # A demo learner cannot join a real class, answered exactly like a wrong code.
    assert _join(c, gh, demo_ref, world.real_class_code) == 404
    demo_teacher = _h(_teacher_token(c, ds.TEACHER_EMAIL, DEMO_TEACHER_PASS))
    demo_class = c.get("/v1/school/classes", headers=demo_teacher).json()["classes"][0]
    assert _join(c, world.real.guardian, world.real.student_ref, demo_class["join_code"]) == 404


# --------------------------------------------------------------------------------- no HTTP route


def test_no_http_route_can_set_a_cohort(world: World) -> None:
    for route in world.app.routes:
        body = getattr(route, "body_field", None)
        model = getattr(getattr(body, "field_info", None), "annotation", None) or getattr(
            body, "type_", None
        )
        if isinstance(model, type) and issubclass(model, BaseModel):
            names = set(model.model_fields) | {
                f.alias for f in model.model_fields.values() if f.alias
            }
            assert "cohort" not in names, getattr(route, "path", route)
    # The family registered above sent "cohort": "demo" in both bodies; it stayed real.
    with SqlIdentityUnitOfWork(world.app.state.identity_session_factory) as uow:
        real = uow.guardians.by_email(REAL_EMAIL)
        assert real is not None and real.cohort == REAL
        assert all(x.cohort == REAL for x in uow.learners.for_guardian(real.guardian_ref))


def test_read_model_choke_point_hides_demo_from_real_readers(world: World) -> None:
    engine = create_db_engine(world.url)
    try:
        model = CurriculumStudioReadModel(create_session_factory(engine))
        code = ds.DEMO_OBJECTIVES[0]
        for cohort, sees in ((REAL, False), (DEMO, True)):
            with reading_as(cohort):
                ids = {v.lesson_id for v in model.published_lessons()}
                assert (FIXTURE_LESSON_ID in ids) is True
                assert any(i.startswith(ds.DEMO_LESSON_PREFIX) for i in ids) is sees
                assert (model.lesson_for(code) is not None) is sees
                graph = {o.objective_code for o in model.published_graph().objectives}
                assert (code in graph) is sees
                catalog = {str(x["objective_code"]) for x in model.published_catalog()}
                assert (code in catalog) is sees
                versions = {str(x["objective_code"]) for x in model.published_versions()}
                assert (code in versions) is sees
                prints = {i for i, _ in model.published_fingerprints()}
                assert any(i.startswith(ds.DEMO_LESSON_PREFIX) for i in prints) is sees
        # Outside any request the reader is real.
        assert model.lesson_for(code) is None
    finally:
        engine.dispose()


# --------------------------------------------------------------------------------- removal


def test_erase_removes_the_demo_cohort_and_nothing_real(world: World, tmp_path: Path) -> None:
    source = Path(world.url.removeprefix("sqlite:///"))
    copy = tmp_path / "erase.db"
    shutil.copy(source, copy)
    url = f"sqlite:///{copy}"
    out = ds.erase_demo(url, env=PROD_ENV, hasher=HASHER)
    assert out["learners_erased"] == 2 and out["guardians_removed"] == 2
    assert out["teachers_suspended"] == 1 and out["lessons_unpublished"] == 12
    again = ds.erase_demo(url, env=PROD_ENV, hasher=HASHER)
    assert not {k: v for k, v in again.items() if v}
    from taleem_core.contexts.identity.adapters.persistence.base import (
        create_identity_engine,
        create_identity_session_factory,
    )

    engine = create_identity_engine(url)
    try:
        with SqlIdentityUnitOfWork(create_identity_session_factory(engine)) as uow:
            assert uow.guardians.by_email(ds.GUARDIAN_EMAIL) is None
            assert uow.guardians.by_email(ds.GUARDIAN_B_EMAIL) is None
            real = uow.guardians.by_email(REAL_EMAIL)
            assert real is not None and uow.learners.for_guardian(real.guardian_ref)
    finally:
        engine.dispose()
    with reading_as(DEMO):
        studio_engine = create_db_engine(url)
        try:
            ids = {
                v.lesson_id
                for v in CurriculumStudioReadModel(
                    create_session_factory(studio_engine)
                ).published_lessons()
            }
        finally:
            studio_engine.dispose()
    assert ids == {FIXTURE_LESSON_ID}


# --------------------------------------------------------------------------------- lesson titles


def test_real_learner_read_models_carry_real_titles_never_demo(world: World) -> None:
    c, h, ref = world.client, world.real.learner, world.real.student_ref
    today = c.get(f"/v1/learning/students/{ref}/today", headers=h)
    assert today.status_code == 200, today.text
    body = today.json()
    _no_demo(today.text)
    title = body["next_action"]["title"]
    assert body["next_action"]["objective_code"] == REAL_OBJECTIVE
    assert title and title["en"] and title["ur"]  # bilingual
    assert body["objective_titles"].get(REAL_OBJECTIVE, title) == title
    recs = c.get(f"/v1/learning/students/{ref}/recommendations", headers=h).json()
    assert all(r["title"] for r in recs["recommendations"])
    index = c.get("/v1/offline/packages", headers=h).json()["packages"]
    fixture = next(p for p in index if p["lesson_id"] == FIXTURE_LESSON_ID)
    assert fixture["title"]["en"] and fixture["title"]["ur"]
    assert not any("[DEMO" in v for p in index for v in p["title"].values())
    overview = c.get(f"/v1/guardian/children/{ref}", headers=world.real.guardian)
    assert overview.status_code == 200, overview.text
    titles = overview.json()["objective_titles"]
    assert REAL_OBJECTIVE in titles and not set(titles) & DEMO_CODES


def test_demo_learner_read_models_carry_the_demo_titles(world: World) -> None:
    c = world.client
    g, learner = _demo_learner(world)
    h, ref = _h(learner["session"]["access_token"]), str(learner["learner"]["student_ref"])
    body = c.get(f"/v1/learning/students/{ref}/today", headers=h).json()
    titles = body["objective_titles"]
    studied = {s.objective for s in ds.SESSIONS}
    assert studied <= set(titles)  # every objective the learner has a state for is named
    for code in studied:
        assert titles[code]["en"].startswith(ds.DEMO_TITLE_PREFIX)
        assert titles[code]["ur"].startswith(ds.DEMO_TITLE_PREFIX)
    index = c.get("/v1/offline/packages", headers=h).json()["packages"]
    demo = [p for p in index if p["lesson_id"].startswith(ds.DEMO_LESSON_PREFIX)]
    assert demo and all(p["title"]["en"].startswith(ds.DEMO_TITLE_PREFIX) for p in demo)
    gh = _h(g["session"]["access_token"])
    overview = c.get(f"/v1/guardian/children/{ref}", headers=gh).json()
    assert overview["objective_titles"][next(iter(studied))]["en"].startswith(ds.DEMO_TITLE_PREFIX)


def test_published_titles_choke_point_matches_cohort(world: World) -> None:
    engine = create_db_engine(world.url)
    try:
        model = CurriculumStudioReadModel(create_session_factory(engine))
        code = ds.DEMO_OBJECTIVES[0]
        with reading_as(REAL):
            real = model.published_titles()
        with reading_as(DEMO):
            demo = model.published_titles()
        assert REAL_OBJECTIVE in real and code not in real
        assert not any("[DEMO" in v for t in real.values() for v in t.values())
        assert demo[code]["en"].startswith(ds.DEMO_TITLE_PREFIX)
        assert model.published_titles() == real  # outside a request the reader is real
    finally:
        engine.dispose()
