"""Assessment scoring (pure) — evaluate a learner's answer against an approved item.

Detects the specific authored misconception a wrong answer implies (via the item's
``option_misconceptions`` map), turning "wrong" into a named mental model the runtime can address
(STUDENT_MODEL §3, LEARNING_SCIENCE §5). No I/O; deterministic.
"""

from __future__ import annotations

from .curriculum_view import ItemView
from .values import Outcome


def evaluate(item: ItemView, answer_option: int) -> tuple[Outcome, tuple[str, ...]]:
    """Return (outcome, misconception_refs) for a chosen option index."""
    if answer_option == item.correct_option:
        return Outcome.CORRECT, ()
    ref = item.option_misconceptions.get(answer_option)
    return Outcome.INCORRECT, (ref,) if ref else ()
