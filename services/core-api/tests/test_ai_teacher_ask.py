"""Ask the teacher: a learner's question answered from the published lesson only.

Unit tests cover the pure retrieval (``domain/lesson_qa.py``): answers are verbatim authored text,
the lesson's own locale is used, answer keys and item text are never quoted, and an off-topic
question is answered honestly ("not in this lesson"). Service tests cover the gates in front of a
typed question (flag, disclosure screen, live consent, each failing closed) and the holding
response on a disclosure. Integration tests drive the real app over SQLite.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import unit_of_work as cs_uow
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction
from taleem_core.contexts.learning.application.ai_teacher_service import (
    ASK_FREE_TEXT_FLAG,
    ASK_HOLDING_KEY,
    AITeacherService,
    AskRefusedError,
)
from taleem_core.contexts.learning.domain import lesson_qa as qa
from taleem_core.contexts.learning.domain.curriculum_view import ItemView, LessonView
from taleem_core.contexts.learning.domain.decision import CurriculumGraph, DecisionConfig
from taleem_core.contexts.learning.domain.runtime import TemplatedTeachingRuntime
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.feature_flags import StaticFlagProvider
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    OBJECTIVE_CODE,
    build_fractions_lesson,
)

_OBJ = "MATH-G4-FR-01"


def _lesson() -> LessonView:
    return LessonView(
        lesson_id="L1",
        objective_code=_OBJ,
        title={"ur": "کسر", "en": "Fractions"},
        explanation={
            "ur": "ایک مکمل چیز کو برابر حصوں میں بانٹتے ہیں۔ اوپر کا نمبر حصے گنتا ہے۔",
            "en": "We split a whole into equal parts. The top number counts the parts. "
            "The bottom number shows the total.",
        },
        worked_example_steps=("You eat one part.", "We write it as 1/4."),
        worked_example_steps_localized=(
            {"ur": "ایک حصہ کھایا۔", "en": "You eat one part."},
            {"ur": "اسے 1/4 لکھتے ہیں۔", "en": "We write it as 1/4."},
        ),
        misconception_corrections={
            "bigger-denominator": (
                "A bigger bottom number means smaller parts, not a bigger fraction."
            )
        },
        practice_items=(
            ItemView(
                item_ref="p1",
                objective_code=_OBJ,
                prompt={"en": "Which is bigger, 1/2 or 1/4?"},
                options=("1/2", "1/4"),
                correct_option=0,
                hints=("Think about the size of each part.",),
            ),
        ),
    )


# ---------------------------------------------------------------- unit: retrieval


def test_typed_question_quotes_the_matching_authored_sentence() -> None:
    lesson = _lesson()
    ans = qa.answer_question(lesson, "What does the bottom number show?", "en")
    assert ans.outcome is qa.AskOutcome.ANSWERED
    assert ans.passages[0].text == "The bottom number shows the total."
    assert "bottom" in ans.matched_terms
    assert qa.is_grounded_excerpt(lesson, ans)


def test_plural_and_case_fold_still_match() -> None:
    ans = qa.answer_question(_lesson(), "PARTS??", "en")
    assert ans.outcome is qa.AskOutcome.ANSWERED
    assert all("part" in p.text.lower() for p in ans.passages)


def test_urdu_question_answers_in_urdu() -> None:
    ans = qa.answer_question(_lesson(), "اوپر کا نمبر کیا کرتا ہے؟", "ur")
    assert ans.outcome is qa.AskOutcome.ANSWERED
    assert ans.passages[0].text == "اوپر کا نمبر حصے گنتا ہے۔"
    assert ans.passages[0].locale == "ur"


def test_off_topic_question_is_not_answered() -> None:
    for question in ("Who won the cricket match?", "what is it?", "", "   ?? "):
        ans = qa.answer_question(_lesson(), question, "en")
        assert ans.outcome is qa.AskOutcome.NOT_IN_LESSON
        assert ans.passages == ()


def test_answers_never_quote_item_prompts_hints_or_keys() -> None:
    lesson = _lesson()
    # These words appear only in the practice item's prompt, hint and options.
    ans = qa.answer_question(lesson, "Which is bigger, 1/2 or 1/4? size of each part", "en")
    for p in ans.passages:
        assert p.text not in ("Which is bigger, 1/2 or 1/4?", "Think about the size of each part.")
        assert p.text not in ("1/2", "1/4")
    sources = {p.source.split("#")[0].split(":")[0] for p in qa.corpus(lesson, "en")}
    assert sources == {"explanation", "worked_example", "correction"}


def test_at_most_two_passages_in_lesson_order() -> None:
    ans = qa.answer_question(_lesson(), "top bottom number parts total", "en")
    assert 1 <= len(ans.passages) <= qa.MAX_ANSWER_PASSAGES
    idx = [int(p.source.split("#")[1]) for p in ans.passages]
    assert idx == sorted(idx)


def test_tap_intents() -> None:
    lesson = _lesson()
    ex = qa.answer_intent(lesson, qa.AskIntent.EXAMPLE, "ur")
    assert [p.text for p in ex.passages] == ["ایک حصہ کھایا۔", "اسے 1/4 لکھتے ہیں۔"]
    mistake = qa.answer_intent(lesson, qa.AskIntent.COMMON_MISTAKE, "en")
    assert mistake.passages[0].source == "correction:bigger-denominator"
    recap = qa.answer_intent(lesson, qa.AskIntent.RECAP, "en")
    assert len(recap.passages) == 2 and recap.passages[0].source == "explanation#0"
    for a in (ex, mistake, recap):
        assert qa.is_grounded_excerpt(lesson, a)
    bare = LessonView(lesson_id="L2", objective_code="X", title={"en": "t"}, explanation={})
    assert qa.answer_intent(bare, qa.AskIntent.EXAMPLE, "en").outcome is (
        qa.AskOutcome.NOT_IN_LESSON
    )
    with pytest.raises(ValueError):
        qa.answer_intent(lesson, qa.AskIntent.QUESTION, "en")


def test_falls_back_to_english_when_locale_not_authored() -> None:
    ans = qa.answer_intent(_lesson(), qa.AskIntent.RECAP, "sd")
    assert ans.passages[0].locale == "en"


def test_grounding_guard_rejects_invented_text() -> None:
    fake = qa.AskAnswer(
        qa.AskIntent.QUESTION,
        qa.AskOutcome.ANSWERED,
        (qa.Passage("Fractions are always less than one.", "explanation#0", "en"),),
    )
    assert not qa.is_grounded_excerpt(_lesson(), fake)
    key = qa.AskAnswer(
        qa.AskIntent.QUESTION, qa.AskOutcome.ANSWERED, (qa.Passage("1/2", "x#0", "en"),)
    )
    assert qa.reveals_answer_key(_lesson(), key)


# ---------------------------------------------------------------- service: gates


class _Curriculum:
    def __init__(self, lesson: LessonView | None) -> None:
        self._lesson = lesson

    def lesson_for(self, code: str) -> LessonView | None:
        return self._lesson if self._lesson and code == self._lesson.objective_code else None


class _Screen:
    def __init__(self, match: bool = False, raises: bool = False) -> None:
        self.match, self.raises, self.calls = match, raises, []  # type: ignore[var-annotated]

    def __call__(self, student_ref: str, ask_id: str, text: str, objective_code: str) -> bool:
        self.calls.append((student_ref, ask_id, text, objective_code))
        if self.raises:
            raise RuntimeError("screen down")
        return self.match


def _service(
    *,
    flag: bool = True,
    screen: _Screen | None = None,
    consent: Any = True,
) -> AITeacherService:
    def consent_fn(ref: str) -> bool:
        if consent == "raise":
            raise RuntimeError("identity down")
        return bool(consent)

    return AITeacherService(
        None,  # type: ignore[arg-type]  (ask never touches sessions)
        None,  # type: ignore[arg-type]  (nor the knowledge service)
        _Curriculum(_lesson()),  # type: ignore[arg-type]
        TemplatedTeachingRuntime(),
        CurriculumGraph(objectives=()),
        DecisionConfig(),
        time.time,
        flags=StaticFlagProvider(frozenset({ASK_FREE_TEXT_FLAG} if flag else ())),
        disclosure_screen=screen,
        ai_teaching_consent=consent_fn,
    )


def _ask(svc: AITeacherService, **kw: Any) -> dict[str, Any] | None:
    args: dict[str, Any] = {"intent": "question", "ask_id": "ask_1", "locale": "en"}
    args.update(kw)
    return svc.ask("stu-1", _OBJ, **args)


def test_typed_question_answered_when_every_gate_open() -> None:
    screen = _Screen()
    out = _ask(_service(screen=screen), question="What does the bottom number show?")
    assert out is not None
    assert out["outcome"] == "answered"
    assert out["answer"][0]["text"] == "The bottom number shows the total."
    assert out["generative"] is False and out["grounded"] is True
    assert out["free_text_enabled"] is True
    assert screen.calls == [("stu-1", "ask_1", "What does the bottom number show?", _OBJ)]


@pytest.mark.parametrize(
    "kw",
    [
        {"flag": False, "screen": _Screen()},
        {"flag": True, "screen": None},
        {"flag": True, "screen": _Screen(), "consent": False},
        {"flag": True, "screen": _Screen(), "consent": "raise"},  # fails closed
    ],
)
def test_typed_question_refused_unless_every_gate_open(kw: dict[str, Any]) -> None:
    svc = _service(**kw)
    with pytest.raises(AskRefusedError) as err:
        _ask(svc, question="What does the bottom number show?")
    assert err.value.code == "FREE_TEXT_DISABLED"
    screen = kw.get("screen")
    assert screen is None or screen.calls == []  # refused before the text is read


def test_disclosure_returns_holding_response_and_no_lesson_text() -> None:
    out = _ask(_service(screen=_Screen(match=True)), question="the bottom number hurts me")
    assert out is not None
    assert out["outcome"] == "holding"
    assert out["message_key"] == ASK_HOLDING_KEY
    assert out["answer"] == [] and out["follow_up"] == []


def test_screen_failure_never_answers() -> None:
    with pytest.raises(RuntimeError):
        _ask(_service(screen=_Screen(raises=True)), question="bottom number")


def test_tap_intent_needs_no_free_text_gates() -> None:
    svc = _service(flag=False, screen=None, consent=False)
    out = _ask(svc, intent="example")
    assert out is not None and out["outcome"] == "answered"
    assert out["follow_up"] == ["common_mistake", "recap"]
    assert out["free_text_enabled"] is False


def test_input_validation() -> None:
    svc = _service(screen=_Screen())
    for kw, code in (
        ({"intent": "chat"}, "UNKNOWN_INTENT"),
        ({"question": "   "}, "QUESTION_REQUIRED"),
        ({"question": "x" * (qa.QUESTION_MAX_CHARS + 1)}, "QUESTION_TOO_LONG"),
    ):
        with pytest.raises(AskRefusedError) as err:
            _ask(svc, **kw)
        assert err.value.code == code
    assert svc.ask("stu-1", "NO-SUCH", intent="recap", ask_id="a") is None


# ---------------------------------------------------------------- integration (SQLite)

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)


def _auth(sub: str) -> dict[str, str]:
    exp = int(time.time()) + 3600
    token = sign_hs256({"sub": sub, "role": "student", "exp": exp}, _SECRET)
    return {"Authorization": f"Bearer {token}"}


_REVIEW_ROLES = (
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
)


def _publish_fractions(app: Any) -> None:
    sf = app.state.studio_session_factory

    def op(fn: Any) -> None:
        with cs_uow(sf) as uow:
            fn(CurriculumStudioService(uow.lessons, uow.publish, clock=lambda: 1000.0))
            uow.commit()

    op(lambda s: s.create(build_fractions_lesson()))
    op(lambda s: s.submit(LESSON_KEY, "subject_author"))
    for role in _REVIEW_ROLES:
        op(lambda s, role=role: s.review(LESSON_KEY, ReviewAction.APPROVE, role))
    op(lambda s: s.publish(LESSON_KEY, "curriculum_architect", "v1"))


def test_ask_endpoint_over_sqlite() -> None:
    app = create_app(Settings(database_url="", enabled_flags_csv=ASK_FREE_TEXT_FLAG))
    client = TestClient(app)
    _publish_fractions(app)
    h = _auth("ask-stu")
    sid = client.post("/v1/learning/sessions", json={"student_ref": "ask-stu"}, headers=h).json()[
        "session_id"
    ]
    url = f"/v1/learning/sessions/{sid}:ask"

    ex = client.post(url, json={"objective_code": OBJECTIVE_CODE, "intent": "example"}, headers=h)
    assert ex.status_code == 200, ex.text
    body = ex.json()
    assert body["outcome"] == "answered"
    assert [a["text"] for a in body["answer"]][:2] == [
        "ایک کیک کو چار برابر حصوں میں کاٹیں۔",
        "ایک حصہ کھایا۔",
    ]
    assert body["ask_id"].startswith("ask_")

    # A learner with no ai_teaching consent cannot type a question even with the flag on.
    typed = client.post(
        url,
        json={"objective_code": OBJECTIVE_CODE, "intent": "question", "question": "top number"},
        headers=h,
    )
    assert typed.status_code == 403
    assert typed.json()["code"] == "FREE_TEXT_DISABLED"

    assert (
        client.post(url, json={"objective_code": "NOPE", "intent": "recap"}, headers=h).status_code
        == 404
    )
    assert (
        client.post(
            url, json={"objective_code": OBJECTIVE_CODE, "intent": "x" * 40}, headers=h
        ).status_code
        == 422
    )
    # Auth + ownership.
    assert (
        client.post(url, json={"objective_code": OBJECTIVE_CODE, "intent": "recap"}).status_code
        == 401
    )
    other = client.post(
        url, json={"objective_code": OBJECTIVE_CODE, "intent": "recap"}, headers=_auth("someone")
    )
    assert other.status_code in (403, 404)


# ---------------------------------------------------------------- vocabulary


def _with_vocab() -> LessonView:
    from dataclasses import replace

    return replace(
        _lesson(),
        vocabulary=(
            (
                {"en": "denominator", "ur": "نسب نما"},
                {"en": "The bottom number of a fraction.", "ur": "کسر کا نیچے والا نمبر۔"},
            ),
            ({"en": "  "}, {"en": "ignored: no term"}),
        ),
    )


def test_what_does_a_word_mean_is_answered_from_the_vocabulary() -> None:
    lesson = _with_vocab()
    ans = qa.answer_question(lesson, "What does denominator mean?", "en")
    assert ans.outcome is qa.AskOutcome.ANSWERED
    assert ans.passages[0].text == "denominator: The bottom number of a fraction."
    assert ans.passages[0].source == "vocabulary#0"
    assert qa.is_grounded_excerpt(lesson, ans)
    ur = qa.answer_question(lesson, "نسب نما کیا ہے؟", "ur")
    assert ur.passages[0].text == "نسب نما: کسر کا نیچے والا نمبر۔"
    # A spliced term/definition pair that was never authored together is not grounded.
    spliced = qa.AskAnswer(
        qa.AskIntent.QUESTION,
        qa.AskOutcome.ANSWERED,
        (qa.Passage("denominator: The top number counts the parts.", "vocabulary#0", "en"),),
    )
    assert not qa.is_grounded_excerpt(lesson, spliced)


def test_vocabulary_reaches_the_lesson_view() -> None:
    from taleem_core.contexts.curriculum_studio.domain.content import VocabularyTerm
    from taleem_core.contexts.learning.adapters.curriculum_read_model import (
        CurriculumStudioReadModel,
    )
    from taleem_core.vertical_slice.fractions_lesson import _loc

    lesson = build_fractions_lesson()
    lesson.vocabulary = [
        VocabularyTerm(
            term=_loc("نسب نما", "denominator"),
            definition=_loc("نیچے کا نمبر۔", "The bottom number."),
        ),
        VocabularyTerm(term=_loc("", ""), definition=_loc("x", "x")),  # no term: dropped
    ]
    view = CurriculumStudioReadModel(None)._project(lesson, OBJECTIVE_CODE)  # type: ignore[arg-type]
    assert view.vocabulary == (
        (
            {"ur": "نسب نما", "en": "denominator"},
            {"ur": "نیچے کا نمبر۔", "en": "The bottom number."},
        ),
    )
