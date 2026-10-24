"""Homework + marking — domain rules and ports, no HTTP (HOMEWORK_AND_MARKING_CONTRACT.md).

Submission state machine (resubmit while submitted/returned, marked is final, max_chars, score
bounds with and without a rubric), the written-item projection and its secrecy, idempotent
human-graded evidence, the in-memory repository, the school ports, and the teacher concern rule.
"""

from __future__ import annotations

import dataclasses

import pytest

from taleem_core.contexts.learning.adapters.persistence.base import (
    LearningBase,
    create_learning_engine,
    create_learning_session_factory,
)
from taleem_core.contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from taleem_core.contexts.learning.application.knowledge_service import KnowledgeService
from taleem_core.contexts.learning.application.sync_consumer import _gradable_item
from taleem_core.contexts.learning.application.written_work import (
    WrittenWorkService,
    written_item_dict,
)
from taleem_core.contexts.learning.domain.curriculum_view import (
    SECRET_ITEM_FIELDS,
    WRITTEN,
    ItemView,
    LessonView,
    RubricLevelView,
    RubricView,
)
from taleem_core.contexts.learning.domain.decision import CurriculumGraph
from taleem_core.contexts.learning.domain.estimator import BKTEstimator
from taleem_core.contexts.learning.domain.forgetting import HalfLifeForgettingModel
from taleem_core.contexts.learning.domain.offline_package import lesson_offline_content
from taleem_core.contexts.learning.domain.scorer import (
    Answer,
    AnswerKindMismatchError,
    evaluate,
)
from taleem_core.contexts.safeguarding.domain.model import (
    Concern,
    InvalidConcernError,
    RaisedBy,
)
from taleem_core.contexts.school.adapters.context_ports import CallableWrittenWork
from taleem_core.contexts.school.adapters.memory import InMemorySubmissionRepository
from taleem_core.contexts.school.application.ports import WrittenItem
from taleem_core.contexts.school.domain.model import (
    MAX_FEEDBACK,
    Assignment,
    Classroom,
    InvalidSchoolDataError,
    MarkOutcome,
    Submission,
    SubmissionConflictError,
    SubmissionStatus,
    clean_answer_text,
    clean_feedback,
)
from taleem_core.platform.concurrency import ConcurrencyConflictError

OBJ = "MATH-G4-FR-01"


def _assignment() -> Assignment:
    classroom = Classroom.create(
        organization_id="org_1", teacher_ref="tch_1", name="Blue", join_code="ABCD-EFGH", now=1.0
    )
    return Assignment.create(
        classroom=classroom, objective_code=OBJ, due_at=100.0, assigned_by="tch_1", now=2.0
    )


def _sub(*, max_chars: int = 200, max_score: int | None = None, text: str = "half") -> Submission:
    return Submission.start(
        assignment=_assignment(),
        item_ref="hw-1",
        student_ref="stu_1",
        text=text,
        max_chars=max_chars,
        max_score=max_score,
        now=10.0,
    )


# ----------------------------------------------------------------------- submission rules


def test_text_is_cleaned_and_bounded() -> None:
    assert clean_answer_text("  a\x00b\n c \t", max_chars=10) == "ab\n c"
    with pytest.raises(InvalidSchoolDataError):
        clean_answer_text(" \n ", max_chars=10)
    with pytest.raises(InvalidSchoolDataError):
        clean_answer_text("x" * 11, max_chars=10)
    with pytest.raises(InvalidSchoolDataError):
        clean_answer_text("x", max_chars=0)
    assert clean_answer_text("x" * 10, max_chars=10) == "x" * 10
    assert clean_feedback(None, required=False) == ""
    with pytest.raises(InvalidSchoolDataError):
        clean_feedback("  ", required=True)
    with pytest.raises(InvalidSchoolDataError):
        clean_feedback("x" * (MAX_FEEDBACK + 1), required=False)


