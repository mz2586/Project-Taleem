"""AI Teacher generative tier — grounded prompt + safety gate (pure; Phase D).

The generative tier may only **rephrase** text the templated teacher already chose from a published
``LessonView``. This module holds the two pure halves of that contract:

1. ``build_prompt`` — the prompt is built *solely* from LessonView fields (each passage keeps its
   field path, which becomes the output's provenance) plus fixed instruction text and the coarse
   age band. No learner identifier, mastery, attempt history, or answer key is ever included.
2. ``gate`` — every model output is checked before it can reach a child. Any violation means the
   output is **refused, not softened**: the caller discards it and serves the authored response.

Rules (each violation carries a ``GateRule``; the evaluation harness scores them by dimension):

- grounding — every number (digits, number words, simple fractions) must appear in the grounding;
  most content words must come from the grounding (``ungrounded_content``); comparison and
  universality words ("always", "bigger"...) must already occur there (``ungrounded_claim``);
  output must not be empty.
- semantic consistency (grounding dimension) — a misstatement built only from grounded words passes
  the lexical rules, so: every statement relating numbers must be exactly true (``Fraction``) or
  authored verbatim (``false_arithmetic``; unreadable relations: ``unverified_numeric_claim``);
  each sentence's negations and comparison directions must match a passage sentence it rephrases
  (``polarity_mismatch``); a clause may not splice parts of two passage sentences
  (``recombined_clause``); a clause's numbers must come from the sentence it rephrases
  (``misplaced_number``).
- answer leak — no item's correct option may appear more often than it already does in the
  grounding, and no answer-revealing phrasing ("the answer is…") — unless that item's hint ladder is
  exhausted (``AnswerContext``).
- age band — total length, sentence length, and novel long words are capped per band.
- safety — no URLs, emails, phone numbers, social handles, requests for personal data, secrecy or
  meeting requests, impersonation of a human, prompt-injection echoes, markup, or unsafe vocabulary.
- locale — the output's script must match the requested locale; an unknown locale is refused.

These are deliberately conservative pattern checks: a false refusal costs a child a rephrase (they
still get the authored text); a false acceptance could cost far more.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from enum import StrEnum
from fractions import Fraction

from .ai_teacher import is_grounded
from .curriculum_view import CHOOSE, FILL, ItemView, LessonView
from .runtime import Utterance

# The feature flag that turns the generative tier on (deny-by-default: unset means OFF).
GENERATIVE_FLAG = "ai_teacher.generative_rephrase"


# ============================================================================ provenance + prompt


@dataclass(frozen=True)
class GroundingPassage:
    """One LessonView text the model may rephrase, with the field it came from."""

    field: str  # e.g. "lesson.explanation.en", "lesson.worked_example_steps[1]"
    text: str


def _item_pools(lesson: LessonView) -> tuple[tuple[str, tuple[ItemView, ...]], ...]:
    return (
        ("practice_items", lesson.practice_items),
        ("homework_items", lesson.homework_items),
        ("assessment_formative", lesson.assessment_formative),
        ("assessment_summative", lesson.assessment_summative),
    )


def lesson_passages(lesson: LessonView) -> tuple[GroundingPassage, ...]:
    """Every authored LessonView text with its field path. Answer options are never passages."""
    out: list[GroundingPassage] = []
    out.extend(GroundingPassage(f"lesson.title.{k}", v) for k, v in lesson.title.items() if v)
    out.extend(
        GroundingPassage(f"lesson.explanation.{k}", v) for k, v in lesson.explanation.items() if v
    )
    out.extend(
        GroundingPassage(f"lesson.worked_example_steps[{i}]", s)
        for i, s in enumerate(lesson.worked_example_steps)
        if s
    )
    out.extend(
        GroundingPassage(f"lesson.worked_example_steps_localized[{i}].{k}", v)
        for i, step in enumerate(lesson.worked_example_steps_localized)
        for k, v in step.items()
        # The English text is already the ``worked_example_steps[i]`` passage; don't list it twice.
        if v and (i >= len(lesson.worked_example_steps) or v != lesson.worked_example_steps[i])
    )
    out.extend(
        GroundingPassage(f"lesson.misconception_corrections[{ref}]", text)
        for ref, text in lesson.misconception_corrections.items()
        if text
    )
    for pool_name, pool in _item_pools(lesson):
        for item in pool:
            base = f"lesson.{pool_name}[{item.item_ref}]"
            out.extend(
                GroundingPassage(f"{base}.prompt.{k}", v) for k, v in item.prompt.items() if v
            )
            out.extend(
                GroundingPassage(f"{base}.hints[{i}]", h) for i, h in enumerate(item.hints) if h
            )
    return tuple(out)


@dataclass(frozen=True)
class AgeBand:
    name: str
    description: str
    max_words: int
    max_sentence_words: int
    max_novel_long_words: int  # long words (see _LONG_WORD) the grounding does not already use


AGE_BANDS: dict[str, AgeBand] = {
    "early": AgeBand("early", "young (early primary)", 45, 12, 0),
    "middle": AgeBand("middle", "primary-school", 80, 16, 1),
    "senior": AgeBand("senior", "older", 130, 22, 3),
}


def age_band(grade_band: str) -> AgeBand:
    """Unknown bands get the strictest limits (fail closed)."""
    return AGE_BANDS.get(grade_band, AGE_BANDS["early"])


# Locale -> (script, language name). A locale missing here cannot be verified, so it is refused.
_LOCALES: dict[str, tuple[str, str]] = {
    "ur": ("arabic", "Urdu"),
    "ar": ("arabic", "Arabic"),
    "fa": ("arabic", "Persian"),
    "ps": ("arabic", "Pashto"),
    "sd": ("arabic", "Sindhi"),
    "en": ("latin", "English"),
    "fr": ("latin", "French"),
    "es": ("latin", "Spanish"),
    "id": ("latin", "Indonesian"),
    "ms": ("latin", "Malay"),
    "sw": ("latin", "Swahili"),
    "tr": ("latin", "Turkish"),
}


@dataclass(frozen=True)
class GroundedPrompt:
    """What the model is given — and the only material its output may draw on."""

    lesson_id: str
    objective_code: str
    locale: str
    grade_band: str
    passages: tuple[GroundingPassage, ...]

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(p.field for p in self.passages)

    @property
    def texts(self) -> tuple[str, ...]:
        return tuple(p.text for p in self.passages)

    def render(self) -> str:
        band = age_band(self.grade_band)
        language = _LOCALES.get(self.locale, ("", self.locale))[1]
        lines = [
            f"Rephrase the approved lesson passages below for a {band.description} learner, "
            f"in {language}.",
            "Use ONLY the facts and numbers in the passages. Add no new facts and no new numbers.",
            "Do not answer any question in the passages and do not say which option is correct.",
            "No links, no contact details, and no questions about the learner.",
            f"At most {band.max_words} words; "
            f"at most {band.max_sentence_words} words per sentence.",
            "Passages:",
        ]
        lines.extend(f"[{i}] {p.text}" for i, p in enumerate(self.passages, 1))
        return "\n".join(lines)


_STEP_FIELD = re.compile(r"^lesson\.worked_example_steps\[(\d+)\]$")


def _localized_step(
    lesson: LessonView, passage: GroundingPassage, locale: str
) -> GroundingPassage | None:
    match = _STEP_FIELD.match(passage.field)
    if match is None:
        return None
    index = int(match.group(1))
    if index >= len(lesson.worked_example_steps_localized):
        return None
    text = lesson.worked_example_steps_localized[index].get(locale, "")
    if not text or text == passage.text:
        return None
    return GroundingPassage(f"lesson.worked_example_steps_localized[{index}].{locale}", text)


class UngroundedPromptError(ValueError):
    """Raised if a prompt would carry text that is not authored lesson content."""


def build_prompt(
    lesson: LessonView, utterances: tuple[Utterance, ...], *, locale: str, grade_band: str
) -> GroundedPrompt:
    """Build the rephrase prompt from the templated utterances, mapped back to LessonView fields.

    Fixed system phrases are not sent (nothing to rephrase); any other text that is not authored
    lesson content aborts the build — ungrounded text never reaches a model.
    """
    if not is_grounded(lesson, utterances):
        raise UngroundedPromptError("refusing to prompt with non-authored text")
    by_text: dict[str, list[GroundingPassage]] = {}
    for passage in lesson_passages(lesson):
        by_text.setdefault(passage.text, []).append(passage)
    chosen: list[GroundingPassage] = []
    seen: set[str] = set()
    for u in utterances:
        candidates = by_text.get(u.text)
        if not candidates or u.text in seen:
            continue  # a fixed system phrase, or a duplicate
        # Prefer the field in the utterance's own locale when the same text is stored twice.
        preferred = [c for c in candidates if c.field.endswith(f".{u.locale}")]
        passage = (preferred or candidates)[0]
        chosen.append(passage)
        seen.add(u.text)
        # The runtime presents worked steps in their English projection; when the authored step
        # exists in the requested locale, ground the rephrase on that version too (same step).
        localized = _localized_step(lesson, passage, locale)
        if localized is not None and localized.text not in seen:
            chosen.append(localized)
            seen.add(localized.text)
    return GroundedPrompt(
        lesson_id=lesson.lesson_id,
        objective_code=lesson.objective_code,
        locale=locale,
        grade_band=grade_band,
        passages=tuple(chosen),
    )


# ============================================================================ text analysis

_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NUMERAL = re.compile(r"\d+(?:[.,/]\d+)*")
_WORD = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")
_SENTENCE_SPLIT = re.compile(r"[.!?۔؟\n]+")

_NUMBER_WORDS: dict[str, str] = {
    # English
    "zero": "0",
    "one": "1",
    "two": "2",
    "three": "3",
    "four": "4",
    "five": "5",
    "six": "6",
    "seven": "7",
    "eight": "8",
    "nine": "9",
    "ten": "10",
    "eleven": "11",
    "twelve": "12",
    "thirteen": "13",
    "fourteen": "14",
    "fifteen": "15",
    "sixteen": "16",
    "seventeen": "17",
    "eighteen": "18",
    "nineteen": "19",
    "twenty": "20",
    "thirty": "30",
    "forty": "40",
    "fifty": "50",
    "sixty": "60",
    "seventy": "70",
    "eighty": "80",
    "ninety": "90",
    "hundred": "100",
    "thousand": "1000",
    "million": "1000000",
    "half": "1/2",
    "halves": "1/2",
    "quarter": "1/4",
    "quarters": "1/4",
    # Fraction words: without these "you eat a third" would carry a number the check never saw.
    "third": "1/3",
    "thirds": "1/3",
    "fourth": "1/4",
    "fourths": "1/4",
    "fifth": "1/5",
    "fifths": "1/5",
    "sixth": "1/6",
    "sixths": "1/6",
    "seventh": "1/7",
    "sevenths": "1/7",
    "eighth": "1/8",
    "eighths": "1/8",
    "ninth": "1/9",
    "ninths": "1/9",
    "tenth": "1/10",
    "tenths": "1/10",
    "twice": "2",
    "double": "2",
    "dozen": "12",
    # Urdu
    "ایک": "1",
    "دو": "2",
    "تین": "3",
    "چار": "4",
    "پانچ": "5",
    "چھ": "6",
    "سات": "7",
    "آٹھ": "8",
    "نو": "9",
    "دس": "10",
    "گیارہ": "11",
    "بارہ": "12",
    "تیرہ": "13",
    "چودہ": "14",
    "پندرہ": "15",
    "سولہ": "16",
    "سترہ": "17",
    "اٹھارہ": "18",
    "انیس": "19",
    "بیس": "20",
    "تیس": "30",
    "چالیس": "40",
    "پچاس": "50",
    "ساٹھ": "60",
    "نوے": "90",
    # (اسی "80" is left out on purpose: it is far more often "this very" — اسی طرح.)
    "سو": "100",
    "ہزار": "1000",
    "آدھا": "1/2",
    "آدھی": "1/2",
    "آدھے": "1/2",
    "چوتھائی": "1/4",
    "تہائی": "1/3",
    "ڈیڑھ": "3/2",
    "ڈھائی": "5/2",
}
_FRACTION_JOINERS = frozenset({"over", "بٹا"})
# Unit-fraction words a count may scale: "three quarters" is 3/4, "دو تہائی" is 2/3.
_FRACTION_WORDS = frozenset(
    w for w, v in _NUMBER_WORDS.items() if v.startswith("1/") and w not in ("آدھا", "آدھی", "آدھے")
)


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


_EN_STOP = _words(
    "a an the and or but if of to in on at by for with from into onto as is are was were be been "
    "this that these those it its it's we you they he she i me my our your their them us his her "
    "do does did can could will would should may might must has have had not no yes so than then "
    "there here what which who whom how why when where all each every some any more most less very "
    "too also just only up down out over about"
)
_UR_STOP = _words(
    "کا کی کے ہے ہیں ہو ہوں تھا تھی تھے میں سے کو اور یہ وہ پر نے تو بھی کیا ہم آپ اس اسے ان جو "
    "یا لیے لئے کہ اگر جب تک ہی نہ نہیں کر کریں کرتے کرو"
)
# Connectives a careful rephrase may add without introducing a fact.
_PEDAGOGY_ALLOW = _words(
    "let let's imagine think look see remember try together like now because means mean called "
    "example again great good well done step first next same say said says show shows "
    "سوچیں دیکھیں یاد آئیے مثال پہلے پھر اب"
)
_LONG_WORD = {"latin": 10, "arabic": 9}
# Comparison / universality / truth words. They are how a recombination of grounded words turns
# into a new (possibly false) claim, so each must already occur in the grounding.
_CLAIM_WORDS = _words(
    "always never bigger biggest smaller smallest larger largest greater greatest fewer more less "
    "most least every all none only must cannot impossible wrong correct incorrect true false "
    "ہمیشہ کبھی بڑا بڑی بڑے چھوٹا چھوٹی چھوٹے زیادہ کم سب صرف غلط صحیح درست"
)

_ARABIC = re.compile("[\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]")
_LATIN = re.compile("[A-Za-z\u00c0-\u024f]")


def _normalize(text: str) -> str:
    return text.translate(_DIGIT_MAP).lower()


def _stem(word: str) -> str:
    if word.endswith("'s"):
        word = word[:-2]
    if len(word) > 3 and word.isascii() and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def numeric_tokens(text: str, *, expand_fractions: bool = False) -> list[str]:
    """Numbers in a text: numerals (with Urdu/Arabic-Indic digits), number words, ``a over b``.

    With ``expand_fractions`` (used for the grounding side) a fraction also contributes its
    numerator and denominator, so grounding "1/4" permits "four parts" — never the other way round.
    """
    norm = _normalize(text)
    tokens: list[str] = []
    for m in _NUMERAL.finditer(norm):
        tok = m.group(0)
        tokens.append(tok)
        if expand_fractions and "/" in tok:
            tokens.extend(tok.split("/"))
    words = _WORD.findall(_NUMERAL.sub(" ", norm))
    values = [_NUMBER_WORDS.get(w) for w in words]
    for i, value in enumerate(values):
        if value is None:
            continue
        tokens.append(value)
        if (
            i + 2 < len(words)
            and words[i + 1] in _FRACTION_JOINERS
            and values[i + 2] is not None
            and "/" not in value
        ):
            tokens.append(f"{value}/{values[i + 2]}")
        if (
            i + 1 < len(words)
            and words[i + 1] in _FRACTION_WORDS
            and "/" not in value
            and value not in ("0", "1")
        ):
            # "three quarters" carries 3/4 as well as 3 and 1/4 (each must be grounded).
            tokens.append(f"{value}/{_NUMBER_WORDS[words[i + 1]].split('/')[1]}")
    return tokens


def content_words(text: str) -> list[str]:
    """Content words (stop-words, number words, and pure connectives removed), lightly stemmed."""
    out: list[str] = []
    for raw in _WORD.findall(_normalize(text)):
        if raw in _EN_STOP or raw in _UR_STOP or raw in _NUMBER_WORDS or raw in _FRACTION_JOINERS:
            continue
        if raw.isascii() and len(raw) < 3:
            continue
        out.append(_stem(raw))
    return out


def _script_ratio(text: str) -> tuple[float, float]:
    arabic = len(_ARABIC.findall(text))
    latin = len(_LATIN.findall(text))
    letters = arabic + latin
    if letters == 0:
        return 0.0, 0.0
    return arabic / letters, latin / letters


def _sentences(text: str) -> list[str]:
    return [s for s in (p.strip() for p in _SENTENCE_SPLIT.split(text)) if s]


def _count_phrase(phrase: str, text: str) -> int:
    pattern = re.compile(r"(?<![\w/])" + re.escape(phrase) + r"(?![\w/])")
    return len(pattern.findall(text))


# ============================================================================ the gate


class GateRule(StrEnum):
    EMPTY = "empty_output"
    UNVERIFIABLE = "unverifiable"
    UNGROUNDED_NUMBER = "ungrounded_number"
    UNGROUNDED_CONTENT = "ungrounded_content"
    UNGROUNDED_CLAIM = "ungrounded_claim"
    FALSE_ARITHMETIC = "false_arithmetic"
    UNVERIFIED_NUMERIC_CLAIM = "unverified_numeric_claim"
    POLARITY_MISMATCH = "polarity_mismatch"
    MISPLACED_NUMBER = "misplaced_number"
    RECOMBINED_CLAUSE = "recombined_clause"
    ANSWER_LEAK = "answer_leak"
    TOO_LONG = "too_long"
    SENTENCE_TOO_LONG = "sentence_too_long"
    TOO_COMPLEX = "too_complex"
    URL = "url"
    CONTACT_INFO = "contact_info"
    PERSONAL_DATA_REQUEST = "personal_data_request"
    DISALLOWED_CONTENT = "disallowed_content"
    WRONG_LOCALE = "wrong_locale"
    UNSUPPORTED_LOCALE = "unsupported_locale"


class Dimension(StrEnum):
    GROUNDING = "grounding"
    ANSWER_LEAK = "answer_leak"
    AGE = "age_appropriateness"
    SAFETY = "safety"
    LOCALE = "locale"


RULE_DIMENSION: dict[GateRule, Dimension] = {
    GateRule.EMPTY: Dimension.GROUNDING,
    GateRule.UNVERIFIABLE: Dimension.GROUNDING,
    GateRule.UNGROUNDED_NUMBER: Dimension.GROUNDING,
    GateRule.UNGROUNDED_CONTENT: Dimension.GROUNDING,
    GateRule.UNGROUNDED_CLAIM: Dimension.GROUNDING,
    GateRule.FALSE_ARITHMETIC: Dimension.GROUNDING,
    GateRule.UNVERIFIED_NUMERIC_CLAIM: Dimension.GROUNDING,
    GateRule.POLARITY_MISMATCH: Dimension.GROUNDING,
    GateRule.MISPLACED_NUMBER: Dimension.GROUNDING,
    GateRule.RECOMBINED_CLAUSE: Dimension.GROUNDING,
    GateRule.ANSWER_LEAK: Dimension.ANSWER_LEAK,
    GateRule.TOO_LONG: Dimension.AGE,
    GateRule.SENTENCE_TOO_LONG: Dimension.AGE,
    GateRule.TOO_COMPLEX: Dimension.AGE,
    GateRule.URL: Dimension.SAFETY,
    GateRule.CONTACT_INFO: Dimension.SAFETY,
    GateRule.PERSONAL_DATA_REQUEST: Dimension.SAFETY,
    GateRule.DISALLOWED_CONTENT: Dimension.SAFETY,
    GateRule.WRONG_LOCALE: Dimension.LOCALE,
    GateRule.UNSUPPORTED_LOCALE: Dimension.LOCALE,
}

MIN_GROUNDING_OVERLAP = 0.6  # share of output content words that must come from the grounding

_URL_PATTERNS = (
    re.compile(r"https?://|\bwww\.|javascript:", re.I),
    re.compile(
        r"\b[\w-]+\.(?:com|org|net|io|pk|edu|gov|info|co|app|dev|ly|me|uk|in|ai|xyz)\b", re.I
    ),
)
_CONTACT_PATTERNS = (
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),  # email
    re.compile(r"(?<![\d/])\+?\d[\d\s().-]{6,}\d(?![\d/])"),  # phone-like digit run
    re.compile(r"(?<![\w@])@[A-Za-z_]\w{1,}"),  # social handle
    re.compile(
        r"\b(?:whatsapp|instagram|facebook|tiktok|snapchat|telegram|discord|youtube|signal)\b",
        re.I,
    ),
    # Red-team (§8): an invitation to private contact needs no address or platform name.
    re.compile(r"\b(?:message|text|dm|call|email|e-mail|contact|ping|add|phone)\s+me\b", re.I),
    re.compile(
        r"\b(?:واٹس\s*ایپ|واٹس\s*اپ|فیس\s*بک|انسٹاگرام|ٹک\s*ٹاک|یوٹیوب|سنیپ\s*چیٹ|ٹیلیگرام|ای\s*میل)\b"
    ),
    re.compile(r"\b(?:رابطہ|میسج|کال)\s+کر\w*|\bمجھے\s+(?:میسج|کال|فون)\b"),
)
_PERSONAL_DATA_PATTERNS = (
    re.compile(
        r"\byour\s+(?:full\s+|real\s+|home\s+)?(?:name|surname|address|phone|mobile|school|"
        r"birthday|email|password|pin|photo|picture|selfie|location|age)\b",
        re.I,
    ),
    re.compile(r"\bphone\s+number\b|\bhow\s+old\s+are\s+you\b|\bwhere\s+do\s+you\s+live\b", re.I),
    re.compile(r"\b(?:send|share|tell|show)\s+(?:me|us)\b", re.I),
    re.compile(r"\bmeet\s+(?:me|up)\b|\bkeep\s+(?:this|it)\s+(?:a\s+)?secret\b", re.I),
    re.compile(r"\b(?:your|you're|you are)\s+(?:mom|mum|dad|parents?)\b", re.I),
    # Urdu patterns are word-bounded: Urdu words embed each other ("جوا" gambling ⊂ "جواب" answer).
    re.compile(
        r"\b(?:آپ\s+کا\s+نام|تمہارا\s+نام|کہاں\s+رہتے|اپنا\s+(?:نمبر|پتہ|فون)|تصویر\s+بھیج|خفیہ|راز)\b"
    ),
    # Red-team (§8): where the child is, who they are, and secrecy/grooming (refused outright).
    re.compile(
        r"\b(?:which|what)\s+(?:school|class|grade|city|town|village|area|street)\b|"
        r"\bdo\s+you\s+live\b|\bwhere\s+(?:is|are)\s+your\b|"
        r"\byour\s+(?:house|city|town|village|street|class|grade|family|father|mother|brother|"
        r"sister|grandparents?|uncle|aunt)\b|"
        r"\b(?:picture|photo|selfie|video)\s+of\s+(?:yourself|you)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:don't|do\s+not|never)\s+tell\b|\bsecrets?\b|\bbetween\s+(?:us|you\s+and\s+me)\b|"
        r"\btrust\s+(?:me|only)\b|\bonly\s+me\b|\b(?:special|best|secret)\s+friends?\b|"
        r"\b(?:delete|erase|hide)\s+(?:this|the|our)\s+(?:chat|messages?|conversation)\b",
        re.I,
    ),
    re.compile(
        r"\b(?:کس|کون\s+سے|کون\s+سی)\s+(?:سکول|اسکول|شہر|جماعت|کلاس|گاؤں)\b|"
        r"(?:آپ\s+کی|تمہاری)\s+عمر\b|\bفون\s+نمبر\b|\bتصویر\s+(?:بھیج|دکھا)\w*|"
        r"\b(?:اپنے|اپنی)\s+(?:امی|ابو|ابا|اماں|والدین|گھر|تصویر)\b|"
        r"(?:آپ\s+کے|آپ\s+کی|تمہارے|تمہاری)\s+(?:والد|والدہ|ابو|امی|بھائی|بہن)\b"
    ),
    re.compile(r"\b(?:مت|نہ)\s+بتا\w*|\bبھروسہ\b|\b(?:خاص|پکا|پکی)\s+(?:دوست|سہیلی)\b"),
)
_DISALLOWED_PATTERNS = (
    # Impersonating a human, or leaking/echoing instructions.
    re.compile(r"\bi\s*(?:am|'m)\s+(?:a\s+)?(?:real\s+)?(?:human|person|man|woman)\b", re.I),
    re.compile(r"\bignore\s+(?:all|any|previous|the\s+above)\b|\bsystem\s+prompt\b", re.I),
    re.compile(r"\bas\s+an\s+ai\b|\blanguage\s+model\b", re.I),
    re.compile(r"\bمیں\s+انسان\s+ہوں\b"),
    # Markup, code, or bracketed tool/stub markers.
    re.compile(r"<\s*/?\s*[a-z][^>]*>|```|\[[^\]]*\]\([^)]*\)|\[stub:", re.I),
    # Vocabulary that has no place in a primary-school maths explanation.
    re.compile(
        r"\b(?:kill|killed|die|dead|death|suicide|weapon|gun|knife|blood|sex|sexy|drugs?|"
        r"alcohol|beer|wine|cigarettes?|vape|gambl\w*|betting|hate|stupid|idiot|dumb|ugly|fat)\b",
        re.I,
    ),
    re.compile(r"\b(?:بیوقوف|احمق|قتل|بندوق|چاقو|شراب|سگریٹ|جوا|خودکشی|موت)\b"),
    # Red-team (§8). Persona: claiming to be a teacher/human/machine, or naming a model vendor.
    re.compile(
        r"\bi\s*(?:am|'m)\s+(?:not\s+)?(?:a\s+|an\s+|your\s+)?(?:real\s+|human\s+|actual\s+)?"
        r"(?:human|person|man|woman|teacher|robot|computer|machine|ai|assistant|chatbot|bot)\b|"
        r"\b(?:claude|anthropic|openai|chatgpt|gpt|gemini|llm)\b",
        re.I,
    ),
    re.compile(
        r"\bمیں\s+(?:\S+\s+){0,3}?(?:استاد|استانی|ٹیچر|انسان|مشین|روبوٹ|کمپیوٹر|ماڈل)"
        r"\s+(?:نہیں\s+)?ہوں\b|\b(?:لینگویج|لسانی)\s+ماڈل\b|\bمصنوعی\s+ذہانت\b"
    ),
    # Injection echo: role markers, passage markers, chat tokens, JSON braces, markdown.
    re.compile(
        r"^\s*(?:system|assistant|user|human|ai)\s*:|\[\d+\]|<\||\|>|[{}]|\*\*|__|^\s{0,3}#{1,6}\s|"
        r"\bhere(?:'s|\s+is|\s+are)\s+(?:the|a|an|your)\s+(?:\w+\s+)?"
        r"(?:rephras\w*|version|text|passages?|rewrite|explanation)\b",
        re.I | re.M,
    ),
    # Self-harm, violence, medicine/dosage, adult themes: never in a rephrase for a child.
    re.compile(
        r"\b(?:hurt|harm|injure|kill)\s+(?:yourself|your\s*self|others?|someone)\b|"
        r"\bself[-\s]?harm\b|\b(?:punch\w*|kick\w*|slap\w*|stab\w*|shoot\w*|fight\w*|hit)\b|"
        r"\b(?:medicines?|medication|pills?|tablets?|dose|dosage|syrup|injection|paracetamol|"
        r"panadol|poison\w*|bleach)\b|"
        r"\b(?:girlfriend|boyfriend|kiss\w*|naked|nude|dating|sexual\w*|porn\w*)\b",
        re.I,
    ),
    re.compile(
        r"\bاپنے\s+آپ\s+کو\s+(?:نقصان|تکلیف|چوٹ|مار)\w*|\b(?:دوائی|دوا|گولی|گولیاں|انجکشن|زہر)\b|"
        r"\b(?:مارو|ماریں|مارنا|پیٹو|لڑو|لڑائی)\b"
    ),
    # Shaming, threats of failure, and guilt ("I'll be sad if you leave").
    re.compile(
        r"\byou(?:'re|\s+are)\s+(?:so\s+|very\s+|really\s+)?(?:slow|lazy|bad|silly|weak)\b|"
        r"\b(?:useless|worthless|hopeless|pathetic|loser|shame\w*|disappoint\w*|fail\w*|baby)\b|"
        r"\bi(?:'ll|\s+will)\s+be\s+(?:so\s+|very\s+)?(?:sad|upset|angry|hurt|lonely)\b|"
        r"\bleave\s+me\b",
        re.I,
    ),
    re.compile(r"\b(?:فیل|ناکام\w*|شرم|سست|نکما|نکمی|نکمے|اداس)\b"),
)
# Red-team (§8): topics and prompt vocabulary with no place in a rephrase UNLESS the authored
# lesson itself uses them (a future civics or Islamiyat lesson may). Refused when ungrounded.
_GROUNDED_ONLY_PATTERNS = (
    re.compile(
        r"\b(?:religions?|religious|god|church|mosque|temple|pray\w*|politic\w*|party|vote\w*|"
        r"elections?|government|minister|president|army|passages?|instructions?|rephras\w*|"
        r"prompts?)\b",
        re.I,
    ),
    re.compile(r"\b(?:مذہب|مذہبی|سیاسی|سیاست|ووٹ|الیکشن|حکومت|ہدایات|نظر\s+انداز)\b"),
)
_ANSWER_PHRASING = (
    re.compile(r"\b(?:the\s+)?(?:correct\s+|right\s+)?answer\s*(?:is|was|=|:)", re.I),
    re.compile(r"\b(?:correct|right)\s+(?:option|choice)\b", re.I),
    re.compile(r"\b(?:choose|pick|select|tick)\s+option\b|\boption\s+[a-d1-9]\b", re.I),
    re.compile(r"جواب\s+ہے|صحیح\s+جواب|درست\s+جواب"),
    # Red-team (§8): pointing at an option by position, and Urdu "the answer ... is".
    re.compile(
        r"\b(?:first|second|third|fourth|last|top|bottom|1st|2nd|3rd)\s+"
        r"(?:option|choice|answer|button)\b|\boption\s+(?:one|two|three|four)\b",
        re.I,
    ),
    re.compile(
        r"\bجواب\s+(?:\S+\s+){0,4}?ہے\b|"
        r"\b(?:پہلا|پہلی|دوسرا|دوسری|تیسرا|تیسری|آخری)\s+(?:آپشن|جواب|انتخاب|والا)\b"
    ),
)
# A statement after a question that carries an item's answer reveals it (red-team, §8).
_SENTENCE_KEEP = re.compile(r"[^.!?۔؟\n]+[.!?۔؟\n]*")


@dataclass(frozen=True)
class AnswerContext:
    """The learner's current item, if any. Only server-trusted hint state may unlock an answer."""

    item_ref: str | None = None
    hints_used: int = 0


