"""Child-safety content check (pure-stdlib): no lesson asks a child for personal details.

A learner-facing text that asks the child to write, say or share a home address, a house number,
a phone number or family members' ages is a BLOCKER (doc 15 child-safety framework: data
minimisation; FD on unaccompanied minors). Text that *warns* against sharing them ("never write
your address") is protective and allowed: a sentence containing a negation is not a request.

The check is deliberately narrow: it names the personal details, not every mention of a home or
a family, so ordinary lessons ("draw your home", "help your family") are unaffected.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Iterator
from typing import Any

from .assessment import AssessmentItem, ItemType
from .content import LocalizedText

# Personal details a lesson must never ask a child for (English and Urdu).
_PERSONAL_DETAIL = re.compile(
    r"\b(?:house|home|street)[ -]?(?:number|address)\b"
    r"|\b(?:your|my|their|home|real|postal|full)\s+address(?:es)?\b"
    r"|\b(?:phone|mobile|telephone)[ -]?numbers?\b"
    r"|\b(?:family|family members'?|parents'?|siblings'?)\s+ages?\b"
    r"|\bages? of (?:your|the) (?:family|parents|brothers|sisters|siblings)\b"
    r"|گھر کا (?:نمبر|پتا|پتہ)|گھر کے نمبر|(?:اپنا|اصل|پورا) پت[اہ]|فون نمبر|موبائل نمبر"
    r"|(?:خاندان|گھر والوں|والدین|بہن بھائیوں)(?:\s+\S+){0,3}\s+(?:کی\s+)?عمر",
    re.IGNORECASE,
)
_NEGATION = re.compile(
    r"\b(?:never|not|don't|do not|no|without|avoid|instead of)\b"
    r"|(?<!\S)(?:نہ|نہیں|مت|بغیر)(?!\S)",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"[.!?؟۔\n;؛]+")

# Lesson fields a learner reads or hears (mentor/teacher notes and AI instructions are excluded:
# they may legitimately discuss what *not* to collect).
LEARNER_FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "student_explanation",
    "teacher_script",
    "worked_examples",
    "interactive_activities",
    "practice_questions",
    "challenge_problems",
    "homework",
    "hints",
    "revision_notes",
    "summary",
    "parent_notes",
)


def _refuted(item: AssessmentItem) -> bool:
    """A true/false statement whose keyed answer is "false" is a claim the child rejects."""
    if item.type is not ItemType.TRUE_FALSE:
        return False
    correct = item.answer_key.get("correct_option")
    if not isinstance(correct, int) or not 0 <= correct < len(item.options):
        return False
    keyed = " ".join(item.options[correct].text.values()).lower()
    return "false" in keyed or "غلط" in keyed


def _texts(value: Any) -> Iterator[str]:
    if isinstance(value, AssessmentItem):
        # Answer options are choices, not requests (a wrong option may name what not to share);
        # a refuted true/false claim is likewise taught as wrong. Stems, hints and
        # explanations are checked.
        if not _refuted(value):
            yield from _texts(value.stem)
        yield from _texts(value.hints)
        yield from _texts(value.explanation)
        return
    if isinstance(value, LocalizedText):
        yield from (t for t in value.text.values() if t)
    elif dataclasses.is_dataclass(value) and not isinstance(value, type):
        for f in dataclasses.fields(value):
            yield from _texts(getattr(value, f.name))
    elif isinstance(value, (list, tuple)):
        for v in value:
            yield from _texts(v)


def personal_detail_requests(text: str) -> list[str]:
    """Sentences of ``text`` that ask for a personal detail (and do not warn against it)."""
    hits: list[str] = []
    for sentence in _SENTENCE.split(text):
        if _PERSONAL_DETAIL.search(sentence) and not _NEGATION.search(sentence):
            hits.append(sentence.strip())
    return hits


def lesson_personal_detail_requests(lesson: Any) -> list[tuple[str, str]]:
    """(field, sentence) for every learner-facing request for a personal detail in ``lesson``."""
    found: list[tuple[str, str]] = []
    for name in LEARNER_FIELDS:
        for text in _texts(getattr(lesson, name, None)):
            found += [(name, s) for s in personal_detail_requests(text)]
    return found
