"""Learning side of ITEM_INTERACTION_CONTRACT.md §2-§4: projection, answers, scoring, secrecy."""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from dataclasses import replace
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from taleem_core.auth.dependencies import bearer_claims
from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.domain.assessment import (
    AssessmentItem,
    Competency,
    ItemType,
)
from taleem_core.contexts.curriculum_studio.domain.content import Hint, Locale, LocalizedText
from taleem_core.contexts.curriculum_studio.domain.lesson import Lesson
from taleem_core.contexts.learning.adapters.api import (
    LearningApiDeps,
    build_learning_router,
    learner_item,
)
from taleem_core.contexts.learning.adapters.curriculum_read_model import (
    CurriculumStudioReadModel,
)
from taleem_core.contexts.learning.adapters.persistence.base import (
    LearningBase,
    create_learning_engine,
    create_learning_session_factory,
)
from taleem_core.contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from taleem_core.contexts.learning.adapters.placement_api import build_placement_router
from taleem_core.contexts.learning.application.placement_service import PlacementService
from taleem_core.contexts.learning.application.sync_consumer import SyncEvidenceConsumer
from taleem_core.contexts.learning.domain.curriculum_view import (
    SECRET_ITEM_FIELDS,
    ItemView,
    LessonView,
)
from taleem_core.contexts.learning.domain.decision import CurriculumGraph, ObjectiveInfo
from taleem_core.contexts.learning.domain.estimator import BKTEstimator
from taleem_core.contexts.learning.domain.forgetting import HalfLifeForgettingModel
from taleem_core.contexts.learning.domain.offline_package import build_package
from taleem_core.contexts.learning.domain.scorer import (
    Answer,
    AnswerKindMismatchError,
    AnswerShapeError,
    answer_fits,
    evaluate,
    normalize,
)
from taleem_core.contexts.learning.domain.values import Outcome
from taleem_core.contexts.sync.domain import DeltaType, Status, SyncDelta
from taleem_core.platform.errors import Problem
from taleem_core.vertical_slice import runner
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)

# ----------------------------------------------------------------------------- fixtures

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_STUDENT = "kinds-stu"
M_FILL, M_ORDER, M_PAIRS = "m-fill-digits", "m-order-sizes", "m-pair-halves"


def _auth(sub: str = _STUDENT) -> dict[str, str]:
    token = sign_hs256({"sub": sub, "role": "student", "exp": int(time.time()) + 3600}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


def _loc(ur: str, en: str) -> LocalizedText:
    return LocalizedText(text={Locale.UR: ur, Locale.EN: en})


def _studio_item(
    item_id: str,
    kind: ItemType,
    key: dict[str, object],
    options: list[str] | None = None,
    variants: list[str] | None = None,
) -> AssessmentItem:
    return AssessmentItem(
        item_id=item_id,
        type=kind,
        objective_ref=OBJECTIVE_CODE,
        competency=Competency.APPLICATION,
        stem=_loc(f"سوال {item_id}", f"Question {item_id}"),
        answer_key=key,
        accepted_variants=variants or [],
        options=[_loc(f"ا {o}", o) for o in options or []],
        hints=[Hint(trigger="wrong", hint=_loc("سوچیں۔", "Think again."))],
    )


ACTIVITIES = [
    _studio_item(
        "a-fill",
        ItemType.FILL_BLANK,
        {"answer": "1,000", "misconception": M_FILL},
        variants=["one thousand"],
    ),
    _studio_item(
        "a-order",
        ItemType.ORDERING,
        {"order": [1, 2, 0], "misconception": M_ORDER},
        ["1/2", "1/8", "1/4"],
    ),
    _studio_item(
        "a-match",
        ItemType.MATCHING,
        {"left_count": 2, "pairs": [[0, 3], [1, 2]], "misconception": M_PAIRS},
        ["half", "quarter", "1/4", "1/2"],
    ),
    _studio_item(
        "a-sort",
        ItemType.INTERACTIVE,
        {"mode": "sort", "left_count": 3, "pairs": [[0, 3], [1, 4], [2, 3]]},
        ["1/2", "3/4", "2/4", "equals a half", "more than a half"],
    ),
    _studio_item("a-widget", ItemType.INTERACTIVE, {"descriptive": "drag the clock hands"}),
    _studio_item("a-human", ItemType.SHORT, {}),
]


def _kinds_lesson() -> Lesson:
    lesson = build_fractions_lesson()
    lesson.interactive_activities = [*lesson.interactive_activities, *ACTIVITIES]
    return lesson


@pytest.fixture
def lesson_view() -> LessonView:
    model = CurriculumStudioReadModel(None)  # type: ignore[arg-type]  # _project needs no store
    return model._project(_kinds_lesson(), OBJECTIVE_CODE)  # noqa: SLF001


@pytest.fixture
def wiring(monkeypatch: pytest.MonkeyPatch) -> runner.SliceWiring:
    monkeypatch.setattr(runner, "build_fractions_lesson", _kinds_lesson)
    w = runner.wire(runner._make_clock())  # noqa: SLF001
    assert w.gates_green
    return w


def _app(*routers: Any) -> TestClient:
    app = FastAPI()

    @app.exception_handler(Problem)
    async def _problem(request: Request, exc: Problem) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.to_dict(str(request.url.path)))

    for r in routers:
        app.include_router(r)
    return TestClient(app)