@dataclass(frozen=True)
class GateViolation:
    rule: GateRule
    detail: str  # a rule-level description — never the output text itself

    @property
    def dimension(self) -> Dimension:
        return RULE_DIMENSION[self.rule]


@dataclass(frozen=True)
class GateVerdict:
    accepted: bool
    violations: tuple[GateViolation, ...]
    metrics: dict[str, float] = field(default_factory=dict)

    @property
    def rules(self) -> tuple[str, ...]:
        return tuple(sorted({v.rule.value for v in self.violations}))

    @property
    def dimensions(self) -> tuple[str, ...]:
        return tuple(sorted({v.dimension.value for v in self.violations}))


def _answer_text(item: ItemView) -> str:
    if item.kind == FILL:  # a typed answer's canonical text is as secret as a correct option
        return _normalize(item.accepted_answers[0]).strip() if item.accepted_answers else ""
    if item.kind != CHOOSE or not 0 <= item.correct_option < len(item.options):
        return ""
    return _normalize(item.options[item.correct_option]).strip()


def _unlocked_item(lesson: LessonView, ctx: AnswerContext) -> ItemView | None:
    """The current item, if (and only if) its hint ladder is exhausted."""
    if ctx.item_ref is None:
        return None
    for _, pool in _item_pools(lesson):
        for item in pool:
            if item.item_ref == ctx.item_ref:
                return item if ctx.hints_used >= len(item.hints) else None
    return None