def test_start_and_resubmit_while_submitted_or_returned() -> None:
    sub = _sub(max_score=0)
    assert sub.submission_id.startswith("sub_") and sub.status is SubmissionStatus.SUBMITTED
    assert sub.max_score is None  # a 0 scale is no scale
    sub.resubmit(text="one half", max_chars=200, max_score=None, now=11.0)
    assert (sub.attempt, sub.text, sub.submitted_at) == (2, "one half", 11.0)
    sub.return_for_rework(feedback="why?", teacher_ref="tch_1", now=12.0)
    assert sub.status is SubmissionStatus.RETURNED and sub.feedback == "why?"
    with pytest.raises(SubmissionConflictError) as returned:
        sub.return_for_rework(feedback="again", teacher_ref="tch_1", now=12.5)
    assert returned.value.code == "SUBMISSION_RETURNED"
    sub.resubmit(text="1/2", max_chars=200, max_score=3, now=13.0)
    assert sub.status is SubmissionStatus.SUBMITTED and sub.attempt == 3 and sub.max_score == 3


def test_marked_is_final() -> None:
    sub = _sub()
    sub.mark(outcome="met", score=None, feedback=" good ", teacher_ref="tch_1", now=20.0)
    assert sub.status is SubmissionStatus.MARKED and sub.outcome is MarkOutcome.MET
    assert sub.feedback == "good" and sub.reviewed_by == "tch_1" and sub.marked_at == 20.0
    for change in (
        lambda: sub.resubmit(text="x", max_chars=200, max_score=None, now=21.0),
        lambda: sub.mark(outcome="met", score=None, feedback="", teacher_ref="t", now=21.0),
        lambda: sub.return_for_rework(feedback="x", teacher_ref="t", now=21.0),
    ):
        with pytest.raises(SubmissionConflictError) as exc:
            change()
        assert exc.value.code == "SUBMISSION_MARKED"


def test_a_returned_answer_can_still_be_marked() -> None:
    sub = _sub()
    sub.return_for_rework(feedback="try", teacher_ref="tch_1", now=11.0)
    sub.mark(outcome="not_yet", score=None, feedback=None, teacher_ref="tch_1", now=12.0)
    assert sub.outcome is MarkOutcome.NOT_YET


def test_score_bounds_with_and_without_a_rubric() -> None:
    plain = _sub()
    with pytest.raises(InvalidSchoolDataError):
        plain.mark(outcome="met", score=0, feedback="", teacher_ref="t", now=1.0)
    with pytest.raises(InvalidSchoolDataError):
        plain.mark(outcome="maybe", score=None, feedback="", teacher_ref="t", now=1.0)
    rubric = _sub(max_score=3)
    for bad in (None, -1, 4, True):
        with pytest.raises(InvalidSchoolDataError):
            rubric.mark(outcome="met", score=bad, feedback="", teacher_ref="t", now=1.0)
    assert rubric.status is SubmissionStatus.SUBMITTED  # nothing changed on a refusal
    rubric.mark(outcome="met", score=0, feedback="", teacher_ref="t", now=1.0)
    assert rubric.score == 0
    edge = _sub(max_score=3)
    edge.mark(outcome="met", score=3, feedback="", teacher_ref="t", now=1.0)
    assert edge.score == 3


def test_max_chars_is_the_items_cap() -> None:
    with pytest.raises(InvalidSchoolDataError):
        _sub(max_chars=200, text="x" * 201)
    assert len(_sub(max_chars=2000, text="x" * 2000).text) == 2000


# --------------------------------------------------------------------- in-memory repository


def test_in_memory_repository_behaves_like_sql() -> None:
    repo = InMemorySubmissionRepository()
    a = _sub()
    b = dataclasses.replace(a, submission_id="sub_b", item_ref="hw-2", submitted_at=5.0)
    repo.add(a)
    repo.add(b)
    with pytest.raises(ConcurrencyConflictError):
        repo.add(dataclasses.replace(a, submission_id="sub_dup"))  # one per (asg, item, learner)
    assert repo.get("org_other", a.submission_id) is None
    loaded = repo.get("org_1", a.submission_id)
    assert loaded is not None and loaded is not a
    assert repo.by_id(b.submission_id) is not None and repo.by_id("nope") is None
    assert repo.find(a.assignment_id, "hw-1", "stu_1") is not None
    assert repo.find(a.assignment_id, "hw-9", "stu_1") is None
    assert [s.item_ref for s in repo.for_student("stu_1")] == ["hw-2", "hw-1"]  # oldest first
    assert len(repo.for_class("org_1", a.class_id, SubmissionStatus.SUBMITTED)) == 2
    assert repo.for_class("org_1", a.class_id, SubmissionStatus.MARKED) == []
    stale = repo.get("org_1", a.submission_id)
    assert loaded is not None and stale is not None
    loaded.mark(outcome="met", score=None, feedback="", teacher_ref="t", now=30.0)
    repo.save(loaded)
    stale.return_for_rework(feedback="x", teacher_ref="t", now=31.0)
    with pytest.raises(ConcurrencyConflictError):
        repo.save(stale)  # the other teacher's change won
    fresh = dataclasses.replace(a, submission_id="sub_new", item_ref="hw-3")
    repo.save(fresh)  # save of an unknown row adds it
    assert repo.by_id(fresh.submission_id) is not None


