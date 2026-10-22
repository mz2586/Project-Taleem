"""Shared value objects for curriculum content (pure-stdlib).

Localized text with recorded-audio pointers, difficulty, and content blocks.
See docs/10-curriculum-studio/CONTENT_STYLE_GUIDE.md and TRANSLATION_STANDARD.md.

Which locales a field must be complete in, which need recorded audio, and which are measured for
readability are *curriculum-pack* policy (``packs.py``), not properties of the text itself.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import ClassVar


class Difficulty(StrEnum):
    INTRO = "intro"
    DEVELOPING = "developing"
    SECURE = "secure"
    CHALLENGE = "challenge"


# BCP-47-ish: a 2-3 letter lowercase primary language subtag, then optional script/region/variant
# subtags (e.g. "ur", "en", "en-GB", "pa-Arab"). Whether a well-formed tag is *usable* is decided by
# the curriculum-pack registry, not by this type.
_LOCALE_TAG = re.compile(r"[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})*")


class Locale(str):
    """An open, validated locale tag (a ``str``), replacing the former closed ``ur``/``en`` enum.

    ``Locale("ur") == "ur"`` and hashes identically, so dicts keyed by ``Locale`` read and persist
    exactly as before. ``Locale.UR`` / ``Locale.EN`` and ``.value`` stay for compatibility.
    """

    __slots__ = ()

    UR: ClassVar[Locale]
    EN: ClassVar[Locale]

    def __new__(cls, tag: str) -> Locale:
        if isinstance(tag, Locale):
            return tag
        if not isinstance(tag, str) or not _LOCALE_TAG.fullmatch(tag):
            raise ValueError(f"not a valid locale tag: {tag!r}")
        return super().__new__(cls, tag)

    @property
    def value(self) -> str:
        return str.__str__(self)


Locale.UR = Locale("ur")  # Urdu
Locale.EN = Locale("en")  # English


@dataclass
class LocalizedText:
    """A localized field; ``audio_ref`` carries recorded-audio pointers per locale."""

    text: dict[Locale, str] = field(default_factory=dict)
    audio_ref: dict[Locale, str] = field(default_factory=dict)

    def has(self, locale: Locale) -> bool:
        return bool(self.text.get(locale, "").strip())

    def is_complete_in(self, locales: Iterable[Locale]) -> bool:
        """True iff text is present in every one of ``locales`` (a pack's required locales)."""
        return all(self.has(loc) for loc in locales)

    def has_audio(self, locale: Locale) -> bool:
        return bool(self.audio_ref.get(locale, "").strip())

    def is_complete_core(self) -> bool:
        """PK-NCP core-path rule: Urdu and English present (TRANSLATION_STANDARD §2).

        Kept for compatibility; the gates use ``is_complete_in(pack required locales)``.
        """
        return self.is_complete_in((Locale.UR, Locale.EN))

    def has_urdu_audio(self) -> bool:
        return self.has_audio(Locale.UR)


@dataclass
class VocabularyTerm:
    term: LocalizedText
    definition: LocalizedText
    pronunciation_audio_ref: str = ""


@dataclass
class Misconception:
    misconception: LocalizedText
    correction: LocalizedText


@dataclass
class Hint:
    trigger: str  # what prompts this hint (e.g. "first_wrong_attempt")
    hint: LocalizedText  # graduated; never the answer first (enforced by AI teaching object)


@dataclass
class WorkedExample:
    prompt: LocalizedText
    steps: list[LocalizedText] = field(default_factory=list)


@dataclass
class MediaRef:
    """Reference to a media asset (SVG/diagram/audio/animation). Original or CC0 only."""

    media_id: str
    kind: str  # svg | diagram | animation | audio | image | widget
    alt_text: LocalizedText = field(default_factory=LocalizedText)