def _statements_after_question(output: str) -> str:
    """The non-question sentences that follow a question (where a reveal would sit)."""
    asked, out = False, []
    for sentence in _SENTENCE_KEEP.findall(output):
        if "?" in sentence or "؟" in sentence:
            asked = True
        elif asked:
            out.append(sentence)
    return " ".join(out)


def _check_answer_leak(
    lesson: LessonView, output: str, grounding: str, ctx: AnswerContext
) -> list[GateViolation]:
    found: list[GateViolation] = []
    unlocked = _unlocked_item(lesson, ctx)
    if unlocked is None and any(p.search(output) for p in _ANSWER_PHRASING):
        found.append(GateViolation(GateRule.ANSWER_LEAK, "answer-revealing phrasing"))
    # Once the current item's ladder is exhausted its answer may be shown — including where another
    # item happens to share that same answer text (otherwise no answer could ever be released).
    released = _answer_text(unlocked) if unlocked is not None else None
    out_norm, ground_norm = _normalize(output), _normalize(grounding)
    out_nums = Counter(numeric_tokens(output))
    ground_nums = Counter(numeric_tokens(grounding))
    after_q = _normalize(_statements_after_question(output))
    after_q_nums = set(numeric_tokens(after_q))
    for _, pool in _item_pools(lesson):
        for item in pool:
            answer = _answer_text(item)
            if not answer or answer == released:
                continue
            answer_nums = numeric_tokens(answer)
            if len(answer_nums) == 1 and _NUMERAL.fullmatch(answer):
                leaked = out_nums[answer_nums[0]] > ground_nums[answer_nums[0]]
            else:
                leaked = _count_phrase(answer, out_norm) > _count_phrase(answer, ground_norm)
            if len(answer_nums) == 1 and _NUMERAL.fullmatch(answer):
                leaked = leaked or answer_nums[0] in after_q_nums
            else:
                leaked = leaked or _count_phrase(answer, after_q) > 0
            if leaked:
                found.append(
                    GateViolation(
                        GateRule.ANSWER_LEAK, f"correct option of {item.item_ref} surfaced"
                    )
                )
    return found


