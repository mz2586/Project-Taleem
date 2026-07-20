"""Test helpers for Curriculum Studio — build a fully-valid lesson (no production content)."""

from __future__ import annotations

from taleem_core.contexts.curriculum_studio.domain.ai_teaching import AITeachingObject
from taleem_core.contexts.curriculum_studio.domain.assessment import (
    AssessmentBlueprint,
    AssessmentItem,
    Competency,
    ItemType,
)
from taleem_core.contexts.curriculum_studio.domain.content import (
    Difficulty,
    Hint,
    Locale,
    LocalizedText,
    MediaRef,
    Misconception,
)
from taleem_core.contexts.curriculum_studio.domain.lesson import (
    Lesson,
    Metadata,
    RemediationRoute,
)
from taleem_core.contexts.curriculum_studio.domain.provenance import Derivation, Provenance

SLO = "MATH-G1-N-01"


def loc(ur: str, en: str, audio: bool = True) -> LocalizedText:
    lt = LocalizedText(text={Locale.UR: ur, Locale.EN: en})
    if audio:
        lt.audio_ref = {Locale.UR: "audio/ur.mp3", Locale.EN: "audio/en.mp3"}
    return lt


def _item(item_id: str, item_type: ItemType = ItemType.MCQ) -> AssessmentItem:
    return AssessmentItem(
        item_id=item_id,
        type=item_type,
        objective_ref=SLO,
        competency=Competency.APPLICATION,
        stem=loc("گنو۔", "Count."),
    )


def make_valid_lesson(lesson_id: str = "L1") -> Lesson:
    """A lesson that passes all structural + automated-gate checks (short sentences)."""
    return Lesson(
        lesson_id=lesson_id,
        title=loc("گنتی", "Counting"),
        metadata=Metadata(grade_key="G1", subject_key="math", author_role="subject_author"),
        provenance=Provenance(derivation=Derivation.AUTHORED_ORIGINAL, aligned_slo_codes=[SLO]),
        ai_teaching_object=AITeachingObject(
            learning_goals=[SLO],
            teaching_strategy="concrete-first",
            questioning_strategy="socratic",
            hint_policy="graduated; cap 3; never answer-first",
            escalation_rules=["distress -> mentor"],
            forbidden_behaviours=["give the answer", "claim to be human"],
            misconception_detectors=["counts objects twice"],
        ),
        assessment=AssessmentBlueprint(formative=[_item("f1")]),
        description=loc("گنتی سیکھیں۔", "Learn counting."),
        learning_outcomes=[SLO],
        prerequisites=[],
        estimated_duration_min=15,
        difficulty=Difficulty.INTRO,
        keywords=["count", "numbers"],
        teacher_script=loc("ہم گنتے ہیں۔", "We count."),
        student_explanation=loc("ہم گنتے ہیں۔ ایک۔ دو۔ تین۔", "We count. One. Two. Three."),
        visual_concepts=[
            MediaRef(media_id="m1", kind="svg", alt_text=loc("تین سیب", "Three apples"))
        ],
        interactive_activities=[_item("a1", ItemType.INTERACTIVE)],
        practice_questions=[_item("p1"), _item("p2"), _item("p3")],
        hints=[Hint(trigger="first_wrong", hint=loc("دوبارہ گنو۔", "Count again."))],
        common_misconceptions=[
            Misconception(
                misconception=loc("دو بار گننا", "double-count"), correction=loc("ایک بار", "once")
            )
        ],
        adaptive_remediation=[
            RemediationRoute(signal="miss:prereq", remediation_ref="MATH-G1-N-00")
        ],
        homework=[_item("h1")],
        revision_notes=loc("گنتی دہرائیں۔", "Revise counting."),
        summary=loc("ہم نے گننا سیکھا۔", "We learned to count."),
        parent_notes=loc("بچے کے ساتھ گنیں۔", "Count with your child."),
        mentor_notes=loc("گننے پر دھیان دیں۔", "Watch counting."),
        accessibility_notes=loc("آڈیو موجود ہے۔", "Audio present."),
        offline_package="pkg/L1",
    )