@pytest.fixture
def client(wiring: runner.SliceWiring) -> TestClient:
    deps = LearningApiDeps(
        session_service=wiring.session_service,
        knowledge_service=wiring.knowledge_service,
        analytics=wiring.analytics,
        curriculum=wiring.read_model,
    )
    return _app(build_learning_router(deps, bearer_claims(_SECRET)))


def _assert_no_secrets(blob: object, view: LessonView) -> None:
    """No secret field name, and no fill answer, anywhere in a learner-facing document."""
    text = json.dumps(blob, ensure_ascii=False)
    for name in SECRET_ITEM_FIELDS:
        assert f'"{name}"' not in text, name
    for item in view.practice_items:
        for answer in item.accepted_answers:
            assert answer not in text, answer
    assert '"pairs"' not in text and '"answer_key"' not in text


# ------------------------------------------------------------------------- normalization


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("۴۰", "40"),  # Urdu digits
        ("٤٠", "40"),  # Arabic-Indic digits
        ("١٬٢٣٤", "1234"),  # Arabic thousands separator between digits
        ("1,000", "1000"),
        ("۱,۰۰۰", "1000"),
        ("a, b", "a, b"),  # a comma not between digits stays
        ("  Forty   Two  ", "forty two"),  # trim, collapse, casefold
        ("STRASSE", "strasse"),
        ("ﬁve", "five"),  # NFKC ligature
        ("４０", "40"),  # NFKC full-width digits
        ("آدھا۔", "آدھا"),  # Urdu full stop
        ("half!", "half"),
        ("half?", "half"),
        ("half . ", "half"),
        ("half.!?", "half"),
        ("1.5", "1.5"),  # an inner point is kept
        ("", ""),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


# ------------------------------------------------------------------------------- scoring


def _choose() -> ItemView:
    return ItemView(
        "c", "O", {"en": "?"}, ("a", "b", "c"), correct_option=1, option_misconceptions={2: "m-c"}
    )


def test_choose_scoring_and_int_compat() -> None:
    item = _choose()
    assert evaluate(item, 1) == (Outcome.CORRECT, ())
    assert evaluate(item, Answer(option=1)) == (Outcome.CORRECT, ())
    assert evaluate(item, 2) == (Outcome.INCORRECT, ("m-c",))
    assert evaluate(item, 0) == (Outcome.INCORRECT, ())
    # The item-level misconception is the fallback after option_misconceptions.
    fallback = replace(item, misconception="m-any")
    assert evaluate(fallback, 0) == (Outcome.INCORRECT, ("m-any",))
    assert evaluate(fallback, 2) == (Outcome.INCORRECT, ("m-c",))


def test_fill_scoring() -> None:
    item = ItemView(
        "f", "O", {"en": "?"}, kind="fill", accepted_answers=("40", "Forty"), misconception="m-f"
    )
    for given in ("40", "۴۰", "٤٠", " 40. ", "forty", "FORTY!", "Forty۔"):
        assert evaluate(item, Answer(text=given))[0] is Outcome.CORRECT, given
    assert evaluate(item, Answer(text="41")) == (Outcome.INCORRECT, ("m-f",))
    assert evaluate(item, Answer(text="   ")) == (Outcome.INCORRECT, ("m-f",))
    big = replace(item, accepted_answers=("1,000",))
    assert evaluate(big, Answer(text="۱۰۰۰"))[0] is Outcome.CORRECT
    assert evaluate(big, Answer(text="1٬000"))[0] is Outcome.CORRECT
    # No accepted answer projected (a non-canonical key): nothing is correct.
    assert evaluate(replace(item, accepted_answers=()), Answer(text=""))[0] is Outcome.INCORRECT