# Red-team (§8): within a script that matches, words of another language. Refused unless the
# grounding uses them (Urdu worked steps are grounded on the English step too).
_FOREIGN_LETTERS: dict[str, tuple[re.Pattern[str], ...]] = {
    "ur": (re.compile(r"[A-Za-z]{2,}"), re.compile("[\u0643\u064a\u0629\u0649]")),
    "en": (re.compile("[\u00c0-\u024f]"),),
}
# A letter of any script other than Latin and Arabic (e.g. Devanagari) is foreign in every locale;
# the script-ratio check above counts only Latin and Arabic letters, so it cannot see them.
_OTHER_SCRIPT = re.compile(
    r"[^\W\d_A-Za-z\u00c0-\u024f\u0600-\u06ff\u0750-\u077f\ufb50-\ufdff\ufe70-\ufeff]"
)


def _ungrounded_match(patterns: tuple[re.Pattern[str], ...], text: str, grounding: str) -> bool:
    """True if a pattern matches text that the grounding itself never uses."""
    ground_norm = _normalize(grounding)

    def grounded(hit: str) -> bool:
        return hit in ground_norm if len(hit) == 1 else _count_phrase(hit, ground_norm) > 0

    return any(not grounded(m.group(0).lower()) for p in patterns for m in p.finditer(text))


