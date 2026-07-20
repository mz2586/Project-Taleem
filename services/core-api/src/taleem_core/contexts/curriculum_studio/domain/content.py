"""Shared value objects for curriculum content (pure-stdlib).

Localized (Urdu-first) text with mandatory-audio semantics, difficulty, and content blocks.
See docs/10-curriculum-studio/CONTENT_STYLE_GUIDE.md and TRANSLATION_STANDARD.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Difficulty(StrEnum):
    INTRO = "intro"
    DEVELOPING = "developing"
    SECURE = "secure"
    CHALLENGE = "challenge"


class Locale(StrEnum):
    UR = "ur"  # Urdu — primary
    EN = "en"  # English — secondary


@dataclass
class LocalizedText:
    """A field localized Urdu-first; `audio_ref` carries the mandatory recorded-audio pointer."""

    text: dict[Locale, str] = field(default_factory=dict)
    audio_ref: dict[Locale, str] = field(default_factory=dict)

    def has(self, locale: Locale) -> bool:
        return bool(self.text.get(locale, "").strip())

    def is_complete_core(self) -> bool:
        """Core-path text requires both Urdu and English present (TRANSLATION_STANDARD §2)."""
        return self.has(Locale.UR) and self.has(Locale.EN)

    def has_urdu_audio(self) -> bool:
        return bool(self.audio_ref.get(Locale.UR, "").strip())


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