def test_order_scoring() -> None:
    item = ItemView("o", "O", {"en": "?"}, ("x", "y", "z"), kind="order", correct_order=(2, 0, 1))
    assert evaluate(item, Answer(order=(2, 0, 1))) == (Outcome.CORRECT, ())
    assert evaluate(item, Answer(order=(0, 1, 2))) == (Outcome.INCORRECT, ())
    assert evaluate(item, Answer(order=(2, 0))) == (Outcome.INCORRECT, ())
    assert evaluate(replace(item, correct_order=()), Answer(order=()))[0] is Outcome.INCORRECT


@pytest.mark.parametrize("kind", ["match", "sort"])
def test_pairs_scoring(kind: str) -> None:
    item = ItemView(
        "m",
        "O",
        {"en": "?"},
        ("a", "b", "1", "2"),
        kind=kind,
        left_count=2,
        correct_pairs=frozenset({(0, 3), (1, 2)}),
        misconception="m-p",
    )
    assert evaluate(item, Answer(pairs=((1, 2), (0, 3)))) == (Outcome.CORRECT, ())  # any order
    assert evaluate(item, Answer(pairs=((0, 2), (1, 3)))) == (Outcome.INCORRECT, ("m-p",))
    assert evaluate(item, Answer(pairs=((0, 3),))) == (Outcome.INCORRECT, ("m-p",))  # no partial
    assert evaluate(item, Answer(pairs=((0, 3), (1, 2), (1, 3))))[0] is Outcome.INCORRECT
    empty = replace(item, correct_pairs=frozenset())
    assert evaluate(empty, Answer(pairs=()))[0] is Outcome.INCORRECT


@pytest.mark.parametrize(
    ("kind", "answer"),
    [
        ("choose", Answer(text="1")),
        ("fill", Answer(option=0)),
        ("order", Answer(pairs=((0, 1),))),
        ("match", Answer(order=(0, 1))),
        ("sort", Answer(text="x")),
        ("widget", Answer(option=0)),  # an unknown kind fits no answer
    ],
)
def test_mismatched_answer_raises(kind: str, answer: Answer) -> None:
    item = ItemView("i", "O", {"en": "?"}, ("a", "b"), kind=kind)
    assert not answer_fits(item, answer)
    with pytest.raises(AnswerKindMismatchError):
        evaluate(item, answer)


def test_answer_shape() -> None:
    with pytest.raises(AnswerShapeError):
        Answer()
    with pytest.raises(AnswerShapeError):
        Answer(option=1, text="1")
    with pytest.raises(AnswerShapeError):
        Answer(text="x" * 201)
    with pytest.raises(AnswerShapeError):
        Answer(order=tuple(range(65)))
    assert Answer(text="x" * 200).field == "text"
    assert Answer(option=2).summary() == "2"
    assert Answer(text="۴۰").summary() == "۴۰"
    assert Answer(order=(1, 0)).summary() == "1,0"
    assert Answer(pairs=((0, 3), (1, 2))).summary() == "0-3,1-2"


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"option": 2}, Answer(option=2)),
        ({"option": 2, "text": None}, Answer(option=2)),  # None counts as absent
        ({"text": "۴۰"}, Answer(text="۴۰")),
        ({"order": [1, 0]}, Answer(order=(1, 0))),
        ({"pairs": [[0, 3], [1, 2]]}, Answer(pairs=((0, 3), (1, 2)))),
        ({"pairs": []}, Answer(pairs=())),
    ],
)
def test_answer_from_payload(payload: dict[str, object], expected: Answer) -> None:
    assert Answer.from_payload(payload) == expected


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"option": 1, "text": "1"},
        {"option": True},
        {"option": "1"},
        {"option": 1.5},
        {"text": 40},
        {"order": "1,0"},
        {"order": [1, "0"]},
        {"order": [True, 0]},
        {"pairs": [[0, 1, 2]]},
        {"pairs": [0, 1]},
        {"pairs": "0-1"},
        {"text": "x" * 201},
    ],
)
def test_answer_from_payload_rejects(payload: dict[str, object]) -> None:
    with pytest.raises(AnswerShapeError):
        Answer.from_payload(payload)


# ---------------------------------------------------------------------------- projection