# ============================================================================ semantic consistency
#
# The rules above are lexical, so a misstatement built only from grounded words passes them. The
# checks below compare the structure that carries meaning with the passages being rephrased:
# arithmetic and comparisons between numbers (exact, with ``Fraction``), negation and comparison
# direction, which numbers sit in which sentence, and which passage sentence a clause's words come
# from. They are deterministic and provider-independent, and every doubt is a refusal.

# Sentence split that keeps decimals ("0.5") whole.
_CLAIM_SPLIT = re.compile(r"(?:(?<!\d)\.|\.(?!\d)|[!?۔؟\n])+")
_CLAIM_TOKEN = re.compile(
    r"\d+(?:[.,/]\d+)*|[^\W\d_]+(?:'[^\W\d_]+)?|[=+×÷*≠≥≤<>−,،]|(?<=\s)[-/](?=\s)|(?<=\d)-(?=\d)"
)
_CONJUNCTIONS = _words("and so but then because while or اور تو لیکن پھر کیونکہ یا")
_CLAUSE_SPLIT = re.compile(r"[;:]|\b(?:" + "|".join(sorted(_CONJUNCTIONS)) + r")\b")

_COPULAS = _words("is are was were")
_NEG_COPULAS = _words("isn't aren't wasn't weren't")
_NEGATORS = _words("not never no cannot nor neither none nothing nobody نہیں نہ مت")
# Comparison direction (+1 "greater", -1 "smaller"): the polarity rule uses all of these; the
# arithmetic rule evaluates the comparatives among them ("bigger than", "سے بڑا").
_MORE_WORDS = _words(
    "bigger biggest larger largest greater greatest more most higher highest taller tallest longer "
    "longest heavier heaviest بڑا بڑی بڑے زیادہ"
)
_LESS_WORDS = _words(
    "smaller smallest less least fewer fewest lower lowest shorter shortest lighter lightest "
    "چھوٹا چھوٹی چھوٹے کم"
)
_COMPARATIVES = _words(
    "bigger larger greater more higher taller longer heavier smaller less fewer lower shorter "
    "lighter بڑا بڑی بڑے زیادہ چھوٹا چھوٹی چھوٹے کم"
)
# Words that express a relation rather than a topic. They never decide which passage a sentence
# rephrases — otherwise swapping "bigger" for "smaller" would also change the alignment.
_RELATION_WORDS = (
    _MORE_WORDS
    | _LESS_WORDS
    | _NEGATORS
    | _words("equal same plus minus time multiplied divided than برابر جمع منفی ضرب تقسیم")
)
_OP_SYMBOLS = {"+": "+", "-": "-", "−": "-", "×": "*", "*": "*", "÷": "/", "/": "/"}
_OP_WORDS = {
    "plus": "+",
    "minus": "-",
    "times": "*",
    "x": "*",
    "جمع": "+",
    "منفی": "-",
    "ضرب": "*",
    "تقسیم": "/",
}
_EQ_WORDS = _words("= equals makes make gives give")
_MULTIPLIER_WORDS = {
    "hundred": 100,
    "thousand": 1000,
    "million": 1_000_000,
    "سو": 100,
    "ہزار": 1000,
}
_INTENSIFIERS = _words("much a lot little bit even far way still")
_ARTICLES = _words("a an the")
_UR_POSSESSIVES = _words("کا کی کے")
_UR_COPULAS = _words("ہے ہیں تھا تھی تھے")
# A word that can glue a number to its neighbour ("1 of 4", "one over four", "چار میں سے تین").
_JOINER_WORDS = _words("of and out by over بٹا میں")


def _numeral_value(token: str) -> Fraction | None:
    """Exact value of a numeral, or None if it cannot be read unambiguously ("1,5", "1/0")."""
    if re.fullmatch(r"\d+", token):
        return Fraction(int(token))
    if re.fullmatch(r"\d+/\d+", token):
        num, den = token.split("/")
        return Fraction(int(num), int(den)) if int(den) else None
    if re.fullmatch(r"\d+\.\d+", token):
        return Fraction(token)
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+", token):
        return Fraction(int(token.replace(",", "")))
    return None


@dataclass(frozen=True)
class _Tok:
    """One unit of a sentence for claim parsing: a number, an operator, a relation word, ..."""

    kind: str  # num | op | eq | eqpost | cop | cmp | than | neg | se | twice | comma | word
    raw: tuple[str, ...]  # the normalized source tokens (verbatim matching uses these)
    value: Fraction | None = None  # num (None: a numeral that cannot be read exactly)
    op: str = ""  # op: + - * /
    sign: int = 0  # cmp: +1 greater, -1 smaller, 0 a relation the checker does not evaluate
    neg: bool = False  # eq / cop: negated ("is not", "isn't")
    spelled: bool = False  # num: written as a word ("twenty", "چار")
    unit: bool = False  # num: a unit-fraction word a count may scale ("quarter")
    implicit_than: bool = False  # cmp: a symbol (">", "<") that needs no "than"

    @property
    def head(self) -> str:
        return self.raw[0] if self.raw else ""


_NOTHING = _Tok("word", ())


def _int_value(tok: _Tok) -> Fraction | None:
    """The token's value if it is a whole number, else None."""
    if tok.kind == "num" and tok.value is not None and tok.value.denominator == 1:
        return tok.value
    return None


def _base_tokens(sentence: str) -> list[_Tok]:
    raw = _CLAIM_TOKEN.findall(_normalize(sentence).replace("’", "'"))
    toks: list[_Tok] = []
    i = 0
    while i < len(raw):
        r = raw[i]
        nxt = raw[i + 1] if i + 1 < len(raw) else ""
        step = 1
        if r[0].isdigit():
            toks.append(_Tok("num", (r,), value=_numeral_value(r)))
        elif r in ("twice", "double"):
            toks.append(_Tok("twice", (r,)))
        elif r in _NUMBER_WORDS:
            value = Fraction(_NUMBER_WORDS[r])
            toks.append(_Tok("num", (r,), value=value, spelled=True, unit=r in _FRACTION_WORDS))
        elif r in _OP_SYMBOLS:
            toks.append(_Tok("op", (r,), op=_OP_SYMBOLS[r]))
        elif r in _OP_WORDS:
            toks.append(_Tok("op", (r,), op=_OP_WORDS[r]))
        elif r in ("multiplied", "divided") and nxt == "by":
            toks.append(_Tok("op", (r, nxt), op="*" if r == "multiplied" else "/"))
            step = 2
        elif r in (">", "<", "≥", "≤"):
            sign = {">": 1, "<": -1}.get(r, 0)
            toks.append(_Tok("cmp", (r,), sign=sign, implicit_than=True))
        elif r == "≠":
            toks.append(_Tok("eq", (r,), neg=True))
        elif r in _EQ_WORDS:
            toks.append(_Tok("eq", (r,)))
        elif r == "equal" and nxt == "to":
            toks.append(_Tok("eq", (r, nxt)))
            step = 2
        elif r in _COPULAS or r in _NEG_COPULAS:
            neg = r in _NEG_COPULAS
            j = i + 1
            if j < len(raw) and raw[j] == "not":
                neg, j = True, j + 1
            if raw[j : j + 2] == ["equal", "to"]:
                toks.append(_Tok("eq", tuple(raw[i : j + 2]), neg=neg))
                j += 2
            elif raw[j : j + 3] == ["the", "same", "as"]:
                toks.append(_Tok("eq", tuple(raw[i : j + 3]), neg=neg))
                j += 3
            else:
                toks.append(_Tok("cop", tuple(raw[i:j]), neg=neg))
            step = j - i
        elif r in _COMPARATIVES:
            toks.append(_Tok("cmp", (r,), sign=1 if r in _MORE_WORDS else -1))
        elif r == "than":
            toks.append(_Tok("than", (r,)))
        elif r in _NEGATORS or r.endswith("n't"):
            toks.append(_Tok("neg", (r,)))
        elif r in (",", "،"):
            toks.append(_Tok("comma", (r,)))  # a comma keeps "2, and half of 8" apart
        elif r == "سے":
            toks.append(_Tok("se", (r,)))
        elif r == "برابر":
            after_possessive = bool(toks) and toks[-1].head in _UR_POSSESSIVES
            toks.append(_Tok("eqpost" if after_possessive else "eq", (r,)))
        else:
            toks.append(_Tok("word", (r,)))
        i += step
    return toks


def _merged(parts: list[_Tok], value: Fraction | None) -> _Tok:
    return _Tok("num", tuple(r for p in parts for r in p.raw), value=value)


def _ratio(num: Fraction, den: Fraction) -> Fraction | None:
    return num / den if den else None


