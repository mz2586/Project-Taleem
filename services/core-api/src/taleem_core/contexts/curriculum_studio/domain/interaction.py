"""Item interaction kinds and canonical answer-key shapes (pure-stdlib).

See docs/10-curriculum-studio/ITEM_INTERACTION_CONTRACT.md. The learner runtime can score five
kinds: ``choose`` (mcq/true_false), ``fill``, ``order``, ``match`` and ``sort``. An ``interactive``
item states its kind in ``answer_key.mode``; an interactive item with no known mode is a *widget*
(no runtime yet): valid content, never projected to the learner or scored.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .assessment import AssessmentItem, ItemType

CHOOSE, FILL, ORDER, MATCH, SORT = "choose", "fill", "order", "match", "sort"
KINDS: tuple[str, ...] = (CHOOSE, FILL, ORDER, MATCH, SORT)

_BY_TYPE: dict[ItemType, str] = {
    ItemType.MCQ: CHOOSE,
    ItemType.TRUE_FALSE: CHOOSE,
    ItemType.FILL_BLANK: FILL,
    ItemType.ORDERING: ORDER,
    ItemType.MATCHING: MATCH,
}


def interaction_kind(item: AssessmentItem) -> str | None:
    """The runtime kind of ``item``; ``None`` for a widget or a human-graded item."""
    if item.type is ItemType.INTERACTIVE:
        mode = item.answer_key.get("mode")
        return mode if isinstance(mode, str) and mode in KINDS else None
    return _BY_TYPE.get(item.type)


def _ints(value: Any) -> list[int] | None:
    if not isinstance(value, list) or not all(
        isinstance(v, int) and not isinstance(v, bool) for v in value
    ):
        return None
    return list(value)


def _pairs(value: Any) -> list[tuple[int, int]] | None:
    if not isinstance(value, list):
        return None
    out: list[tuple[int, int]] = []
    for p in value:
        ints = _ints(p)
        if ints is None or len(ints) != 2:
            return None
        out.append((ints[0], ints[1]))
    return out


def answer_key_errors(item: AssessmentItem) -> list[str]:
    """Problems with ``item``'s answer key for its kind (empty = canonical).

    ``choose`` keys are checked only when present (unkeyed choose items predate this contract);
    the other kinds must be fully canonical.
    """
    kind = interaction_kind(item)
    key, n = item.answer_key, len(item.options)
    errors: list[str] = []
    if kind == CHOOSE:
        if "correct_option" in key:
            c = key["correct_option"]
            if not isinstance(c, int) or isinstance(c, bool) or not 0 <= c < n:
                errors.append("correct_option must index an option")
    elif kind == FILL:
        answer = key.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            errors.append('fill needs a non-empty "answer"')
    elif kind == ORDER:
        order = _ints(key.get("order"))
        if n < 2 or order is None or sorted(order) != list(range(n)):
            errors.append('order needs >=2 options and "order" = a permutation of their indices')
    elif kind in (MATCH, SORT):
        k = key.get("left_count")
        pairs = _pairs(key.get("pairs"))
        if not isinstance(k, int) or isinstance(k, bool) or not 0 < k < n or pairs is None:
            errors.append(f'{kind} needs 0 < "left_count" < options and "pairs" of [left, right]')
        else:
            lefts = [p[0] for p in pairs]
            rights = [p[1] for p in pairs]
            if sorted(lefts) != list(range(k)):
                errors.append(f"{kind}: every left item (0..{k - 1}) must appear exactly once")
            if any(not k <= r < n for r in rights):
                errors.append(f"{kind}: every right index must be in {k}..{n - 1}")
            if kind == MATCH and len(set(rights)) != len(rights):
                errors.append("match: each right item may be used once (use sort for groups)")
    misconception = key.get("misconception")
    if misconception is not None and not (isinstance(misconception, str) and misconception):
        errors.append('"misconception" must be a non-empty library id')
    return errors


def lesson_answer_key_errors(items: Sequence[tuple[str, AssessmentItem]]) -> list[str]:
    """``"<field>[<item_id>]: <problem>"`` for every item with a non-canonical key."""
    return [f"{name}[{item.item_id}]: {e}" for name, item in items for e in answer_key_errors(item)]