def test_projection_puts_playable_activities_first_and_skips_widgets(
    lesson_view: LessonView,
) -> None:
    refs = [i.item_ref for i in lesson_view.practice_items]
    assert refs[:5] == ["a1-shade-quarter", "a-fill", "a-order", "a-match", "a-sort"]
    assert refs[5:] == [q.item_id for q in build_fractions_lesson().practice_questions]
    assert "a-widget" not in refs and "a-human" not in refs
    assert lesson_view.activity_count == 5
    assert [i.item_ref for i in lesson_view.practice_questions] == refs[5:]


def test_projection_of_each_kind(lesson_view: LessonView) -> None:
    by = {i.item_ref: i for i in lesson_view.practice_items}
    assert by["p1-one-of-four"].kind == "choose" and by["p1-one-of-four"].left_count == 0
    fill = by["a-fill"]
    assert (fill.kind, fill.options, fill.left_count) == ("fill", (), 0)
    assert fill.accepted_answers == ("1,000", "one thousand")
    assert fill.misconception == M_FILL
    order = by["a-order"]
    assert (order.kind, order.correct_order) == ("order", (1, 2, 0))
    assert order.options == ("1/2", "1/8", "1/4")
    match = by["a-match"]
    assert (match.kind, match.left_count) == ("match", 2)
    assert match.correct_pairs == frozenset({(0, 3), (1, 2)})
    sort = by["a-sort"]
    assert (sort.kind, sort.left_count, len(sort.options)) == ("sort", 3, 5)
    assert sort.correct_pairs == frozenset({(0, 3), (1, 4), (2, 3)})
    assert sort.misconception == ""
    assert all(i.playable for i in lesson_view.practice_items)


def test_projection_tolerates_malformed_keys() -> None:
    bad = [
        _studio_item("b-order", ItemType.ORDERING, {"order": [0, "1"]}, ["x", "y"]),
        _studio_item("b-match", ItemType.MATCHING, {"left_count": 1, "pairs": [[0]]}, ["x", "y"]),
        _studio_item("b-sort", ItemType.INTERACTIVE, {"mode": "sort", "pairs": "x"}, ["x", "y"]),
        _studio_item("b-fill", ItemType.FILL_BLANK, {"misconception": 3}),
    ]
    lesson = build_fractions_lesson()
    lesson.interactive_activities = bad
    view = CurriculumStudioReadModel(None)._project(lesson, OBJECTIVE_CODE)  # type: ignore[arg-type]  # noqa: SLF001, E501
    by = {i.item_ref: i for i in view.practice_items}
    assert by["b-order"].correct_order == ()
    assert by["b-match"].correct_pairs == frozenset()
    assert by["b-sort"].correct_pairs == frozenset() and by["b-sort"].left_count == 0
    assert by["b-fill"].accepted_answers == () and by["b-fill"].misconception == ""
    assert not by["b-fill"].playable


# ------------------------------------------------------------------------------- secrecy


def test_learner_item_and_offline_package_carry_no_secret(lesson_view: LessonView) -> None:
    items = [learner_item(i) for i in lesson_view.practice_items]
    assert {i["kind"] for i in items} == {"choose", "fill", "order", "match", "sort"}
    assert all(
        set(i) == {"item_ref", "kind", "left_count", "prompt", "options", "hint_count"}
        for i in items
    )  # noqa: E501
    _assert_no_secrets(items, lesson_view)

    package = build_package(lesson_view, now_ms=1).to_dict()
    _assert_no_secrets(package, lesson_view)
    content = package["content"]
    assert isinstance(content, dict)
    offline = {i["item_ref"]: i for i in content["practice_items"]}
    assert offline["a-match"]["kind"] == "match" and offline["a-match"]["left_count"] == 2
    assert offline["a-fill"]["options"] == [] and offline["a-fill"]["kind"] == "fill"
    assert set(offline["a-sort"]) == {
        "item_ref",
        "objective_code",
        "kind",
        "left_count",
        "prompt",
        "options",
        "hints",
    }


def test_offline_hash_depends_on_kind(lesson_view: LessonView) -> None:
    # A changed kind is a content change: the package version moves, so caches invalidate.
    first = lesson_view.practice_items[0]
    other = replace(lesson_view, practice_items=(replace(first, kind="order"),))
    same = replace(lesson_view, practice_items=(first,))
    assert build_package(other, now_ms=1).manifest.version != (
        build_package(same, now_ms=1).manifest.version
    )


# ----------------------------------------------------------------------- session API (e2e)