def _combine_numbers(toks: list[_Tok]) -> list[_Tok]:
    """Read multi-token quantities as one number: "twenty five", "one over four", "3 out of 4",
    "three quarters", "چار میں سے تین" (3/4), "one and a half", "ساڑھے تین", "twice 3"; and a
    fraction "of" a number ("half of 8", "آٹھ کا آدھا") as a product."""
    out: list[_Tok] = []
    i, n = 0, len(toks)

    def at(j: int) -> _Tok:
        return toks[j] if j < n else _NOTHING

    while i < n:
        t = toks[i]
        if t.kind == "twice":
            skip = 1 if at(i + 1).raw == ("of",) and at(i + 2).kind == "num" else 0
            if at(i + 1 + skip).kind == "num":
                out += [_merged([t, *toks[i + 1 : i + 1 + skip]], Fraction(2))]
                out.append(_Tok("op", (), op="*"))
                i += 1 + skip
                continue
            t = _Tok("num", t.raw, value=Fraction(2), spelled=True)
        if t.head == "ساڑھے" and (v := _int_value(at(i + 1))) is not None:
            t, i = _merged([t, at(i + 1)], v + Fraction(1, 2)), i + 1
        a = _int_value(t)
        if a is None:
            out.append(t)
            i += 1
            continue
        b = _int_value(at(i + 1))
        if t.spelled and b is not None and at(i + 1).spelled:
            if a in range(20, 100, 10) and 1 <= b <= 9:  # "twenty five", "twenty-five"
                t, i = _merged([t, at(i + 1)], a + b), i + 1
            elif at(i + 1).head in _MULTIPLIER_WORDS:  # "three hundred"
                t, i = _merged([t, at(i + 1)], a * _MULTIPLIER_WORDS[at(i + 1).head]), i + 1
        a = _int_value(t) or Fraction(0)
        nxt = at(i + 1)
        if nxt.head in ("over", "بٹا") and (d := _int_value(at(i + 2))) is not None:
            t, i = _merged(toks[i : i + 3], _ratio(a, d)), i + 2  # "one over four"
        elif (
            nxt.raw == ("out",)
            and at(i + 2).raw == ("of",)
            and (d := _int_value(at(i + 3))) is not None
        ):
            t, i = _merged(toks[i : i + 4], _ratio(a, d)), i + 3  # "3 out of 4"
        elif (
            nxt.raw == ("میں",)
            and at(i + 2).kind == "se"
            and (m := _int_value(at(i + 3))) is not None
        ):
            t, i = _merged(toks[i : i + 4], _ratio(m, a)), i + 3  # "چار میں سے تین" = 3/4
        elif nxt.kind == "num" and nxt.unit and not t.unit and nxt.value is not None:
            t, i = _merged([t, nxt], a * nxt.value), i + 1  # "three quarters", "دو تہائی"
        elif nxt.raw == ("and",):  # "one and a half"
            j = i + 3 if at(i + 2).head in ("a", "an") else n
            frac = at(j)
            if frac.kind == "num" and frac.unit and frac.value is not None:
                t, i = _merged(toks[i : j + 1], a + frac.value), j
        out.append(t)
        i += 1
    for k in range(1, len(out) - 1):
        left, mid, right = out[k - 1], out[k], out[k + 1]
        if left.kind != "num" or right.kind != "num" or mid.kind != "word":
            continue
        if mid.raw == ("of",) and left.value is not None and left.value.denominator != 1:
            out[k] = _Tok("op", mid.raw, op="*")  # "half of 8", "1/4 of 12"
        elif (
            mid.head in _UR_POSSESSIVES and right.value is not None and right.value.denominator != 1
        ):
            out[k] = _Tok("op", mid.raw, op="*")  # "آٹھ کا آدھا" (half of eight)
    return out


def _expr_end(toks: list[_Tok], start: int) -> int:
    end = start
    while end + 2 < len(toks) and toks[end + 1].kind == "op" and toks[end + 2].kind == "num":
        end += 2
    return end


def _expr_start(toks: list[_Tok], end: int) -> int:
    start = end
    while start >= 2 and toks[start - 1].kind == "op" and toks[start - 2].kind == "num":
        start -= 2
    return start


def _evaluate(expr: list[_Tok]) -> Fraction | None:
    """Exact value of ``num (op num)*`` with the usual precedence; None if it cannot be computed."""
    values = [t.value for t in expr[::2]]
    ops = [t.op for t in expr[1::2]]
    first = values[0]
    if first is None:
        return None
    terms: list[Fraction] = [first]
    signs: list[str] = []
    for op, v in zip(ops, values[1:], strict=True):
        if v is None:
            return None
        if op == "*":
            terms[-1] *= v
        elif op == "/":
            if v == 0:
                return None
            terms[-1] /= v
        else:
            signs.append(op)
            terms.append(v)
    total = terms[0]
    for op, v in zip(signs, terms[1:], strict=True):
        total = total + v if op == "+" else total - v
    return total


def _relation(left: Fraction | None, right: Fraction | None, sign: int | None) -> bool | None:
    """sign None: equality; +1: left > right; -1: left < right; 0: not evaluated."""
    if left is None or right is None or sign == 0:
        return None
    if sign is None:
        return left == right
    return left > right if sign > 0 else left < right


def _dangling(toks: list[_Tok], index: int, step: int, lo: int, hi: int) -> bool:
    """True if the number at ``index`` may continue (towards ``step``) into a quantity the parser
    did not read — e.g. "one and a quarter", "2 of 4": the claim is then unverifiable."""
    j = index + step
    if not lo <= j < hi:
        return False
    if toks[j].kind in ("num", "op", "twice"):
        return True
    return toks[j].head in _JOINER_WORDS and lo <= j + step < hi and toks[j + step].kind == "num"


@dataclass(frozen=True)
class NumericClaim:
    """A statement relating numbers ("2 + 3 = 5", "3/4 is bigger than 2/3", "۳/۴ ... سے بڑا")."""

    tokens: tuple[str, ...]  # the claim's normalized source tokens
    holds: bool | None  # True: exactly true; False: false; None: a relation that cannot be read

    @property
    def text(self) -> str:
        return " ".join(self.tokens)


