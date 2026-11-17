"""Ask the teacher: a learner's question answered from the published lesson only (pure).

This is in-house, deterministic retrieval, not a language model. It answers by **quoting authored
lesson text verbatim** (an excerpt of the explanation, a worked-example step, or a misconception
correction), so every answer is grounded by construction and checkable with
:func:`is_grounded_excerpt`. When nothing in the lesson answers the question it says so; it never
invents. Answer keys (``SECRET_ITEM_FIELDS``) are never part of the corpus, and item prompts and
hints are excluded too, so an answer can never point at the solution to a practice question.

Two ways to ask:

- **Tap intents** (no free text): ``example``, ``common_mistake``, ``recap``. Always available.
- **A typed question** (``question``): matched against the lesson by content-word overlap weighted
  by inverse document frequency. Free text is screened for safeguarding disclosures *before* this
  module is called (the application service does that) and is gated by a feature flag.

The module is locale-aware (Urdu and English, or any authored locale) and keeps no state.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from .curriculum_view import LessonView

QUESTION_MAX_CHARS = 300
MAX_ANSWER_PASSAGES = 2
# A typed question needs at least this much IDF-weighted overlap with a passage to be answered.
MIN_SCORE = 1.0


class AskIntent(StrEnum):
    QUESTION = "question"  # a typed question (free text; flag-gated)
    EXAMPLE = "example"  # "show me an example"
    COMMON_MISTAKE = "common_mistake"  # "what do children often get wrong?"
    RECAP = "recap"  # "tell me the main idea again"


TAP_INTENTS: tuple[AskIntent, ...] = (AskIntent.EXAMPLE, AskIntent.COMMON_MISTAKE, AskIntent.RECAP)


class AskOutcome(StrEnum):
    ANSWERED = "answered"
    NOT_IN_LESSON = "not_in_lesson"  # honest: the lesson does not cover it
    HOLDING = "holding"  # the disclosure screen matched; a fixed holding response is served


@dataclass(frozen=True)
class Passage:
    """One retrievable unit of authored text and where it came from."""

    text: str
    source: str  # "explanation#0", "worked_example#2", "correction:<ref>", "title"
    locale: str


@dataclass(frozen=True)
class AskAnswer:
    intent: AskIntent
    outcome: AskOutcome
    passages: tuple[Passage, ...] = ()
    matched_terms: tuple[str, ...] = ()  # the content words that matched (explainability)

    def to_dict(self) -> dict[str, object]:
        return {
            "intent": self.intent.value,
            "outcome": self.outcome.value,
            "answer": [
                {"text": p.text, "source": p.source, "locale": p.locale} for p in self.passages
            ],
            "matched_terms": list(self.matched_terms),
        }


# ------------------------------------------------------------------------------ text handling

# Sentence ends: Latin, Urdu full stop (U+06D4), Arabic question mark (U+061F), and "!".
_SENTENCE_END = re.compile(r"(?<=[.!?۔؟])\s+|\n+")
_WORD = re.compile(r"[\w؀-ۿ]+", re.UNICODE)

# Small function-word lists. Retrieval only needs the high-frequency words that carry no topic.
# fmt: off
_STOPWORDS: frozenset[str] = frozenset(
    {
        # English
        "a", "an", "the", "is", "are", "was", "were", "be", "been", "am", "do", "does", "did",
        "what", "why", "how", "when", "where", "which", "who", "whom", "whose", "can", "could",
        "will", "would", "should", "shall", "may", "might", "must", "i", "me", "my", "you",
        "your", "we", "our", "it", "its", "this", "that", "these", "those", "there", "here",
        "of", "to", "in", "on", "at", "for", "with", "by", "from", "about", "as", "and", "or",
        "but", "if", "so", "not", "no", "yes", "please", "tell", "explain", "mean", "means",
        "meaning", "know", "understand", "dont", "don", "t", "s", "get", "got", "have", "has",
        "had", "some", "any", "all", "more", "most", "very", "just", "then", "than", "also",
        # Urdu
        "کیا", "ہے", "ہیں", "تھا", "تھی", "تھے", "کا", "کی", "کے", "کو", "میں", "سے", "پر",
        "اور", "یا", "یہ", "وہ", "اس", "ان", "کون", "کیوں", "کیسے", "کب", "کہاں", "مجھے", "میرا",
        "میری", "آپ", "ہم", "نہیں", "بھی", "تو", "جو", "ایک", "کر", "کرو", "کریں", "بتائیں",
        "بتاؤ", "مطلب", "سمجھ", "ہو", "گا", "گی", "گے", "لیے", "لئے",
    }
)
# fmt: on


def normalise(text: str) -> str:
    """NFKC, case-folded, with Arabic-script diacritics (harakat) removed."""
    folded = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in folded if not ("ً" <= ch <= "ٟ" or ch == "ٰ"))


def content_words(text: str) -> tuple[str, ...]:
    """The topic-bearing words of ``text`` in order (stop words and single letters dropped)."""
    words = _WORD.findall(normalise(text))
    out: list[str] = []
    for w in words:
        if w in _STOPWORDS or (len(w) < 2 and not w.isdigit()):
            continue
        # Light English plural folding so "fractions" matches "fraction".
        if w.isascii() and len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.append(w)
    return tuple(out)


def sentences(text: str) -> tuple[str, ...]:
    return tuple(s.strip() for s in _SENTENCE_END.split(text) if s and s.strip())


def _pick(localized: dict[str, str], locale: str) -> tuple[str, str]:
    """The text for ``locale``, else English, else any authored locale; with the locale used."""
    for loc in (locale, "en", *sorted(localized)):
        text = localized.get(loc, "")
        if text.strip():
            return text, loc
    return "", locale


# ------------------------------------------------------------------------------ corpus


def corpus(lesson: LessonView, locale: str) -> tuple[Passage, ...]:
    """Every passage an answer may quote, in the learner's locale where authored.

    Explanation sentences, worked-example steps, vocabulary definitions and misconception
    corrections. Never item
    prompts, hints, options or any answer-key field.
    """
    out: list[Passage] = []
    explanation, exp_loc = _pick(lesson.explanation, locale)
    for i, sentence in enumerate(sentences(explanation)):
        out.append(Passage(sentence, f"explanation#{i}", exp_loc))
    out.extend(_worked_steps(lesson, locale))
    for i, (term, definition) in enumerate(lesson.vocabulary):
        word, loc = _pick(term, locale)
        # The definition in the same locale as the term where authored, so a quote never mixes.
        meaning = definition.get(loc, "") or _pick(definition, loc)[0]
        if word.strip() and meaning.strip():
            # Quoted as "<term>: <definition>", an authored pair (checked by is_grounded_excerpt).
            out.append(Passage(f"{word.strip()}: {meaning.strip()}", f"vocabulary#{i}", loc))
    for ref in sorted(lesson.misconception_corrections):
        text = lesson.misconception_corrections[ref].strip()
        if text:
            out.append(Passage(text, f"correction:{ref}", locale))
    return tuple(out)


def _worked_steps(lesson: LessonView, locale: str) -> list[Passage]:
    out: list[Passage] = []
    if lesson.worked_example_steps_localized:
        for i, step in enumerate(lesson.worked_example_steps_localized):
            text, loc = _pick(step, locale)
            if text.strip():
                out.append(Passage(text.strip(), f"worked_example#{i}", loc))
        return out
    for i, text in enumerate(lesson.worked_example_steps):
        if text.strip():
            out.append(Passage(text.strip(), f"worked_example#{i}", "en"))
    return out


# ------------------------------------------------------------------------------ answering


def answer_intent(lesson: LessonView, intent: AskIntent, locale: str = "ur") -> AskAnswer:
    """Answer a tap intent from the lesson. Deterministic; no free text involved."""
    passages = corpus(lesson, locale)
    if intent is AskIntent.EXAMPLE:
        chosen = tuple(p for p in passages if p.source.startswith("worked_example#"))
    elif intent is AskIntent.COMMON_MISTAKE:
        chosen = tuple(p for p in passages if p.source.startswith("correction:"))[:1]
    elif intent is AskIntent.RECAP:
        chosen = tuple(p for p in passages if p.source.startswith("explanation#"))[:2]
    else:
        raise ValueError(f"not a tap intent: {intent}")
    outcome = AskOutcome.ANSWERED if chosen else AskOutcome.NOT_IN_LESSON
    return AskAnswer(intent, outcome, chosen)


def answer_question(lesson: LessonView, question: str, locale: str = "ur") -> AskAnswer:
    """Answer a typed question by quoting the best-matching authored passages, or say the lesson
    does not cover it. The caller has already screened ``question`` for disclosures."""
    asked = set(content_words(question[:QUESTION_MAX_CHARS]))
    passages = corpus(lesson, locale)
    if not asked or not passages:
        return AskAnswer(AskIntent.QUESTION, AskOutcome.NOT_IN_LESSON)

    docs = [set(content_words(p.text)) for p in passages]
    n = len(docs)
    idf = {w: math.log(1 + n / (1 + sum(w in d for d in docs))) + 0.5 for w in asked}

    scored: list[tuple[float, int, frozenset[str]]] = []
    for i, d in enumerate(docs):
        hit = frozenset(asked & d)
        if hit:
            scored.append((sum(idf[w] for w in hit), i, hit))
    scored.sort(key=lambda s: (-s[0], s[1]))  # best first; ties keep authored order
    best = [s for s in scored if s[0] >= MIN_SCORE][:MAX_ANSWER_PASSAGES]
    if not best:
        return AskAnswer(AskIntent.QUESTION, AskOutcome.NOT_IN_LESSON)
    best.sort(key=lambda s: s[1])  # read them in lesson order
    terms = sorted(set().union(*(s[2] for s in best)))
    return AskAnswer(
        AskIntent.QUESTION,
        AskOutcome.ANSWERED,
        tuple(passages[s[1]] for s in best),
        tuple(terms),
    )


def is_grounded_excerpt(lesson: LessonView, answer: AskAnswer) -> bool:
    """True iff every quoted passage appears verbatim inside an authored lesson text."""
    authored: list[str] = [
        *lesson.explanation.values(),
        *lesson.worked_example_steps,
        *(t for step in lesson.worked_example_steps_localized for t in step.values()),
        *lesson.misconception_corrections.values(),
    ]
    vocab = {
        f"{t.strip()}: {d.strip()}"
        for term, definition in lesson.vocabulary
        for t in term.values()
        for d in definition.values()
        if t.strip() and d.strip()
    }
    return all(p.text in vocab or any(p.text in a for a in authored) for p in answer.passages)


def reveals_answer_key(lesson: LessonView, answer: AskAnswer) -> bool:
    """True if a quoted passage contains an item's correct option or accepted answer verbatim as
    a whole passage (a guard; the corpus excludes item fields, so this should never be true)."""
    keys: set[str] = set()
    for pool in (
        lesson.practice_items,
        lesson.homework_items,
        lesson.assessment_formative,
        lesson.assessment_summative,
    ):
        for item in pool:
            keys.update(a.strip() for a in item.accepted_answers if a.strip())
            chosen_ok = item.kind == "choose" and 0 <= item.correct_option < len(item.options)
            if chosen_ok:
                keys.add(item.options[item.correct_option].strip())
    return any(p.text.strip() in keys for p in answer.passages)