_RIGHT: dict[str, dict[str, object]] = {
    "a1-shade-quarter": {"option": 0},
    "a-fill": {"text": "۱٬۰۰۰۔"},
    "a-order": {"order": [1, 2, 0]},
    "a-match": {"pairs": [[1, 2], [0, 3]]},
    "a-sort": {"pairs": [[0, 3], [1, 4], [2, 3]]},
}
_WRONG: dict[str, tuple[dict[str, object], str | None]] = {
    "a-fill": ({"text": "100"}, M_FILL),
    "a-order": ({"order": [0, 1, 2]}, M_ORDER),
    "a-match": ({"pairs": [[0, 2], [1, 3]]}, M_PAIRS),
    "a-sort": ({"pairs": [[0, 4], [1, 4], [2, 3]]}, None),
}


def _taught(client: TestClient) -> tuple[str, dict[str, Any]]:
    sid = client.post("/v1/learning/sessions", json={"student_ref": _STUDENT}, headers=_auth())
    session_id = sid.json()["session_id"]
    assert client.post(f"/v1/learning/sessions/{session_id}:next", headers=_auth()).status_code
    taught = client.post(
        f"/v1/learning/sessions/{session_id}:teach",
        json={"objective_code": OBJECTIVE_CODE},
        headers=_auth(),
    )
    assert taught.status_code == 200
    return session_id, taught.json()


def _answer(client: TestClient, session_id: str, ref: str, body: dict[str, object]) -> Any:
    return client.post(
        f"/v1/learning/sessions/{session_id}:answer",
        json={"objective_code": OBJECTIVE_CODE, "item_ref": ref, **body},
        headers=_auth(),
    )


def test_session_answers_one_item_of_each_kind(client: TestClient) -> None:
    session_id, taught = _taught(client)
    items = {i["item_ref"]: i for i in taught["items"]}
    assert [i["item_ref"] for i in taught["items"]][:5] == list(_RIGHT)
    assert items["a-sort"]["kind"] == "sort" and items["a-sort"]["left_count"] == 3
    assert items["a-fill"]["options"] == []
    assert items["p1-one-of-four"]["kind"] == "choose"

    for ref, (body, misconception) in _WRONG.items():
        r = _answer(client, session_id, ref, body)
        assert r.status_code == 200, r.text
        assert r.json()["outcome"] == "incorrect", ref
        if misconception is None:
            assert r.json()["feedback"] == []
    for ref, body in _RIGHT.items():
        r = _answer(client, session_id, ref, body)
        assert r.status_code == 200, r.text
        assert r.json()["outcome"] == "correct", ref
    # The pre-contract body still works for a choose item.
    assert _answer(client, session_id, "p1-one-of-four", {"option": 0}).json()["outcome"] == (
        "correct"
    )


@pytest.mark.parametrize(
    ("ref", "body"),
    [
        ("p1-one-of-four", {"text": "1/4"}),  # choose answered by text
        ("a-fill", {"option": 0}),
        ("a-order", {"pairs": [[0, 1]]}),
        ("a-match", {"order": [0, 1]}),
        ("a-sort", {"text": "x"}),
        ("a-fill", {}),  # no answer field
        ("a-fill", {"text": "1", "option": 1}),  # two answer fields
        ("a-fill", {"text": "x" * 201}),
        ("a-order", {"order": "1,2,0"}),
        ("a-match", {"pairs": [[0, 1, 2]]}),
    ],
)
def test_session_answer_422s(client: TestClient, ref: str, body: dict[str, object]) -> None:
    session_id, _ = _taught(client)
    assert _answer(client, session_id, ref, body).status_code == 422


def test_service_answer_requires_exactly_one_shape(wiring: runner.SliceWiring) -> None:
    svc = wiring.session_service
    session = svc.start(_STUDENT)
    decision = svc.plan_next(session)
    _, lesson = svc.teach(session, decision)
    item = lesson.practice_items[0]
    with pytest.raises(ValueError, match="exactly one"):
        svc.submit_answer(
            session, lesson, item, decision_kind=decision.kind, hints_used=0, self_confidence=None
        )
    turn = svc.submit_answer(
        session,
        lesson,
        item,
        answer_option=0,
        decision_kind=decision.kind,
        hints_used=0,
        self_confidence=None,
    )
    assert turn.result.outcome is Outcome.CORRECT


# ----------------------------------------------------------------------------- placement