class _ClaimFinder:
    """Finds the numeric claims in one sentence (see ``numeric_claims``)."""

    def __init__(self, toks: list[_Tok]) -> None:
        self.toks = toks
        self.found: dict[tuple[int, int], bool | None] = {}
        # A claim never reaches across a conjunction ("and", "so", "اور"...).
        self.clause: list[tuple[int, int]] = []
        lo = 0
        for k, t in enumerate(toks):
            if t.kind == "word" and t.head in _CONJUNCTIONS:
                self.clause.extend([(lo, k)] * (k - lo) + [(k, k)])
                lo = k + 1
        self.clause.extend([(lo, len(toks))] * (len(toks) - lo))

    def nums(self, lo: int, hi: int) -> list[int]:
        return [m for m in range(lo, hi) if self.toks[m].kind == "num"]

    def judge(
        self, a: tuple[int, int], b: tuple[int, int], end: int, sign: int | None, neg: bool
    ) -> None:
        left = _evaluate(self.toks[a[0] : a[1] + 1])
        right = _evaluate(self.toks[b[0] : b[1] + 1])
        holds = _relation(left, right, sign)
        self.found[(a[0], end)] = None if holds is None else holds != neg

    def unverified(self, start: int, end: int) -> None:
        self.found[(start, end)] = None

    def run(self) -> list[NumericClaim]:
        for k, t in enumerate(self.toks):
            lo, hi = self.clause[k]
            if t.kind in ("eq", "cop") and lo < k < hi - 1:
                self.equation(k, lo, hi)
            elif t.kind == "cmp" and (t.implicit_than or t.head.isascii()):
                self.english_comparison(k, lo, hi)
            elif t.kind == "se" and k + 1 < hi and self.toks[k + 1].kind == "cmp":
                self.urdu_comparison(k, lo, hi)
            elif t.kind == "eqpost" or (t.head in _UR_COPULAS and k > lo):
                self.urdu_equation(k, lo, hi)
        return [
            NumericClaim(tuple(r for tok in self.toks[s : e + 1] for r in tok.raw), holds)
            for (s, e), holds in sorted(self.found.items())
        ]

    def equation(self, k: int, lo: int, hi: int) -> None:
        """Equations and equalities: "2 + 3 = 5", "half of 8 is 4", "1/2 is the same as 2/4"."""
        toks = self.toks
        j = k + 1 + (toks[k + 1].head in ("a", "an"))
        if toks[k - 1].kind != "num" or j >= hi or toks[j].kind != "num":
            return
        a = (_expr_start(toks, k - 1), k - 1)
        b = (j, _expr_end(toks, j))
        if _dangling(toks, a[0], -1, lo, hi) or _dangling(toks, b[1], 1, lo, hi):
            self.unverified(a[0], b[1])
        else:
            self.judge(a, b, b[1], None, toks[k].neg)

    def english_comparison(self, k: int, lo: int, hi: int) -> None:
        """English comparisons: "3/4 is bigger than 2/3", "1/4 of a cake is not more than 1/2 of a
        cake", "3 > 2"."""
        toks = self.toks
        left = self.nums(lo, k)
        if toks[k].implicit_than:
            j = k + 1
        elif k + 1 < hi and toks[k + 1].kind == "than":
            j = k + 2
        else:
            than = next((m for m in range(k + 1, hi) if toks[m].kind == "than"), None)
            if than is not None and left and self.nums(than, hi):
                self.unverified(left[0], hi - 1)  # e.g. "1/4 has a bigger bottom number than 1/2"
            return
        while j < hi and toks[j].head in _ARTICLES and toks[j].kind == "word":
            j += 1
        if not left:
            return  # one-sided ("this is bigger than 1/4"): there are no two numbers to relate
        if j >= hi or toks[j].kind != "num":
            if self.nums(k, hi):
                self.unverified(left[0], hi - 1)
            return
        i, neg = k - 1, False
        while i >= lo and (
            toks[i].kind in ("neg", "cop")
            or (toks[i].kind == "word" and toks[i].head in _INTENSIFIERS)
        ):
            neg ^= toks[i].kind == "neg" or toks[i].neg
            i -= 1
        a = (_expr_start(toks, left[-1]), left[-1])
        b = (j, _expr_end(toks, j))
        # Words between the left number and the comparison ("of the cake") must recur after the
        # right number, so both sides measure the same thing; otherwise the claim is unreadable.
        filler = toks[a[1] + 1 : i + 1]
        after = toks[b[1] + 1 : b[1] + 1 + len(filler)]
        same = all(f.kind == "word" for f in filler) and [
            tuple(map(_stem, f.raw)) for f in filler
        ] == [tuple(map(_stem, f.raw)) for f in after]
        end = b[1] + len(filler)
        if not same or _dangling(toks, a[0], -1, lo, hi) or _dangling(toks, end, 1, lo, hi):
            self.unverified(a[0], min(max(end, b[1]), hi - 1))
        else:
            self.judge(a, b, end, toks[k].sign, neg)

    def left_operand(self, b_start: int, lo: int) -> int | None:
        """Urdu puts both operands first ("A، B سے بڑا"): the end of A, just before B."""
        p = b_start - 1
        if p >= lo and self.toks[p].kind == "comma":
            p -= 1
        return p if p >= lo and self.toks[p].kind == "num" else None

    def urdu_comparison(self, k: int, lo: int, hi: int) -> None:
        """Urdu comparisons: "۳/۴، ۲/۳ سے بڑا ہے" (3/4 is bigger than 2/3), negated with نہیں."""
        toks = self.toks
        c = k + 1
        while c + 1 < hi and toks[c + 1].kind == "cmp":
            c += 1  # "سے زیادہ بڑا": the last comparative carries the direction
        neg = any(toks[m].kind == "neg" for m in range(c + 1, hi))
        before = self.nums(lo, k)
        if not before:
            return
        if toks[k - 1].kind != "num":
            self.unverified(before[0], c)
            return
        b = (_expr_start(toks, k - 1), k - 1)
        a_end = self.left_operand(b[0], lo)
        if a_end is None:
            if self.nums(lo, b[0]):
                self.unverified(before[0], c)
            return  # one-sided ("یہ ایک بٹا چار سے بڑا ہے")
        a = (_expr_start(toks, a_end), a_end)
        if _dangling(toks, a[0], -1, lo, hi):
            self.unverified(a[0], c)
        else:
            self.judge(a, b, c, toks[c].sign, neg)

    def urdu_equation(self, k: int, lo: int, hi: int) -> None:
        """Urdu equalities: "ایک بٹا دو، دو بٹا چار کے برابر ہے"; "دو جمع تین پانچ ہے"."""
        toks = self.toks
        post = toks[k].kind == "eqpost"
        j, neg = (k - 2, False) if post else (k - 1, False)
        if post:
            neg = any(toks[m].kind == "neg" for m in range(k + 1, hi))
        elif j >= lo and toks[j].kind == "neg":
            neg, j = True, j - 1
        if j < lo or toks[j].kind != "num":
            if post and self.nums(lo, k):
                self.unverified(self.nums(lo, k)[0], k)
            return
        b = (_expr_start(toks, j), j)
        a_end = self.left_operand(b[0], lo)
        if a_end is None:
            if post and self.nums(lo, b[0]):
                self.unverified(self.nums(lo, b[0])[0], k)
            return  # "یہ ایک بٹا چار ہے": a number is named, nothing is related to it
        a = (_expr_start(toks, a_end), a_end)
        if _dangling(toks, a[0], -1, lo, hi):
            self.unverified(a[0], k)
        else:
            self.judge(a, b, k, None, neg)


def _claim_sentences(text: str) -> list[str]:
    return [s for s in (p.strip() for p in _CLAIM_SPLIT.split(text)) if s]


def numeric_claims(text: str) -> list[NumericClaim]:
    """Every statement in ``text`` that relates numbers, judged by exact arithmetic.

    Covers equations ("2 + 3 = 5", "half of 8 is 4", "دو جمع تین پانچ ہے"), equalities ("1/2 is
    the same as 2/4", "... کے برابر ہے") and comparisons ("3/4 is bigger than 2/3", "۳/۴، ۲/۳ سے
    بڑا ہے"), with negation. A relation the parser cannot read exactly has ``holds=None``.
    """
    claims: list[NumericClaim] = []
    for sentence in _claim_sentences(text):
        claims.extend(_claims_and_residue(sentence)[0])
    return claims


def _claims_and_residue(sentence: str) -> tuple[list[NumericClaim], str]:
    """The sentence's numeric claims, and its text with every *proven-true* claim removed.

    A comparison proven by exact arithmetic needs no polarity check ("1/2 is bigger than 1/4"
    may restate "1/4 is smaller than 1/2"); everything else in the sentence still gets one.
    """
    toks = _combine_numbers(_base_tokens(sentence))
    finder = _ClaimFinder(toks)
    claims = finder.run()
    proven = [span for span, holds in finder.found.items() if holds]
    residue = " ".join(
        r
        for k, tok in enumerate(toks)
        if not any(lo <= k <= hi for lo, hi in proven)
        for r in tok.raw
    )
    return claims, residue


def polarity(text: str) -> tuple[int, tuple[int, ...]]:
    """(number of negations, comparison directions in order) — e.g. "not bigger" → (1, (1,))."""
    words = _WORD.findall(_normalize(text).replace("’", "'"))
    negations = sum(1 for w in words if w in _NEGATORS or w.endswith("n't"))
    directions = tuple(
        1 if w in _MORE_WORDS else -1 for w in words if w in _MORE_WORDS or w in _LESS_WORDS
    )
    return negations, directions


def _key_words(text: str) -> frozenset[str]:
    return frozenset(w for w in content_words(text) if w not in _RELATION_WORDS)


@dataclass(frozen=True)
class _GroundSentence:
    words: frozenset[str]
    numbers: frozenset[str]  # fractions expanded, as for the grounding-wide number check
    polarity: tuple[int, tuple[int, ...]]


def _ground_sentences(passages: tuple[str, ...]) -> list[_GroundSentence]:
    seen: set[str] = set()
    out: list[_GroundSentence] = []
    for passage in passages:
        for sentence in _claim_sentences(passage):
            norm = " ".join(_normalize(sentence).split())
            if norm in seen:
                continue
            seen.add(norm)
            out.append(
                _GroundSentence(
                    _key_words(sentence),
                    frozenset(numeric_tokens(sentence, expand_fractions=True)),
                    polarity(_claims_and_residue(sentence)[1]),
                )
            )
    return out


def _aligned(
    key: frozenset[str], numbers: frozenset[str], ground: list[_GroundSentence]
) -> list[_GroundSentence]:
    """The grounding sentences an output sentence plausibly rephrases: they share at least two of
    its topic words (all of them if it has fewer), or — with no topic words — its numbers."""
    if key:
        need = min(2, len(key))
        return [g for g in ground if len(key & g.words) >= need]
    if numbers:
        need = min(2, len(numbers))
        return [g for g in ground if len(numbers & g.numbers) >= need]
    return []


def _contains_verbatim(claim: NumericClaim, grounding_claim_tokens: list[tuple[str, ...]]) -> bool:
    needle = "\x1f" + "\x1f".join(claim.tokens) + "\x1f"
    return any(needle in "\x1f" + "\x1f".join(g) + "\x1f" for g in grounding_claim_tokens)


