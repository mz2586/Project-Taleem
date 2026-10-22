"""Studio review surface: lesson content in responses, answer-key exposure rules, the draft PATCH
route (If-Match optimistic locking), reviewer identity by token subject (self-approval blocked by
subject as well as role), and per-version lesson bodies.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import mapper, unit_of_work
from taleem_core.contexts.curriculum_studio.application.repository import (
    InMemoryLessonRepository,
    RecordingPublishPort,
)
from taleem_core.contexts.curriculum_studio.application.service import (
    CurriculumStudioService,
    StudioError,
)
from taleem_core.contexts.curriculum_studio.domain.content import Locale
from taleem_core.contexts.curriculum_studio.domain.lesson import Lesson
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from tests.studio_helpers import make_valid_lesson

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
AUTHOR = "staff-author-1"
REVIEWERS = [
    ("subject_expert", "staff-se-1"),
    ("instructional_designer", "staff-id-1"),
    ("a11y_specialist", "staff-a11y-1"),
    ("language_editor", "staff-lang-1"),
    ("safety_officer", "staff-safety-1"),
]
ANSWER_FIELDS = ("answer_key", "accepted_variants", "auto_marking_guidance")


def _auth(role: str, sub: str) -> dict[str, str]:
    token = sign_hs256({"sub": sub, "role": role, "exp": int(time.time()) + 3600}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


AUTHOR_H = _auth("subject_author", AUTHOR)
ARCHITECT_H = _auth("curriculum_architect", "staff-arch-1")


def _lesson(lesson_id: str = "R1") -> Lesson:
    lesson = make_valid_lesson(lesson_id)
    lesson.metadata.author_subject = AUTHOR
    lesson.metadata.tags = ["provisional", "imported-from:grade-4"]
    q = lesson.practice_questions[0]
    q.answer_key = {"correct": "3"}
    q.accepted_variants = ["three"]
    q.auto_marking_guidance = "accept 3 or three"
    lesson.assessment.formative[0].answer_key = {"correct": "2"}
    return lesson


def _app_with(*lessons: Lesson) -> tuple[Any, TestClient]:
    app = create_app(Settings(database_url=""))  # private in-memory store
    with unit_of_work(app.state.studio_session_factory) as uow:
        svc = CurriculumStudioService(uow.lessons, uow.publish)
        for lesson in lessons:
            svc.create(lesson)
        uow.commit()
    return app, TestClient(app)


def _answer_fields(value: Any) -> list[str]:
    """Every answer field found anywhere in a JSON value."""
    found: list[str] = []
    if isinstance(value, dict):
        found += [k for k in value if k in ANSWER_FIELDS]
        for v in value.values():
            found += _answer_fields(v)
    elif isinstance(value, list):
        for v in value:
            found += _answer_fields(v)
    return found


def _drive_to_published(c: TestClient, lesson_id: str) -> None:
    assert c.post(f"/v1/studio/lessons/{lesson_id}:submit", json={}, headers=AUTHOR_H).is_success
    for role, sub in REVIEWERS:
        r = c.post(
            f"/v1/studio/lessons/{lesson_id}:review",
            json={"action": "approve"},
            headers=_auth(role, sub),
        )
        assert r.status_code == 200, r.text
    r = c.post(
        f"/v1/studio/lessons/{lesson_id}:publish",
        json={"change_summary": "v1"},
        headers=ARCHITECT_H,
    )
    assert r.status_code == 200, r.text


# =============================================================================================
# 1. Content in responses; answer keys only on single GET for reviewer/architect roles
# =============================================================================================


def test_list_exposes_content_but_never_answer_keys() -> None:
    _, c = _app_with(_lesson())
    for headers in (AUTHOR_H, ARCHITECT_H, _auth("subject_expert", "staff-se-1")):
        lessons = c.get("/v1/studio/lessons", headers=headers).json()["lessons"]
        view = lessons[0]
        assert _answer_fields(view) == []
        assert view["answer_keys_included"] is False
    assert view["metadata"]["tags"] == ["provisional", "imported-from:grade-4"]
    assert view["metadata"]["author_role"] == "subject_author"
    assert view["metadata"]["author_subject"] == AUTHOR
    assert view["provenance"]["derivation"] == "authored-original"
    assert view["student_explanation"]["text"]["en"] == "We count. One. Two. Three."
    assert view["teacher_script"]["text"]["ur"]
    q = view["practice_questions"][0]
    assert q["item_id"] == "p1" and q["stem"]["text"]["en"] == "Count."
    assert view["hints"][0]["hint"]["text"]["en"] == "Count again."
    assert view["common_misconceptions"][0]["misconception"]["text"]["en"] == "double-count"
    assert view["homework"][0]["item_id"] == "h1"
    assert view["workflow"] == {"state": "draft", "history": []}
    assert view["title"] == {"ur": "گنتی", "en": "Counting"}
    assert "version_history" not in view


def test_single_get_answer_keys_by_role() -> None:
    _, c = _app_with(_lesson())
    for role in (*(r for r, _ in REVIEWERS), "curriculum_architect"):
        r = c.get("/v1/studio/lessons/R1", headers=_auth(role, "staff-x"))
        body = r.json()
        assert body["answer_keys_included"] is True, role
        assert body["practice_questions"][0]["answer_key"] == {"correct": "3"}
        assert body["practice_questions"][0]["accepted_variants"] == ["three"]
        assert body["assessment"]["formative"][0]["answer_key"] == {"correct": "2"}
    # The author role (and anything not a reviewer/architect) gets the content without keys.
    body = c.get("/v1/studio/lessons/R1", headers=AUTHOR_H).json()
    assert body["answer_keys_included"] is False
    assert _answer_fields(body) == []
    assert body["practice_questions"][0]["stem"]["text"]["en"] == "Count."


def test_mutation_responses_never_carry_answer_keys() -> None:
    _, c = _app_with(_lesson())
    r = c.post("/v1/studio/lessons/R1:submit", json={}, headers=AUTHOR_H)
    assert r.status_code == 200 and _answer_fields(r.json()) == []
    r = c.post(
        "/v1/studio/lessons/R1:review",
        json={"action": "approve"},
        headers=_auth("subject_expert", "staff-se-1"),
    )
    assert r.status_code == 200 and _answer_fields(r.json()) == []


# =============================================================================================
# 2. PATCH a draft (author only, draft only, If-Match)
# =============================================================================================


def _etag(c: TestClient, lesson_id: str = "R1") -> str:
    r = c.get(f"/v1/studio/lessons/{lesson_id}", headers=AUTHOR_H)
    assert r.headers["ETag"] == r.json()["etag"]
    return str(r.headers["ETag"])


def test_patch_updates_a_draft_with_locale_generic_fields() -> None:
    _, c = _app_with(_lesson())
    tag = _etag(c)
    r = c.patch(
        "/v1/studio/lessons/R1",
        json={
            "title": {"en": "Counting to ten", "ur": ""},  # "" removes that locale
            "student_explanation": {"en": "We count to ten."},
            "tags": ["provisional", "edited"],
            "keywords": ["count"],
            "estimated_duration_min": 20,
            "difficulty": "developing",
        },
        headers={**AUTHOR_H, "If-Match": tag},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["title"] == {"en": "Counting to ten"}
    assert body["student_explanation"]["text"] == {
        "ur": "ہم گنتے ہیں۔ ایک۔ دو۔ تین۔",
        "en": "We count to ten.",
    }
    assert body["metadata"]["tags"] == ["provisional", "edited"]
    assert body["metadata"]["author_subject"] == AUTHOR  # authorship never re-attributed
    assert body["estimated_duration_min"] == 20 and body["difficulty"] == "developing"
    assert r.headers["ETag"] == body["etag"] != tag
    # Persisted: a fresh read (new unit of work) sees the edit.
    again = c.get("/v1/studio/lessons/R1", headers=AUTHOR_H).json()
    assert again["title"] == {"en": "Counting to ten"} and again["etag"] == body["etag"]


def test_patch_preconditions() -> None:
    _, c = _app_with(_lesson())
    url = "/v1/studio/lessons/R1"
    r = c.patch(url, json={"tags": ["x"]}, headers=AUTHOR_H)
    assert r.status_code == 428 and r.json()["code"] == "PRECONDITION_REQUIRED"
    r = c.patch(url, json={"tags": ["x"]}, headers={**AUTHOR_H, "If-Match": '"stale"'})
    assert r.status_code == 412 and r.json()["code"] == "PRECONDITION_FAILED"
    tag = _etag(c)
    ok = c.patch(url, json={"tags": ["x"]}, headers={**AUTHOR_H, "If-Match": f"W/{tag}"})
    assert ok.status_code == 200
    # The old ETag is now stale: a second writer holding it is refused.
    r = c.patch(url, json={"tags": ["y"]}, headers={**AUTHOR_H, "If-Match": tag})
    assert r.status_code == 412
    missing = c.patch("/v1/studio/lessons/nope", json={}, headers={**AUTHOR_H, "If-Match": tag})
    assert missing.status_code == 404


@pytest.mark.parametrize(
    ("body", "status", "code"),
    [
        ({"title": {"fr": "Compter"}}, 422, "BAD_LOCALE"),
        ({"summary": {"Not A Tag": "x"}}, 422, "BAD_LOCALE"),
        ({"instructional_locales": ["EN"]}, 422, "BAD_LOCALE"),
        ({"title": {"ur": "", "en": ""}}, 422, "BAD_LOCALE"),
        ({"title": {"ur": "a"}, "title_ur": "b"}, 422, "BAD_LOCALE"),
        ({"difficulty": "impossible"}, 422, "BAD_DIFFICULTY"),
        ({"answer_key": {"x": 1}}, 422, None),  # unknown fields are refused
    ],
)
def test_patch_rejects_invalid_input(body: dict[str, Any], status: int, code: str | None) -> None:
    _, c = _app_with(_lesson())
    r = c.patch("/v1/studio/lessons/R1", json=body, headers={**AUTHOR_H, "If-Match": _etag(c)})
    assert r.status_code == status, r.text
    if code is not None:
        assert r.json()["code"] == code


def test_patch_is_author_only_and_draft_only() -> None:
    _, c = _app_with(_lesson())
    tag = _etag(c)
    for headers in (_auth("subject_expert", "staff-se-1"), ARCHITECT_H):
        r = c.patch(
            "/v1/studio/lessons/R1", json={"tags": ["x"]}, headers={**headers, "If-Match": tag}
        )
        assert r.status_code == 403
    c.post("/v1/studio/lessons/R1:submit", json={}, headers=AUTHOR_H)
    r = c.patch(
        "/v1/studio/lessons/R1", json={"tags": ["x"]}, headers={**AUTHOR_H, "If-Match": _etag(c)}
    )
    assert r.status_code == 422
    assert "only draft lessons can be edited" in r.json()["detail"]


# =============================================================================================
# 3. Reviewer identity by token subject
# =============================================================================================


def test_self_approval_is_refused_by_subject_even_with_a_reviewer_role() -> None:
    _, c = _app_with(_lesson())
    c.post("/v1/studio/lessons/R1:submit", json={}, headers=AUTHOR_H)
    # The author holds a second, reviewer token: same person, different role. Refused.
    r = c.post(
        "/v1/studio/lessons/R1:review",
        json={"action": "approve"},
        headers=_auth("subject_expert", AUTHOR),
    )
    assert r.status_code == 422
    assert "no self-approval" in r.json()["detail"]
    r = c.post(
        "/v1/studio/lessons/R1:review",
        json={"action": "request_changes"},
        headers=_auth("subject_expert", AUTHOR),
    )
    assert r.status_code == 422
    # A different person with that role may.
    r = c.post(
        "/v1/studio/lessons/R1:review",
        json={"action": "approve"},
        headers=_auth("subject_expert", "staff-se-1"),
    )
    assert r.status_code == 200


def test_transitions_and_gates_record_subjects_and_survive_reload() -> None:
    _, c = _app_with(_lesson())
    _drive_to_published(c, "R1")
    body = c.get("/v1/studio/lessons/R1", headers=ARCHITECT_H).json()  # fresh unit of work
    history = body["workflow"]["history"]
    # Compared as a set: rows written within one clock tick may load in either order.
    assert sorted((h["action"], h["actor_role"], h["actor_subject"]) for h in history) == sorted(
        [
            ("submit", "subject_author", AUTHOR),
            *[("approve", role, sub) for role, sub in REVIEWERS],
            ("publish", "curriculum_architect", "staff-arch-1"),
        ]
    )
    human = {g["gate"]: g for g in body["gates"] if g["mode"] == "human"}
    assert human["technical_accuracy"]["reviewer_subject"] == "staff-se-1"
    assert human["educational_review"]["reviewer_subject"] == "staff-id-1"
    assert human["ai_safety"]["reviewer_subject"] == "staff-safety-1"
    assert all(g["reviewer_subject"] == "" for g in body["gates"] if g["mode"] == "auto")


def test_service_blocks_the_submitter_when_no_author_subject_was_recorded() -> None:
    svc = CurriculumStudioService(InMemoryLessonRepository(), RecordingPublishPort())
    svc.create(make_valid_lesson("S1"))  # legacy lesson: no author_subject
    svc.submit("S1", "subject_author", actor_subject="staff-9")
    with pytest.raises(StudioError, match="no self-approval"):
        svc.review("S1", ReviewAction.APPROVE, "subject_expert", actor_subject="staff-9")
    svc.review("S1", ReviewAction.APPROVE, "subject_expert", actor_subject="staff-10")
    # The role rule still applies with no subjects at all.
    lesson = make_valid_lesson("S2")
    lesson.metadata.author_role = "subject_expert"
    svc.create(lesson)
    svc.submit("S2", "subject_author")
    with pytest.raises(StudioError, match="no self-approval"):
        svc.review("S2", ReviewAction.APPROVE, "subject_expert")


def test_update_keeps_the_recorded_author() -> None:
    svc = CurriculumStudioService(InMemoryLessonRepository(), RecordingPublishPort())
    svc.create(_lesson("U1"))
    edited = _lesson("U1")
    edited.metadata.author_subject = "someone-else"
    assert svc.update(edited).metadata.author_subject == AUTHOR


def test_identity_bookkeeping_does_not_change_the_content_hash() -> None:
    a, b = _lesson(), _lesson()
    b.metadata.author_subject = "another"
    assert a.content_hash() == b.content_hash()


def test_mapper_restores_identities_whatever_the_row_order() -> None:
    lesson = _lesson()
    svc = CurriculumStudioService(InMemoryLessonRepository(), RecordingPublishPort())
    svc.create(lesson)
    svc.submit("R1", "subject_author", actor_subject=AUTHOR)
    svc.review("R1", ReviewAction.APPROVE, "subject_expert", actor_subject="staff-se-1")
    body = mapper.to_body(svc.get("R1"))
    identity = body[mapper.IDENTITY_KEY]
    assert identity["transitions"] == [
        ["draft", "subject_expert", "submit", AUTHOR],
        ["subject_expert", "educational_qa", "approve", "staff-se-1"],
    ]
    assert identity["gates"]["technical_accuracy"] == "staff-se-1"


# =============================================================================================
# 4. Per-version lesson bodies
# =============================================================================================


def test_version_body_is_served_for_diffing_with_the_answer_key_rule() -> None:
    _, c = _app_with(_lesson())
    _drive_to_published(c, "R1")
    versions = c.get("/v1/studio/lessons/R1/versions", headers=AUTHOR_H).json()["versions"]
    assert [v["version"] for v in versions] == [1]
    assert "body" not in versions[0]

    v1 = c.get("/v1/studio/lessons/R1/versions/1", headers=ARCHITECT_H).json()
    assert v1["version"] == 1 and v1["content_hash"] == versions[0]["content_hash"]
    assert v1["body"]["title"]["text"] == {"ur": "گنتی", "en": "Counting"}
    assert v1["body"]["metadata"]["tags"] == ["provisional", "imported-from:grade-4"]
    assert "version_history" not in v1["body"]
    assert v1["answer_keys_included"] is True
    assert v1["body"]["practice_questions"][0]["answer_key"] == {"correct": "3"}

    as_author = c.get("/v1/studio/lessons/R1/versions/1", headers=AUTHOR_H).json()
    assert as_author["answer_keys_included"] is False
    assert _answer_fields(as_author["body"]) == []
    assert c.get("/v1/studio/lessons/R1/versions/9", headers=AUTHOR_H).status_code == 404
    assert c.get("/v1/studio/lessons/nope/versions/1", headers=AUTHOR_H).status_code == 404


def test_version_snapshot_does_not_nest_prior_versions() -> None:
    svc = CurriculumStudioService(InMemoryLessonRepository(), RecordingPublishPort())
    svc.create(_lesson("V1"))
    svc.submit("V1", "subject_author", actor_subject=AUTHOR)
    for role, sub in REVIEWERS:
        svc.review("V1", ReviewAction.APPROVE, role, actor_subject=sub)
    svc.publish("V1", "curriculum_architect", "v1", actor_subject="staff-arch-1")
    snapshot = svc.get("V1").version_history.get(1)
    assert snapshot is not None
    assert "version_history" not in snapshot.snapshot
    assert snapshot.snapshot["metadata"]["author_subject"] == AUTHOR
    assert snapshot.snapshot["title"]["text"][Locale.EN] == "Counting"