@pytest.fixture
def placement(wiring: runner.SliceWiring) -> Iterator[tuple[TestClient, PlacementService]]:
    engine = create_learning_engine("sqlite://")
    LearningBase.metadata.create_all(engine)
    sf = create_learning_session_factory(engine)
    graph = CurriculumGraph(objectives=(ObjectiveInfo(OBJECTIVE_CODE, LESSON_KEY, (), 0),))
    service = PlacementService(lambda: LearningUnitOfWork(sf), wiring.read_model, graph, time.time)
    yield _app(build_placement_router(service, bearer_claims(_SECRET))), service
    engine.dispose()


def test_placement_item_json_and_answer_shapes(
    placement: tuple[TestClient, PlacementService],
) -> None:
    client, service = placement
    url = f"/v1/learning/students/{_STUDENT}/placement"
    nxt = client.get(url, headers=_auth()).json()["next_item"]
    assert set(nxt) == {"item_ref", "objective_code", "kind", "left_count", "prompt", "options"}
    assert nxt["kind"] == "choose"
    ref = nxt["item_ref"]
    for bad in ({"text": "1"}, {}, {"option": 0, "order": [0]}, {"option": -1}):
        r = client.post(f"{url}:answer", json={"item_ref": ref, **bad}, headers=_auth())
        assert r.status_code == 422, bad
        assert "correct_option" not in r.text
    ok = client.post(f"{url}:answer", json={"item_ref": ref, "option": 0}, headers=_auth())
    assert ok.status_code == 200
    _assert_no_secrets(ok.json(), service._content()[1][OBJECTIVE_CODE])  # noqa: SLF001
    with pytest.raises(ValueError, match="exactly one"):
        service.answer(_STUDENT, item_ref=ref)


def test_placement_offers_every_playable_kind(wiring: runner.SliceWiring) -> None:
    from taleem_core.contexts.learning.application.placement_service import _diagnostic_items

    lesson = wiring.read_model.lesson_for(OBJECTIVE_CODE)
    assert lesson is not None
    kinds = {i.kind for i in _diagnostic_items(lesson)}
    assert kinds == {"choose", "fill", "order", "match", "sort"}


# ---------------------------------------------------------------------------------- sync


@pytest.fixture
def consumer(wiring: runner.SliceWiring) -> Iterator[SyncEvidenceConsumer]:
    engine = create_learning_engine("sqlite://")
    LearningBase.metadata.create_all(engine)
    sf = create_learning_session_factory(engine)
    yield SyncEvidenceConsumer(
        lambda: LearningUnitOfWork(sf),
        wiring.read_model,
        BKTEstimator(),
        HalfLifeForgettingModel(),
        time.time,
    )
    engine.dispose()


def _delta(n: int, item_ref: str, answer: dict[str, object]) -> SyncDelta:
    payload: dict[str, object] = {
        "student_ref": _STUDENT,
        "objective_code": OBJECTIVE_CODE,
        "item_ref": item_ref,
        "evidence_id": f"ev-{n}-{item_ref}",
        **answer,
    }
    return SyncDelta(
        client_event_id=f"ce-{n}",
        type=DeltaType.ATTEMPT_SUBMITTED,
        entity_key=f"attempt:{item_ref}",
        payload=payload,
    )


def test_sync_applies_every_kind(consumer: SyncEvidenceConsumer) -> None:
    apply: Callable[[SyncDelta], Status] = consumer.apply_attempt
    for n, (ref, body) in enumerate(_RIGHT.items()):
        assert apply(_delta(n, ref, body)) is Status.APPLIED, ref
    assert apply(_delta(1, "a-fill", _RIGHT["a-fill"])) is Status.DUPLICATE
    assert apply(_delta(9, "p1-one-of-four", {"option": "0"})) is Status.APPLIED  # legacy string


@pytest.mark.parametrize(
    ("ref", "body"),
    [
        ("p1-one-of-four", {"text": "1/4"}),
        ("a-fill", {"option": 0}),
        ("a-order", {"pairs": [[0, 1]]}),
        ("a-match", {"order": [0, 1]}),
        ("a-sort", {"text": "x"}),
        ("a-fill", {}),
        ("a-fill", {"text": "1", "order": [0]}),
        ("a-fill", {"text": "x" * 201}),
        ("a-order", {"order": [0, "1"]}),
        ("p1-one-of-four", {"option": "zero"}),
    ],
)
def test_sync_conflicts_on_bad_or_mismatched_answers(
    consumer: SyncEvidenceConsumer, ref: str, body: dict[str, object]
) -> None:
    assert consumer.apply_attempt(_delta(1, ref, body)) is Status.CONFLICT
