"""Studio side of ITEM_INTERACTION_CONTRACT.md: interaction kinds and canonical answer keys."""

from __future__ import annotations

from typing import Any

import pytest

from taleem_core.contexts.curriculum_studio.domain.assessment import (
    AssessmentItem,
    Competency,
    ItemType,
)
from taleem_core.contexts.curriculum_studio.domain.interaction import (
    answer_key_errors,
    interaction_kind,
)
from taleem_core.contexts.curriculum_studio.domain.validation import validate
from tests.studio_helpers import loc, make_valid_lesson


def _item(kind: ItemType, key: dict[str, Any], n_options: int = 0) -> AssessmentItem:
    return AssessmentItem(
        item_id="i1",
        type=kind,
        objective_ref="SLO-1",
        competency=Competency.APPLICATION,
        stem=loc("سوال", "Question", audio=False),
        options=[loc(f"ا{i}", f"o{i}", audio=False) for i in range(n_options)],
        answer_key=key,
    )


@pytest.mark.parametrize(
    ("kind", "key", "expected"),
    [
        (ItemType.MCQ, {}, "choose"),
        (ItemType.TRUE_FALSE, {}, "choose"),
        (ItemType.FILL_BLANK, {}, "fill"),
        (ItemType.ORDERING, {}, "order"),
        (ItemType.MATCHING, {}, "match"),
        (ItemType.INTERACTIVE, {"mode": "sort"}, "sort"),
        (ItemType.INTERACTIVE, {"mode": "choose"}, "choose"),
        (ItemType.INTERACTIVE, {}, None),  # a widget
        (ItemType.INTERACTIVE, {"mode": "clock"}, None),
        (ItemType.SHORT, {}, None),  # human-graded
        (ItemType.LONG, {}, None),
    ],
)
def test_interaction_kind(kind: ItemType, key: dict[str, Any], expected: str | None) -> None:
    assert interaction_kind(_item(kind, key)) == expected


@pytest.mark.parametrize(
    ("kind", "key", "n"),
    [
        (ItemType.MCQ, {}, 0),  # unkeyed choose items predate the contract
        (ItemType.MCQ, {"correct_option": 2}, 3),
        (ItemType.FILL_BLANK, {"answer": "40"}, 0),
        (ItemType.ORDERING, {"order": [2, 0, 1]}, 3),
        (ItemType.MATCHING, {"left_count": 2, "pairs": [[0, 3], [1, 2]]}, 4),
        (
            ItemType.INTERACTIVE,
            {"mode": "sort", "left_count": 3, "pairs": [[0, 3], [1, 4], [2, 3]]},
            5,
        ),
        (ItemType.INTERACTIVE, {"descriptive": "a widget key"}, 0),
        (ItemType.ORDERING, {"order": [1, 0], "misconception": "m-x"}, 2),
    ],
)
def test_canonical_keys_pass(kind: ItemType, key: dict[str, Any], n: int) -> None:
    assert answer_key_errors(_item(kind, key, n)) == []


@pytest.mark.parametrize(
    ("kind", "key", "n", "message"),
    [
        (ItemType.MCQ, {"correct_option": 3}, 3, "correct_option"),
        (ItemType.MCQ, {"correct_option": True}, 3, "correct_option"),
        (ItemType.FILL_BLANK, {}, 0, "answer"),
        (ItemType.FILL_BLANK, {"answer": "  "}, 0, "answer"),
        (ItemType.ORDERING, {"order": [0, 1]}, 3, "permutation"),
        (ItemType.ORDERING, {"order": ["b", "a"]}, 2, "permutation"),
        (ItemType.ORDERING, {"order": [0]}, 1, "permutation"),
        (ItemType.MATCHING, {"pairs": {"a": "b"}}, 4, "left_count"),
        (ItemType.MATCHING, {"left_count": 2, "pairs": [[0, 2]]}, 4, "exactly once"),
        (ItemType.MATCHING, {"left_count": 2, "pairs": [[0, 1], [1, 2]]}, 4, "right index"),
        (ItemType.MATCHING, {"left_count": 2, "pairs": [[0, 2], [1, 2]]}, 4, "used once"),
        (ItemType.INTERACTIVE, {"mode": "sort", "left_count": 3, "pairs": [[0, 3]]}, 5, "once"),
        (ItemType.ORDERING, {"order": [1, 0], "misconception": ""}, 2, "misconception"),
    ],
)
def test_malformed_keys_are_reported(
    kind: ItemType, key: dict[str, Any], n: int, message: str
) -> None:
    errors = answer_key_errors(_item(kind, key, n))
    assert errors and message in " ".join(errors)


def test_validator_blocks_a_lesson_with_a_malformed_key() -> None:
    lesson = make_valid_lesson()
    assert not [f for f in validate(lesson).structural if f.field == "answer_key"]
    lesson.interactive_activities.append(_item(ItemType.ORDERING, {"order": [0, 0]}, 2))
    (finding,) = [f for f in validate(lesson).structural if f.field == "answer_key"]
    assert finding.severity.value == "blocker"
    assert "interactive_activities[i1]" in finding.message