# ---------------------------------------------------------------------- learning projection


def _rubric() -> RubricView:
    return RubricView(
        criteria="explains",
        max_score=2,
        levels=(RubricLevelView(level=1, descriptor={"en": "some"}),),
    )


def _written(ref: str = "hw-1", **kw: object) -> ItemView:
    defaults: dict[str, object] = {
        "kind": WRITTEN,
        "max_chars": 200,
        "hints": ("think",),
        "rubric": _rubric(),
        "sample_answer": "SAMPLE",
        "guidance": "GUIDE",
    }
    defaults.update(kw)
    return ItemView(item_ref=ref, objective_code=OBJ, prompt={"en": "why?"}, **defaults)  # type: ignore[arg-type]


def test_written_item_view_fields() -> None:
    item = _written()
    assert item.written and not item.playable
    assert item.learner_fields() == {"kind": "written", "left_count": 0, "max_chars": 200}
    assert item.teacher_fields() == {
        "rubric": {
            "criteria": "explains",
            "max_score": 2,
            "levels": [{"score": 1, "label": "1", "descriptor": {"en": "some"}}],
        },
        "sample_answer": "SAMPLE",
        "guidance": "GUIDE",
    }
    bare = _written(rubric=None, sample_answer="", guidance="")
    assert bare.teacher_fields() == {"rubric": None, "sample_answer": None, "guidance": None}
    assert _rubric().scored and not RubricView(criteria="", max_score=0).scored
    choose = ItemView(item_ref="c", objective_code=OBJ, prompt={}, options=("a", "b"))
    assert "max_chars" not in choose.learner_fields() and not choose.written
    assert {"rubric", "sample_answer", "guidance"} <= set(SECRET_ITEM_FIELDS)


def test_written_items_are_never_auto_scored() -> None:
    with pytest.raises(AnswerKindMismatchError):
        evaluate(_written(), Answer(text="half"))
    with pytest.raises(AnswerKindMismatchError):
        evaluate(_written(), 0)
    lesson = LessonView(
        lesson_id="L",
        objective_code=OBJ,
        title={},
        explanation={},
        homework_items=(_written(),),
        written_items=(_written(),),
    )
    assert _gradable_item(lesson, "hw-1") is None  # sync ignores a written item
    assert lesson.written_item("hw-1") is not None and lesson.written_item("x") is None


def test_offline_content_has_no_marking_aid() -> None:
    lesson = LessonView(
        lesson_id="L", objective_code=OBJ, title={}, explanation={}, homework_items=(_written(),)
    )
    content = lesson_offline_content(lesson)
    text = repr(content)
    for secret in ("SAMPLE", "GUIDE", "explains", "rubric", "sample_answer", "guidance"):
        assert secret not in text
    assert content["homework_items"][0]["max_chars"] == 200  # type: ignore[index]


# --------------------------------------------------------------- idempotent human evidence


class _ReadModel:
    def __init__(self, lesson: LessonView | None) -> None:
        self._lesson = lesson

    def lesson_for(self, objective_code: str) -> LessonView | None:
        return self._lesson

    def published_lessons(self) -> list[LessonView]:
        return [self._lesson] if self._lesson else []

    def published_graph(self) -> CurriculumGraph:
        return CurriculumGraph(objectives=())


