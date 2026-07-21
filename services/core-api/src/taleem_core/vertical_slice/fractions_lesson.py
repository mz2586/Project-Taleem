"""ORIGINAL sample lesson: Grade 4 · Mathematics · Introduction to Fractions.

Authored original content (NOT copied from any textbook) for the Phase-4.1 vertical slice. Aligned
to an NCP-style Student Learning Outcome; provenance is ``authored-original``. Practice items encode
their correct option, the misconception a wrong option implies, and the authored correction — the
data the learning context's scorer and teaching runtime consume.
"""

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
    WorkedExample,
)
from taleem_core.contexts.curriculum_studio.domain.lesson import (
    Lesson,
    Metadata,
    RemediationRoute,
)
from taleem_core.contexts.curriculum_studio.domain.provenance import Derivation, Provenance

OBJECTIVE_CODE = "MATH-G4-FR-01"
LESSON_KEY = "L-math-g4-intro-fractions"
MISCONCEPTION_BIGGER_DENOMINATOR = "m-bigger-denominator-is-bigger"


def _loc(ur: str, en: str, *, audio: bool = True) -> LocalizedText:
    lt = LocalizedText(text={Locale.UR: ur, Locale.EN: en})
    if audio:
        lt.audio_ref = {Locale.UR: "audio/ur/fractions.mp3", Locale.EN: "audio/en/fractions.mp3"}
    return lt


def _mcq(
    item_id: str,
    stem_ur: str,
    stem_en: str,
    options: list[tuple[str, str]],
    correct_option: int,
    *,
    option_misconceptions: dict[str, str] | None = None,
    corrections: dict[str, str] | None = None,
    hints: list[tuple[str, str]] | None = None,
) -> AssessmentItem:
    answer_key: dict[str, object] = {"correct_option": correct_option}
    if option_misconceptions:
        answer_key["option_misconceptions"] = option_misconceptions
    if corrections:
        answer_key["corrections"] = corrections
    return AssessmentItem(
        item_id=item_id,
        type=ItemType.MCQ,
        objective_ref=OBJECTIVE_CODE,
        competency=Competency.APPLICATION,
        stem=_loc(stem_ur, stem_en, audio=False),
        answer_key=answer_key,
        options=[_loc(ur, en, audio=False) for ur, en in options],
        hints=[Hint(trigger="wrong", hint=_loc(ur, en, audio=False)) for ur, en in (hints or [])],
    )