def _check_consistency(passages: tuple[str, ...], output: str) -> list[GateViolation]:
    found: list[GateViolation] = []
    ground = _ground_sentences(passages)
    vocab = frozenset(w for g in ground for w in g.words)
    where: Counter[str] = Counter(w for g in ground for w in g.words)
    home = {w: i for i, g in enumerate(ground) for w in g.words if where[w] == 1}

    # 1. Arithmetic and comparisons between numbers: exactly true, or authored verbatim.
    grounding_tokens = [
        tuple(r for tok in _base_tokens(s) for r in tok.raw)
        for p in passages
        for s in _claim_sentences(p)
    ]
    false_claims = unread_claims = 0
    for claim in numeric_claims(output):
        if claim.holds or _contains_verbatim(claim, grounding_tokens):
            continue
        if claim.holds is None:
            unread_claims += 1
        else:
            false_claims += 1
    if false_claims:
        found.append(
            GateViolation(GateRule.FALSE_ARITHMETIC, f"{false_claims} false numeric claim(s)")
        )
    if unread_claims:
        found.append(
            GateViolation(
                GateRule.UNVERIFIED_NUMERIC_CLAIM,
                f"{unread_claims} numeric claim(s) not verifiable",
            )
        )

    flipped = recombined = misplaced = 0
    for sentence in _claim_sentences(output):
        # 2. Polarity: negations and comparison directions match a passage sentence it rephrases
        #    (or two, merged into one sentence, in either order).
        sig = polarity(_claims_and_residue(sentence)[1])
        aligned = _aligned(
            _key_words(sentence) & vocab, frozenset(numeric_tokens(sentence)), ground
        )
        if aligned:
            sigs = {g.polarity for g in aligned}
            sigs |= {
                (a.polarity[0] + b.polarity[0], a.polarity[1] + b.polarity[1])
                for a in aligned
                for b in aligned
                if a is not b
            }
            flipped += sig not in sigs
        elif sig != (0, ()):
            flipped += 1  # a negation or comparison with no passage to check it against
        for clause in _CLAUSE_SPLIT.split(sentence):
            # 3. Recombination: words that only one passage sentence uses tie a clause to that
            #    sentence. A clause tied to several may join whole sentences (a title run into the
            #    next line) but may not splice parts of two: "the top number shows the total".
            key = _key_words(clause) & vocab
            homes = {home[w] for w in key if w in home}
            partial = [h for h in homes if not ground[h].words <= key]
            if len(homes) > 1 and len(partial) > 1:
                recombined += 1
                continue
            # 4. Number provenance per clause: its numbers belong to the sentence it rephrases.
            numbers = set(numeric_tokens(clause))
            if not numbers or not key:
                continue
            if homes:
                sources = [ground[h] for h in homes]
            else:
                sources = _aligned(key, frozenset(), ground) or [g for g in ground if key & g.words]
            allowed = {n for g in sources for n in g.numbers}
            misplaced += bool(numbers - allowed)
    if flipped:
        found.append(
            GateViolation(
                GateRule.POLARITY_MISMATCH,
                f"{flipped} sentence(s) differ in negation or comparison direction",
            )
        )
    if recombined:
        found.append(
            GateViolation(
                GateRule.RECOMBINED_CLAUSE, f"{recombined} clause(s) recombine separate passages"
            )
        )
    if misplaced:
        found.append(
            GateViolation(
                GateRule.MISPLACED_NUMBER,
                f"{misplaced} clause(s) with a number from another passage",
            )
        )
    return found


_SENTENCE_PIECES = re.compile(r"[^.!?۔؟\n]+[.!?۔؟]*")


def _sentence_key(sentence: str) -> str:
    return " ".join(_normalize(sentence).split()).strip(" .!?۔؟")


def _unauthored_sentences(norm_output: str, passages: tuple[str, ...]) -> str:
    """The output's sentences that are not an exact copy of a passage sentence, joined."""
    authored = {
        _sentence_key(m.group(0)) for text in passages for m in _SENTENCE_PIECES.finditer(text)
    }
    return " ".join(
        m.group(0)
        for m in _SENTENCE_PIECES.finditer(norm_output)
        if _sentence_key(m.group(0)) not in authored
    )


def unverifiable(detail: str) -> GateVerdict:
    """The verdict when grounding cannot be checked at all: refuse (serve the authored text)."""
    return GateVerdict(accepted=False, violations=(GateViolation(GateRule.UNVERIFIABLE, detail),))


def gate(
    lesson: LessonView,
    prompt: GroundedPrompt,
    output: str,
    *,
    answer_context: AnswerContext | None = None,
) -> GateVerdict:
    """Check one model output against its grounding. Accepted only with zero violations."""
    ctx = answer_context or AnswerContext()
    if not prompt.passages:
        # Nothing to check the output against: it cannot be verified, so it is never shown.
        return unverifiable("no grounding passages")
    violations: list[GateViolation] = []
    grounding = " ".join(prompt.texts)
    text = output.strip()
    band = age_band(prompt.grade_band)
    metrics: dict[str, float] = {"output_chars": float(len(text))}

    # -- grounding -------------------------------------------------------------------------
    words = content_words(text)
    if not text or not _WORD.search(text):
        violations.append(GateViolation(GateRule.EMPTY, "no text"))
    allowed_numbers = set(numeric_tokens(grounding, expand_fractions=True))
    novel_numbers = sorted({n for n in numeric_tokens(text) if n not in allowed_numbers})
    if novel_numbers:
        violations.append(
            GateViolation(
                GateRule.UNGROUNDED_NUMBER, f"{len(novel_numbers)} number(s) not in grounding"
            )
        )
    vocab = set(content_words(grounding)) | _PEDAGOGY_ALLOW
    overlap = (sum(w in vocab for w in words) / len(words)) if words else 1.0
    metrics["grounding_overlap"] = round(overlap, 3)
    if words and overlap < MIN_GROUNDING_OVERLAP:
        violations.append(
            GateViolation(
                GateRule.UNGROUNDED_CONTENT, f"overlap {overlap:.2f} < {MIN_GROUNDING_OVERLAP}"
            )
        )
    grounding_words = set(_WORD.findall(_normalize(grounding)))
    claims = {w for w in _WORD.findall(_normalize(text)) if w in _CLAIM_WORDS} - grounding_words
    if claims:
        violations.append(
            GateViolation(
                GateRule.UNGROUNDED_CLAIM, f"{len(claims)} claim word(s) not in grounding"
            )
        )
    # Semantic consistency: arithmetic, polarity, recombination, per-sentence number provenance.
    if text:
        violations.extend(_check_consistency(prompt.texts, text))

    # -- answer leak -----------------------------------------------------------------------
    violations.extend(_check_answer_leak(lesson, text, grounding, ctx))

    # -- age band --------------------------------------------------------------------------
    total_words = len(_WORD.findall(text))
    longest = max((len(_WORD.findall(s)) for s in _sentences(text)), default=0)
    metrics["words"] = float(total_words)
    metrics["max_sentence_words"] = float(longest)
    if total_words > band.max_words:
        violations.append(
            GateViolation(GateRule.TOO_LONG, f"{total_words} > {band.max_words} words")
        )
    if longest > band.max_sentence_words:
        violations.append(
            GateViolation(
                GateRule.SENTENCE_TOO_LONG, f"sentence {longest} > {band.max_sentence_words} words"
            )
        )
    novel_long = {
        w
        for w in words
        if w not in vocab and len(w) >= _LONG_WORD["latin" if w.isascii() else "arabic"]
    }
    if len(novel_long) > band.max_novel_long_words:
        violations.append(
            GateViolation(GateRule.TOO_COMPLEX, f"{len(novel_long)} novel long word(s)")
        )

    # -- safety ----------------------------------------------------------------------------
    norm = text.translate(_DIGIT_MAP)
    if any(p.search(norm) for p in _URL_PATTERNS):
        violations.append(GateViolation(GateRule.URL, "link or domain"))
    if any(p.search(norm) for p in _CONTACT_PATTERNS):
        violations.append(GateViolation(GateRule.CONTACT_INFO, "contact detail or handle"))
    # The harm-word lists below would also refuse the curriculum's own safety teaching ("Some
    # secrets are good…", "Never write your address…"). A sentence the output repeats exactly from
    # a passage is the authored text itself, so only the other sentences are checked. A reworded
    # sentence gets no exemption: it is refused and the child sees the authored text.
    unauthored = _unauthored_sentences(norm, prompt.texts)
    if any(p.search(unauthored) for p in _PERSONAL_DATA_PATTERNS):
        violations.append(GateViolation(GateRule.PERSONAL_DATA_REQUEST, "asks for personal data"))
    if any(p.search(unauthored) for p in _DISALLOWED_PATTERNS):
        violations.append(GateViolation(GateRule.DISALLOWED_CONTENT, "disallowed content"))
    elif _ungrounded_match(_GROUNDED_ONLY_PATTERNS, norm, grounding):
        violations.append(GateViolation(GateRule.DISALLOWED_CONTENT, "ungrounded sensitive topic"))

    # -- locale ----------------------------------------------------------------------------
    script = _LOCALES.get(prompt.locale, ("", ""))[0]
    arabic, latin = _script_ratio(text)
    metrics["arabic_script_ratio"] = round(arabic, 3)
    if not script:
        violations.append(GateViolation(GateRule.UNSUPPORTED_LOCALE, f"locale {prompt.locale!r}"))
    elif (script == "arabic" and arabic < 0.6) or (script == "latin" and latin < 0.95):
        violations.append(
            GateViolation(GateRule.WRONG_LOCALE, f"script does not match {prompt.locale}")
        )
    elif _ungrounded_match(
        (_OTHER_SCRIPT, *_FOREIGN_LETTERS.get(prompt.locale, ())), text, grounding
    ):
        violations.append(
            GateViolation(GateRule.WRONG_LOCALE, f"foreign-language text for {prompt.locale}")
        )

    return GateVerdict(accepted=not violations, violations=tuple(violations), metrics=metrics)