def _knowledge() -> tuple[KnowledgeService, LearningUnitOfWork]:
    engine = create_learning_engine("sqlite://")
    LearningBase.metadata.create_all(engine)
    sf = create_learning_session_factory(engine)
    service = KnowledgeService(
        lambda: LearningUnitOfWork(sf), BKTEstimator(), HalfLifeForgettingModel(), lambda: 50.0
    )
    return service, LearningUnitOfWork(sf)


def test_record_marked_is_idempotent_by_submission_id() -> None:
    knowledge, _ = _knowledge()
    lesson = LessonView(
        lesson_id="L",
        objective_code=OBJ,
        title={"en": "Fractions"},
        explanation={},
        written_items=(_written(),),
    )
    work = WrittenWorkService(_ReadModel(lesson), knowledge)
    args = {"submission_id": "sub_1", "student_ref": "stu_1", "objective_code": OBJ}
    assert work.record_marked(**args, item_ref="hw-1", met=True) is True
    assert work.record_marked(**args, item_ref="hw-1", met=True) is False  # a retry
    assert work.record_marked(**args, item_ref="hw-1", met=False) is False
    snap = knowledge.snapshot("stu_1")
    assert snap is not None
    assert [e.evidence_id for e in snap.evidence] == ["sub_1"]
    assert snap.objectives[OBJ].attempts == 1  # mastery updated once
    assert work.record_marked(
        submission_id="sub_2", student_ref="stu_1", objective_code=OBJ, item_ref="hw-1", met=False
    )
    snap = knowledge.snapshot("stu_1")
    assert snap is not None and snap.objectives[OBJ].attempts == 2

    view = work.written_lesson(OBJ)
    assert view is not None and view["title"] == {"en": "Fractions"}
    assert view["items"] == [written_item_dict(_written())]
    assert WrittenWorkService(_ReadModel(None), knowledge).written_lesson(OBJ) is None


def test_callable_written_work_port() -> None:
    calls: list[dict[str, object]] = []

    def record(**kw: object) -> bool:
        calls.append(kw)
        return True

    view = {
        "objective_code": OBJ,
        "title": {"en": "T", "ur": ""},
        "items": [
            written_item_dict(_written()),
            written_item_dict(_written("hw-2", rubric=None, sample_answer=" ", guidance="")),
        ],
    }
    port = CallableWrittenWork(lambda code: view if code == OBJ else None, record)
    lesson = port.lesson(OBJ)
    assert lesson is not None and port.lesson("other") is None
    assert lesson.title == {"en": "T"}
    first, second = lesson.items
    assert first.max_score == 2 and first.sample_answer == "SAMPLE"
    assert second.max_score is None and second.sample_answer is None and second.guidance is None
    assert lesson.item("hw-2") is second and lesson.item("x") is None
    assert port.record_marked(
        submission_id="sub_1", student_ref="s", objective_code=OBJ, item_ref="hw-1", met=True
    )
    assert calls[0]["met"] is True
    zero = WrittenItem(item_ref="z", prompt={}, hints=(), max_chars=200, rubric={"max_score": 0})
    assert zero.max_score is None


# ---------------------------------------------------------------------- safeguarding domain


def test_teacher_concern_carries_the_submission_ref() -> None:
    concern = Concern.raise_new(
        subject_ref="stu_1",
        raised_by_ref="tch_1",
        raised_by_role=RaisedBy.TEACHER,
        category="felt_unsafe",
        free_text=None,
        screen="teacher/marking",
        lesson_id=None,
        now=1.0,
        submission_id="sub_1",
    )
    assert concern.context_submission_id == "sub_1"
    with pytest.raises(InvalidConcernError):
        Concern.raise_new(
            subject_ref="stu_1",
            raised_by_ref="gdn_1",
            raised_by_role=RaisedBy.GUARDIAN,
            category="other",
            free_text=None,
            screen=None,
            lesson_id=None,
            now=1.0,
            submission_id="sub_1",
        )
    with pytest.raises(InvalidConcernError):
        Concern.raise_new(
            subject_ref="stu_1",
            raised_by_ref="tch_1",
            raised_by_role=RaisedBy.TEACHER,
            category="other",
            free_text=None,
            screen=None,
            lesson_id=None,
            now=1.0,
            submission_id="bad ref!",
        )
