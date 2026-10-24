"""Assessment scoring (pure) — evaluate a learner's answer against an approved item.

Scores every interaction kind of ITEM_INTERACTION_CONTRACT.md §4 (choose / fill / order / match /
sort) and detects the authored misconception a wrong answer implies (the item's
``option_misconceptions`` map for a chosen option, else its item-level ``misconception``), turning
"wrong" into a named mental model the runtime can address (STUDENT_MODEL §3, LEARNING_SCIENCE §5).
No I/O; deterministic.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

from .curriculum_view import CHOOSE, FILL, MATCH, ORDER, SORT, ItemView
from .values import Outcome

MAX_TEXT_CHARS = 200  # a typed (fill) answer
MAX_SEQUENCE = 64  # an order / pairs answer (no authored item comes near this)

# The single answer field each kind accepts (contract §3).
ANSWER_FIELD: dict[str, str] = {
    CHOOSE: "option",
    FILL: "text",
    ORDER: "order",
    MATCH: "pairs",
    SORT: "pairs",
}
ANSWER_FIELDS: tuple[str, ...] = ("option", "text", "order", "pairs")


class AnswerShapeError(ValueError):
    """The answer is malformed: not exactly one well-typed answer field."""


class AnswerKindMismatchError(ValueError):
    """The answer's field does not fit the item's kind (e.g. ``text`` for a choose item)."""


@dataclass(frozen=True)
class Answer:
    """A learner's answer: exactly one of ``option`` / ``text`` / ``order`` / ``pairs``."""

    option: int | None = None
    text: str | None = None
    order: tuple[int, ...] | None = None
    pairs: tuple[tuple[int, int], ...] | None = None

    def __post_init__(self) -> None:
        present = [f for f in ANSWER_FIELDS if getattr(self, f) is not None]
        if len(present) != 1:
            raise AnswerShapeError("exactly one of option / text / order / pairs is required")
        if self.text is not None and len(self.text) > MAX_TEXT_CHARS:
            raise AnswerShapeError(f"text is longer than {MAX_TEXT_CHARS} characters")
        for seq in (self.order, self.pairs):
            if seq is not None and len(seq) > MAX_SEQUENCE:
                raise AnswerShapeError(f"at most {MAX_SEQUENCE} entries")

    @property
    def field(self) -> str:
        """The answer field this answer carries."""
        return next(f for f in ANSWER_FIELDS if getattr(self, f) is not None)

    def summary(self) -> str:
        """A compact text form of the answer (the session's student turn)."""
        if self.option is not None:
            return str(self.option)
        if self.text is not None:
            return self.text
        if self.order is not None:
            return ",".join(str(i) for i in self.order)
        return ",".join(f"{left}-{right}" for left, right in self.pairs or ())

    @classmethod
    def from_payload(cls, payload: Mapping[str, object]) -> Answer:
        """Parse the answer fields of an API body or sync payload (strictly typed).

        A field set to ``None`` counts as absent. Raises ``AnswerShapeError`` on anything else
        than exactly one well-typed field.
        """
        present = {f: payload[f] for f in ANSWER_FIELDS if payload.get(f) is not None}
        if len(present) != 1:
            raise AnswerShapeError("exactly one of option / text / order / pairs is required")
        (name, value), *_ = present.items()
        if name == "option":
            if not isinstance(value, int) or isinstance(value, bool):
                raise AnswerShapeError("option must be an integer")
            return cls(option=value)
        if name == "text":
            if not isinstance(value, str):
                raise AnswerShapeError("text must be a string")
            return cls(text=value)
        if name == "order":
            ints = _int_list(value)
            if ints is None:
                raise AnswerShapeError("order must be a list of option indices")
            return cls(order=tuple(ints))
        if not isinstance(value, (list, tuple)):
            raise AnswerShapeError("pairs must be a list of [left, right]")
        pairs: list[tuple[int, int]] = []
        for p in value:
            ints = _int_list(p)
            if ints is None or len(ints) != 2:
                raise AnswerShapeError("pairs must be a list of [left, right]")
            pairs.append((ints[0], ints[1]))
        return cls(pairs=tuple(pairs))


def _int_list(value: object) -> list[int] | None:
    if not isinstance(value, (list, tuple)):
        return None
    ints = [v for v in value if isinstance(v, int) and not isinstance(v, bool)]
    return ints if len(ints) == len(value) else None


def answer_fits(item: ItemView, answer: Answer) -> bool:
    """Whether ``answer`` carries the field ``item``'s kind expects."""
    return ANSWER_FIELD.get(item.kind) == answer.field


# Urdu (Extended Arabic-Indic) and Arabic-Indic digits -> ASCII.
_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_DIGIT_SEPARATOR = re.compile(r"(?<=[0-9])[,٬](?=[0-9])")
_TRAILING = re.compile(r"[\s.۔!?]+$")


def normalize(text: str) -> str:
    """Canonical form of a typed answer (contract §4).

    NFKC; Urdu/Arabic-Indic digits to ASCII; ``,``/``٬`` between digits removed; whitespace trimmed
    and collapsed; case folded; trailing ``. ۔ ! ?`` stripped.
    """
    s = unicodedata.normalize("NFKC", text).translate(_DIGITS)
    s = _DIGIT_SEPARATOR.sub("", s)
    s = " ".join(s.split()).casefold()
    return _TRAILING.sub("", s)


def _is_correct(item: ItemView, answer: Answer) -> bool:
    if item.kind == CHOOSE:
        return answer.option == item.correct_option
    if item.kind == FILL:
        given = normalize(answer.text or "")
        return bool(given) and any(given == normalize(a) for a in item.accepted_answers)
    if item.kind == ORDER:
        return bool(item.correct_order) and answer.order == item.correct_order
    return bool(item.correct_pairs) and set(answer.pairs or ()) == item.correct_pairs


def evaluate(item: ItemView, answer: Answer | int) -> tuple[Outcome, tuple[str, ...]]:
    """Return (outcome, misconception_refs) for an answer.

    An ``int`` is a chosen option index (the pre-contract call shape, still valid for choose
    items). Raises ``AnswerKindMismatchError`` if the answer's field does not fit the item's kind.
    """
    ans = Answer(option=answer) if isinstance(answer, int) else answer
    if not answer_fits(item, ans):
        raise AnswerKindMismatchError(
            f"a {item.kind} item takes {ANSWER_FIELD.get(item.kind, '?')!r}, not {ans.field!r}"
        )
    if _is_correct(item, ans):
        return Outcome.CORRECT, ()
    ref = item.option_misconceptions.get(ans.option) if ans.option is not None else None
    ref = ref or item.misconception
    return Outcome.INCORRECT, (ref,) if ref else ()
