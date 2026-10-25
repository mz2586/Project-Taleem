"""The homework disclosure screen (HOMEWORK_AND_MARKING_CONTRACT §6) — pure, deterministic.

With no teacher reading a child's written answer, nobody reading must not mean nobody protecting.
Every submitted text is compared with an Urdu + English phrase list kept as **configuration**
(``disclosure_phrases.json`` next to this context), not code. A match only escalates to a human:
the service raises one concern in the safeguarding triage queue. The screen never decides, never
replies to the child, and never blocks or changes the submission.

Matching: NFKC; case folded; Arabic-script diacritics and tatweel removed; Arabic letter variants
folded to their Urdu forms (ي→ی, ى→ی, ك→ک); apostrophes dropped; every other non-letter/digit
becomes a space; whitespace collapsed. A phrase matches when its normalised form occurs in the
normalised text as whole words. No fuzzy match, no model, no score.

The list is an engineering STARTER marked pending safeguarding-lead approval (M-Safe).
"""

from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .model import CATEGORY_PRIORITY, PRIORITY_ORDER, Category, parse_category

PHRASES_PATH = Path(__file__).resolve().parents[1] / "disclosure_phrases.json"
STARTER_HEADER = "STARTER LIST — pending safeguarding-lead approval (M-Safe)"

_DIACRITICS = set(range(0x064B, 0x0660)) | {0x0670, 0x0640, 0x06EA, 0x06ED}
_FOLD = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک"})
_APOSTROPHES = {"'", "’", "‘", "`", "ʼ"}


def normalise(text: str) -> str:
    """The screen's canonical form of a text (see the module docstring)."""
    s = unicodedata.normalize("NFKC", text).casefold().translate(_FOLD)
    out: list[str] = []
    for ch in s:
        if ord(ch) in _DIACRITICS or ch in _APOSTROPHES:
            continue
        cat = unicodedata.category(ch)
        out.append(ch if cat[0] in ("L", "N") or cat == "Mn" else " ")
    return " ".join("".join(out).split())


@dataclass(frozen=True)
class Phrase:
    phrase_id: str
    lang: str
    category: Category
    normalised: str
    phrase: str = ""  # the list entry as written (shown only to the safeguarding lead)


@dataclass(frozen=True)
class PhraseList:
    header: str
    phrases: tuple[Phrase, ...]

    def matches(self, text: str) -> tuple[Phrase, ...]:
        """Every phrase that occurs in ``text`` as whole words (list order)."""
        padded = f" {normalise(text)} "
        return tuple(p for p in self.phrases if p.normalised and f" {p.normalised} " in padded)


def strongest_category(matched: tuple[Phrase, ...]) -> Category:
    """The matched category with the most urgent priority (T1 before T2 before T3)."""
    return min(
        (p.category for p in matched),
        key=lambda c: (PRIORITY_ORDER[CATEGORY_PRIORITY[c]], c.value),
    )


def parse_phrase_list(data: object) -> PhraseList:
    if not isinstance(data, dict):
        raise ValueError("the disclosure phrase list must be a JSON object")
    header = str(data.get("_header", ""))
    raw = data.get("phrases")
    if not isinstance(raw, list) or not raw:
        raise ValueError("the disclosure phrase list has no phrases")
    phrases: list[Phrase] = []
    seen: set[str] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("each disclosure phrase must be an object")
        phrase_id = str(entry.get("id", ""))
        if not phrase_id or phrase_id in seen:
            raise ValueError(f"disclosure phrase id {phrase_id!r} is missing or repeated")
        seen.add(phrase_id)
        normalised = normalise(str(entry.get("phrase", "")))
        if not normalised:
            raise ValueError(f"disclosure phrase {phrase_id} is empty")
        phrases.append(
            Phrase(
                phrase_id=phrase_id,
                lang=str(entry.get("lang", "")),
                category=parse_category(str(entry.get("category", ""))),
                normalised=normalised,
                phrase=str(entry.get("phrase", "")),
            )
        )
    return PhraseList(header=header, phrases=tuple(phrases))


@lru_cache(maxsize=1)
def default_phrase_list() -> PhraseList:
    """The shipped list (read once per process)."""
    return parse_phrase_list(json.loads(PHRASES_PATH.read_text(encoding="utf-8")))
