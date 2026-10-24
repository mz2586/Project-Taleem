"""Units of the AI-led homework path (HOMEWORK_AND_MARKING_CONTRACT §6): the submission rules
(self-paced, auto-mark, retry, evidence ids), the disclosure screen (data, normalisation,
matching) and the AI rubric marker (inert unless every gate holds)."""

from __future__ import annotations

import json

import pytest

from taleem_core.contexts.learning.application.written_marker import (
    AI_RUBRIC_MARKING_FLAG,
    FD03_APPROVED,
    LLMWrittenWorkMarker,
    MarkProposal,
    RubricForMarking,
    StubWrittenWorkMarker,
)
from taleem_core.contexts.safeguarding.domain.disclosure import (
    PHRASES_PATH,
    STARTER_HEADER,
    default_phrase_list,
    normalise,
    parse_phrase_list,
    strongest_category,
)
from taleem_core.contexts.safeguarding.domain.model import (
    Category,
    Concern,
    InvalidConcernError,
    RaisedBy,
)
from taleem_core.contexts.school.domain.model import (
    InvalidSchoolDataError,
    MarkOutcome,
    Submission,
    SubmissionConflictError,
    SubmissionSource,
    SubmissionStatus,
)
from taleem_core.platform.feature_flags import StaticFlagProvider
from taleem_core.ports.llm import StubLLMGateway
from taleem_core.ports.llm_inert import InertProviderGateway

# ------------------------------------------------------------------------ submission rules


def _self_paced(text: str = "an answer") -> Submission:
    return Submission.start_self_paced(
        objective_code="MATH-G4-FR-01",
        item_ref="hw-exact",
        student_ref="stu_1",
        text=text,
        max_chars=200,
        max_score=None,
        now=10.0,
    )


def test_a_self_paced_submission_has_no_class_assignment_or_organization() -> None:
    sub = _self_paced("  hi  ")
    assert sub.source is SubmissionSource.SELF_PACED and sub.self_paced
    assert (sub.assignment_id, sub.class_id, sub.organization_id) == (None, None, "")
    assert sub.text == "hi" and sub.status is SubmissionStatus.SUBMITTED
    with pytest.raises(InvalidSchoolDataError):
        Submission.start_self_paced(
            objective_code="bad code!",
            item_ref="x",
            student_ref="s",
            text="t",
            max_chars=200,
            max_score=None,
            now=1.0,
        )


def test_auto_not_yet_is_retryable_and_auto_met_is_final() -> None:
    sub = _self_paced()
    sub.auto_mark(met=False, now=11.0)
    assert sub.auto_marked and sub.can_retry and sub.outcome is MarkOutcome.NOT_YET
    assert sub.reviewed_by == "auto" and sub.evidence_id == sub.submission_id
    sub.resubmit(text="again", max_chars=200, max_score=None, now=12.0)
    assert sub.status is SubmissionStatus.SUBMITTED and sub.attempt == 2
    assert sub.outcome is None and sub.reviewed_by is None and sub.marked_at is None
    sub.auto_mark(met=True, now=13.0)
    assert not sub.can_retry and sub.evidence_id == f"{sub.submission_id}:2"
    with pytest.raises(SubmissionConflictError):
        sub.resubmit(text="more", max_chars=200, max_score=None, now=14.0)


def test_a_teachers_not_yet_stays_final_and_uses_the_submission_id() -> None:
    sub = _self_paced()
    sub.resubmit(text="second", max_chars=200, max_score=None, now=11.0)
    sub.mark(outcome="not_yet", score=None, feedback="", teacher_ref="tch_1", now=12.0)
    assert not sub.can_retry and sub.evidence_id == sub.submission_id
    with pytest.raises(SubmissionConflictError):
        sub.resubmit(text="third", max_chars=200, max_score=None, now=13.0)


# ------------------------------------------------------------------------ disclosure screen


def test_the_phrase_list_is_data_marked_as_a_starter_pending_m_safe() -> None:
    raw = json.loads(PHRASES_PATH.read_text(encoding="utf-8"))
    assert raw["_header"].startswith(STARTER_HEADER)
    phrases = default_phrase_list()
    assert phrases.header.startswith(STARTER_HEADER)
    langs = {p.lang for p in phrases.phrases}
    assert {"en", "ur"} <= langs
    assert {p.category for p in phrases.phrases} <= set(Category)


def test_normalise_folds_case_punctuation_diacritics_and_letter_variants() -> None:
    assert normalise("  He HITS   me!!! ") == "he hits me"
    assert normalise("Don't tell anyone.") == "dont tell anyone"
    assert normalise("مُجھے مارتا ہے۔") == "مجھے مارتا ہے"
    assert normalise("مرنا چاہتي ہوں") == normalise("مرنا چاہتی ہوں")  # Arabic yeh → Urdu yeh


def test_matching_is_whole_word_and_deterministic() -> None:
    phrases = default_phrase_list()
    assert [p.phrase_id for p in phrases.matches("My brother hits me, please help")] == ["en-01"]
    assert phrases.matches("She whits melons") == ()  # no partial-word match
    assert phrases.matches("Ali hit the ball") == ()
    assert [p.phrase_id for p in phrases.matches("وہ مجھے مارتا ہے")] == ["ur-01"]
    matched = phrases.matches("he bullies me and I want to die")
    assert strongest_category(matched) is Category.VERY_SAD  # T1 beats T2