def build_fractions_lesson() -> Lesson:
    """Return the complete, valid, original Introduction-to-Fractions lesson."""
    practice = [
        _mcq(
            "p1-one-of-four",
            "ایک کیک چار برابر حصوں میں ہے۔ آپ نے ایک حصہ کھایا۔ کونسی کسر؟",
            "A cake has four equal parts. You eat one part. Which fraction?",
            [("ایک بٹا چار", "1/4"), ("چار بٹا ایک", "4/1"), ("ایک", "1")],
            correct_option=0,
        ),
        _mcq(
            "p2-compare-half-quarter",
            "کونسی کسر بڑی ہے: ایک بٹا دو یا ایک بٹا چار؟",
            "Which fraction is bigger: 1/2 or 1/4?",
            [("ایک بٹا دو", "1/2"), ("ایک بٹا چار", "1/4")],
            correct_option=0,
            option_misconceptions={"1": MISCONCEPTION_BIGGER_DENOMINATOR},
            corrections={
                MISCONCEPTION_BIGGER_DENOMINATOR: (
                    "A bigger bottom number means more, smaller pieces. So 1/4 is SMALLER than 1/2."
                )
            },
            hints=[
                ("پیزا کے ٹکڑوں کا سوچیں۔", "Think about pizza slices."),
                ("زیادہ ٹکڑے مطلب چھوٹے ٹکڑے۔", "More slices means smaller slices."),
            ],
        ),
        _mcq(
            "p3-denominator",
            "ایک چاکلیٹ کے تین برابر ٹکڑے ہیں۔ نیچے کا نمبر کیا ہے؟",
            "A chocolate has three equal pieces. What is the bottom number?",
            [("تین", "3"), ("ایک", "1"), ("دو", "2")],
            correct_option=0,
        ),
        _mcq(
            "p4-write-half",
            "آدھے کو کسر میں کیسے لکھتے ہیں؟",
            "How do we write one half as a fraction?",
            [("ایک بٹا دو", "1/2"), ("دو بٹا ایک", "2/1")],
            correct_option=0,
        ),
        _mcq(
            "p5-three-of-four",
            "چار میں سے تین حصے کونسی کسر ہیں؟",
            "Three parts out of four is which fraction?",
            [("تین بٹا چار", "3/4"), ("چار بٹا تین", "4/3")],
            correct_option=0,
        ),
    ]

    return Lesson(
        lesson_id=LESSON_KEY,
        title=_loc("کسر کا تعارف", "Introduction to Fractions"),
        metadata=Metadata(grade_key="G4", subject_key="math", author_role="subject_author"),
        provenance=Provenance(
            derivation=Derivation.AUTHORED_ORIGINAL, aligned_slo_codes=[OBJECTIVE_CODE]
        ),
        ai_teaching_object=AITeachingObject(
            learning_goals=[OBJECTIVE_CODE],
            teaching_strategy="concrete-to-abstract using everyday whole objects",
            questioning_strategy="ask the learner to name parts before naming the fraction",
            hint_policy="graduated; two hints max; never reveal the answer first",
            escalation_rules=["repeated confusion after remediation -> mentor"],
            forbidden_behaviours=["give the final answer", "claim to be a human teacher"],
            misconception_detectors=["chooses the larger denominator as the larger fraction"],
        ),
        assessment=AssessmentBlueprint(formative=list(practice)),
        description=_loc(
            "کسر یعنی مکمل چیز کا ایک برابر حصہ۔", "A fraction is an equal part of a whole."
        ),
        learning_outcomes=[OBJECTIVE_CODE],
        prerequisites=[],
        estimated_duration_min=20,
        difficulty=Difficulty.INTRO,
        keywords=["fraction", "numerator", "denominator", "equal parts"],
        teacher_script=_loc(
            "ہم مکمل چیز کو برابر حصوں میں بانٹتے ہیں۔ ہر حصہ ایک کسر ہے۔",
            "We split a whole into equal parts. Each part is a fraction.",
        ),
        student_explanation=_loc(
            "ایک مکمل چیز کو برابر حصوں میں بانٹتے ہیں۔ ہر حصہ ایک کسر ہے۔ "
            "اوپر کا نمبر حصے گنتا ہے۔ نیچے کا نمبر کل حصے بتاتا ہے۔",
            "We split a whole into equal parts. Each part is a fraction. "
            "The top number counts the parts. The bottom number shows the total.",
        ),
        worked_examples=[
            WorkedExample(
                prompt=_loc(
                    "ایک کیک کو چار برابر حصوں میں کاٹیں۔",
                    "Cut a cake into four equal parts.",
                    audio=False,
                ),
                steps=[
                    _loc("ایک حصہ کھایا۔", "You eat one part.", audio=False),
                    _loc("یہ ایک بٹا چار ہے۔", "This is one over four.", audio=False),
                    _loc("اسے 1/4 لکھتے ہیں۔", "We write it as 1/4.", audio=False),
                ],
            )
        ],
        visual_concepts=[
            MediaRef(
                media_id="m-fraction-circle",
                kind="svg",
                alt_text=_loc(
                    "چار برابر حصوں والا دائرہ", "A circle split into four equal parts", audio=False
                ),
            )
        ],
        interactive_activities=[
            _mcq(
                "a1-shade-quarter",
                "دائرے کا ایک بٹا چار حصہ منتخب کریں۔",
                "Select one quarter of the circle.",
                [("ایک حصہ", "one part"), ("سب حصے", "all parts")],
                correct_option=0,
            )
        ],
        practice_questions=list(practice),
        hints=[
            Hint(
                trigger="first_wrong",
                hint=_loc("برابر حصوں کو گنیں۔", "Count the equal parts.", audio=False),
            )
        ],
        common_misconceptions=[
            Misconception(
                misconception=_loc(
                    "بڑا نیچے کا نمبر بڑی کسر",
                    "bigger denominator means bigger fraction",
                    audio=False,
                ),
                correction=_loc(
                    "زیادہ حصے مطلب چھوٹے حصے۔", "More parts means smaller parts.", audio=False
                ),
            )
        ],
        adaptive_remediation=[
            RemediationRoute(
                signal=f"misconception:{MISCONCEPTION_BIGGER_DENOMINATOR}",
                remediation_ref=OBJECTIVE_CODE,
            )
        ],
        homework=[
            _mcq(
                "hw1-half-of-two",
                "دو سیبوں میں سے ایک کونسی کسر ہے؟",
                "One out of two apples is which fraction?",
                [("ایک بٹا دو", "1/2"), ("دو بٹا ایک", "2/1")],
                correct_option=0,
            )
        ],
        revision_notes=_loc("کسر مکمل کا برابر حصہ ہے۔", "A fraction is an equal part of a whole."),
        summary=_loc("ہم نے کسر کا مطلب سیکھا۔", "We learned what a fraction means."),
        parent_notes=_loc(
            "بچے کے ساتھ کھانا برابر حصوں میں بانٹیں۔",
            "Share food into equal parts with your child.",
        ),
        mentor_notes=_loc(
            "نیچے کے نمبر کی غلط فہمی پر دھیان دیں۔", "Watch for the denominator misconception."
        ),
        accessibility_notes=_loc("آڈیو اور تصویر موجود ہیں۔", "Audio and image are provided."),
        offline_package="pkg/math-g4-intro-fractions",
    )
