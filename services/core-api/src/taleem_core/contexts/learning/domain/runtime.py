"""AI Teaching Runtime — templated (no-LLM) tier (AI_TEACHING_RUNTIME.md §2 tier 4a).

This is a *real* implementation, not a mock: it deterministically presents and sequences **approved
lesson content** (explanation, worked examples, authored questions, graduated hints, misconception
corrections). It is offline-capable and in-scope by construction — it can only emit content that
exists in the supplied ``LessonView``. The generative tiers (small/frontier model) plug in behind
the ``LLMGateway`` port later to *rephrase* this content; they never source new curriculum.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .curriculum_view import ItemView, LessonView


class TurnKind(StrEnum):
    PRESENT = "present"  # teach the concept
    ASK = "ask"  # pose a question
    HINT = "hint"  # graduated help
    FEEDBACK = "feedback"  # affirm / correct
    REMEDIATE = "remediate"  # address a misconception


@dataclass(frozen=True)
class Utterance:
    kind: TurnKind
    text: str
    locale: str = "ur"


class TemplatedTeachingRuntime:
    """Deterministic teaching runtime over approved content (the ``TeachingRuntime`` port)."""

    def present(self, lesson: LessonView, locale: str = "ur") -> list[Utterance]:
        """Introduce the concept: title, explanation, then worked-example steps (one at a time)."""
        out = [
            Utterance(
                TurnKind.PRESENT, lesson.title.get(locale, lesson.title.get("en", "")), locale
            ),
            Utterance(
                TurnKind.PRESENT,
                lesson.explanation.get(locale, lesson.explanation.get("en", "")),
                locale,
            ),
        ]
        out.extend(
            Utterance(TurnKind.PRESENT, step, locale) for step in lesson.worked_example_steps
        )
        return out

    def ask(self, item: ItemView, locale: str = "ur") -> Utterance:
        return Utterance(TurnKind.ASK, item.prompt.get(locale, item.prompt.get("en", "")), locale)

    def hint(self, item: ItemView, level: int, locale: str = "ur") -> Utterance | None:
        """Return the graduated hint at `level` (0-based); None if the ladder is exhausted."""
        if 0 <= level < len(item.hints):
            return Utterance(TurnKind.HINT, item.hints[level], locale)
        return None

    def affirm(self, locale: str = "ur") -> Utterance:
        text = "بہت خوب! یہ درست ہے۔" if locale == "ur" else "Well done! That's correct."
        return Utterance(TurnKind.FEEDBACK, text, locale)

    def correct(self, lesson: LessonView, misconception_ref: str, locale: str = "ur") -> Utterance:
        """Deliver the *authored* correction for a misconception (never an invented one)."""
        text = lesson.misconception_corrections.get(
            misconception_ref,
            "آئیے دوبارہ کوشش کرتے ہیں۔" if locale == "ur" else "Let's try that again.",
        )
        return Utterance(TurnKind.REMEDIATE, text, locale)