def test_a_malformed_phrase_list_is_refused() -> None:
    with pytest.raises(ValueError):
        parse_phrase_list({"phrases": []})
    with pytest.raises(ValueError):
        parse_phrase_list({"phrases": [{"id": "a", "category": "other", "phrase": " ! "}]})
    dup = {"id": "a", "category": "other", "phrase": "x"}
    with pytest.raises(ValueError):
        parse_phrase_list({"phrases": [dup, dup]})
    with pytest.raises(InvalidConcernError):
        parse_phrase_list({"phrases": [{"id": "a", "category": "nope", "phrase": "x"}]})


def test_only_a_teacher_or_the_system_names_a_submission_and_the_system_always_does() -> None:
    def raise_as(role: RaisedBy, submission_id: str | None) -> Concern:
        return Concern.raise_new(
            subject_ref="stu_1",
            raised_by_ref="disclosure_screen" if role is RaisedBy.SYSTEM else "gdn_1",
            raised_by_role=role,
            category="very_sad",
            free_text=None,
            screen="learner/homework",
            lesson_id=None,
            now=1.0,
            submission_id=submission_id,
        )

    assert raise_as(RaisedBy.SYSTEM, "sub_1").context_submission_id == "sub_1"
    with pytest.raises(InvalidConcernError):
        raise_as(RaisedBy.SYSTEM, None)
    with pytest.raises(InvalidConcernError):
        raise_as(RaisedBy.GUARDIAN, "sub_1")


# ------------------------------------------------------------------------ AI rubric marker

RUBRIC = RubricForMarking(criteria="explains equal parts", max_score=3, levels=((1, "some"),))


class _Clear:
    def __init__(self, clear: bool = True) -> None:
        self.clear = clear
        self.seen: list[str] = []

    def is_clear(self, text: str) -> bool:
        self.seen.append(text)
        return self.clear


def _reply(_: object) -> str:
    return '{"score": 2, "met": true, "rationale": "fair"}'


def _marker(**kw: object) -> tuple[LLMWrittenWorkMarker, StubLLMGateway]:
    gateway = StubLLMGateway(_reply)
    flags = StaticFlagProvider({AI_RUBRIC_MARKING_FLAG} if kw.pop("flag", True) else set())
    defaults: dict[str, object] = {"distress_classifier": _Clear(), "fd03_approved": True}
    defaults.update(kw)
    return LLMWrittenWorkMarker(gateway=gateway, flags=flags, **defaults), gateway  # type: ignore[arg-type]


def test_fd03_is_not_approved_in_this_build() -> None:
    assert FD03_APPROVED is False


@pytest.mark.parametrize(
    "kw",
    [
        {"flag": False},  # the flag is off by default
        {"fd03_approved": False},  # the default: FD-03 undecided
        {"distress_classifier": None},  # no in-region classifier exists
    ],
)
def test_the_marker_never_calls_a_model_unless_every_gate_holds(kw: dict[str, object]) -> None:
    marker, gateway = _marker(**kw)
    assert marker.propose(prompt="Explain", rubric=RUBRIC, text="my answer") is None
    assert gateway.calls == 0 and not marker.enabled()


def test_default_construction_is_inert() -> None:
    gateway = StubLLMGateway(_reply)
    marker = LLMWrittenWorkMarker(
        gateway=gateway,
        flags=StaticFlagProvider({AI_RUBRIC_MARKING_FLAG}),
        distress_classifier=_Clear(),
    )
    assert marker.propose(prompt="Explain", rubric=RUBRIC, text="x") is None
    assert gateway.calls == 0


def test_distress_adjacent_text_never_reaches_a_model() -> None:
    classifier = _Clear(clear=False)
    marker, gateway = _marker(distress_classifier=classifier)
    assert marker.propose(prompt="Explain", rubric=RUBRIC, text="sad words") is None
    assert classifier.seen == ["sad words"] and gateway.calls == 0


def test_with_every_gate_open_a_stub_gateway_gives_a_bounded_proposal() -> None:
    marker, gateway = _marker()
    proposal = marker.propose(prompt="Explain", rubric=RUBRIC, text="halves are equal")
    assert proposal == MarkProposal(met=True, score=2, rationale="fair")
    assert gateway.calls == 1
    assert marker.propose(prompt="Explain", rubric=None, text="x") is None  # no rubric
    bad = LLMWrittenWorkMarker(
        gateway=StubLLMGateway(lambda _: '{"score": 9, "met": true}'),
        flags=StaticFlagProvider({AI_RUBRIC_MARKING_FLAG}),
        distress_classifier=_Clear(),
        fd03_approved=True,
    )
    assert bad.propose(prompt="Explain", rubric=RUBRIC, text="x") is None  # out of range


def test_the_inert_provider_is_refused_and_the_marker_declines() -> None:
    marker = LLMWrittenWorkMarker(
        gateway=InertProviderGateway("some-provider"),
        flags=StaticFlagProvider({AI_RUBRIC_MARKING_FLAG}),
        distress_classifier=_Clear(),
        fd03_approved=True,
    )
    assert marker.propose(prompt="Explain", rubric=RUBRIC, text="x") is None


def test_the_stub_marker_is_scripted_and_records_calls() -> None:
    stub = StubWrittenWorkMarker(lambda p, r, t: MarkProposal(met=False, score=0, rationale=t))
    assert stub.propose(prompt="P", rubric=RUBRIC, text="T") == MarkProposal(False, 0, "T")
    assert stub.calls == [("P", RUBRIC, "T")]
