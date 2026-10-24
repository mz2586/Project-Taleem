"""Child safety in lesson content: no learner-facing text asks a child for personal details.

Regression for the Grade 4 math homework that asked children to write their house number
(MATH-G4-NB-01) and to order family members' ages (MATH-G4-NB-03). The Studio validator now blocks
any such request, and the whole Grade 4 curriculum (design documents + AI drafts) is scanned.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from taleem_core.contexts.curriculum_studio.domain.assessment import (
    AssessmentItem,
    Competency,
    ItemType,
)
from taleem_core.contexts.curriculum_studio.domain.safety import (
    lesson_personal_detail_requests,
    personal_detail_requests,
)
from taleem_core.contexts.curriculum_studio.domain.validation import validate
from taleem_core.tools import curriculum_ai_drafts as cad
from taleem_core.tools import curriculum_ingest as ci
from tests.studio_helpers import loc, make_valid_lesson

ROOT = Path(__file__).resolve().parents[3]

# The two homework texts removed from GRADE4_MATH_CURRICULUM.md on 2026-10-24.
REMOVED_HOMEWORK = (
    "write three household numbers (page number, house number, a price) in words.",
    "order four family members' ages / four prices.",
)


@pytest.mark.parametrize(
    "text",
    [
        *REMOVED_HOMEWORK,
        "Write your home address.",
        "Ask your mother for her phone number and write it down.",
        "List the ages of your brothers and sisters.",
        "گھر کا نمبر لکھیں۔",
        "اپنا پتا لکھیں۔",
        "خاندان کے چار افراد کی عمریں ترتیب میں لکھیں۔",
        "اپنے ابو کا فون نمبر یاد کر کے لکھیں۔",
    ],
)
def test_requests_for_personal_details_are_detected(text: str) -> None:
    assert personal_detail_requests(text)


@pytest.mark.parametrize(
    "text",
    [
        "Never write your address or phone number in a note.",
        "Do not share your home address with anyone online.",
        "کسی نوٹ میں اپنا پتا یا فون نمبر نہ لکھیں۔",
        "مجھے پتا ہے کہ آج بارش ہوگی۔",  # پتا = "to know"
        "Address the moving = living misconception.",  # address as a verb
        "write three numbers from a book or a price label (a page number, a price, a date).",
        "Draw your home and your family.",
        "order four prices from a shop or a price list, smallest first.",
    ],
)
def test_ordinary_and_protective_text_is_allowed(text: str) -> None:
    assert personal_detail_requests(text) == []


def _true_false(stem: str, correct: int) -> AssessmentItem:
    return AssessmentItem(
        item_id="tf",
        type=ItemType.TRUE_FALSE,
        objective_ref="SLO-1",
        competency=Competency.KNOWLEDGE,
        stem=loc("", stem, audio=False),
        options=[loc("صحیح", "True", audio=False), loc("غلط", "False", audio=False)],
        answer_key={"correct_option": correct},
    )


def test_refuted_claims_and_answer_options_are_teaching_not_requests() -> None:
    lesson = make_valid_lesson()
    refuted = _true_false("You must write your home address in a note.", correct=1)
    lesson.practice_questions = [refuted, *lesson.practice_questions]
    lesson.practice_questions[1].options.append(loc("", "your home address", audio=False))
    assert lesson_personal_detail_requests(lesson) == []
    # The same claim keyed TRUE teaches the child to share it: blocked.
    lesson.practice_questions[0] = _true_false("You must write your home address.", correct=0)
    assert lesson_personal_detail_requests(lesson) == [
        ("practice_questions", "You must write your home address")
    ]


def test_validator_blocks_a_lesson_that_asks_for_family_ages() -> None:
    lesson = make_valid_lesson()
    assert not [f for f in validate(lesson).structural if f.field == "child_safety"]
    lesson.homework[0].stem = loc("", REMOVED_HOMEWORK[1], audio=False)
    findings = [f for f in validate(lesson).structural if f.field == "child_safety"]
    assert len(findings) == 1 and findings[0].severity.value == "blocker"
    assert not validate(lesson).ok


def test_teacher_only_fields_are_not_scanned() -> None:
    """Mentor notes may discuss what *not* to collect; they never reach the child."""
    lesson = make_valid_lesson()
    lesson.mentor_notes = loc("", "Children may mention a house number; do not record it.")
    assert lesson_personal_detail_requests(lesson) == []


def test_no_grade4_lesson_asks_for_personal_details() -> None:
    spine, contents = ci.load_inputs(ROOT)
    service, _ids = ci.generate_service(spine, contents, cad.load_drafts(ROOT, spine))
    lessons = service.list()
    assert len(lessons) == 139
    hits = {
        lesson.learning_outcomes[0]: found
        for lesson in lessons
        if (found := lesson_personal_detail_requests(lesson))
    }
    assert hits == {}
    docs = " ".join(cs_text for cs_text in ci.read_docs(ROOT).values())
    for removed in REMOVED_HOMEWORK:
        assert removed not in docs
