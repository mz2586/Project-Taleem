"""Import the human-authored lesson content already in the repository into the Grade 4 drafts.

Sources (all ``authored-original`` project content, imported verbatim — see ``curriculum_content``):

- the ★ exemplar sections of ``curriculum/grade-4/*.md`` and every lesson section of
  ``GRADE4_MATH_CURRICULUM.md`` §7 (vocabulary, worked-example scripts, quoted hints, library
  misconceptions, homework, parent/teacher notes);
- for ``MATH-G4-FR-01`` only, the vertical-slice fixture ``build_fractions_lesson()`` (scripts,
  explanation, practice items with options + answer keys, hints, misconceptions, homework, notes,
  AI-teaching object). Its audio pointers, media reference, offline-package id and accessibility
  note are **not** imported: they point at, or claim, assets that do not exist in the repository.

Rules (asserted by ``tests/test_curriculum_ingest.py``):

- Only drafts are updated, only through ``CurriculumStudioService.update``; nothing is submitted,
  reviewed or published.
- Every imported lesson is tagged ``provisional`` + ``content-status:provisional-pending-review``,
  ``imported-from:<doc §section>`` and a ``provenance-note:`` so no UI or report can mistake it for
  reviewed curriculum.
- Non-destructive: each imported field's fingerprint is recorded as ``import-hash:<field>=<sha>``.
  A field is (re)written only if it still equals the last imported value, or — never imported —
  still equals the empty spine draft. Anything else is an author's edit: it is kept and reported.
"""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from ..contexts.curriculum_studio.application.service import CurriculumStudioService
from ..contexts.curriculum_studio.domain.assessment import AssessmentItem, Competency, ItemType
from ..contexts.curriculum_studio.domain.content import (
    Hint,
    Locale,
    LocalizedText,
    Misconception,
    VocabularyTerm,
    WorkedExample,
)
from ..contexts.curriculum_studio.domain.lesson import Lesson
from ..contexts.curriculum_studio.domain.workflow import WorkflowState
from .curriculum_ai_drafts import AI_FIELD_TAG, AI_TAGS, AIDraft
from .curriculum_content import AuthoredContent, Bilingual
from .curriculum_spine import Objective, Spine

PROVISIONAL_TAGS: tuple[str, ...] = ("provisional", "content-status:provisional-pending-review")
HASH_TAG = "import-hash:"
SOURCE_TAG = "imported-from:"
NOTE_TAG = "provenance-note:"
PROVENANCE_NOTE = (
    "authored-original project content imported verbatim; provisional, pending the 5-stage "
    "human review; not reviewed curriculum"
)
AI_DRAFT_NOTE = (
    "fields tagged ai-drafted-field were written by an AI model as a first draft, never "
    "human-reviewed; a subject author must rewrite or confirm them before review"
)

FIXTURE_CODE = "MATH-G4-FR-01"
FIXTURE_SOURCE = "services/core-api/src/taleem_core/vertical_slice/fractions_lesson.py"
# Fixture fields imported verbatim (audio pointers stripped).
FIXTURE_FIELDS: tuple[str, ...] = (
    "keywords",
    "teacher_script",
    "student_explanation",
    "worked_examples",
    "interactive_activities",
    "practice_questions",
    "hints",
    "common_misconceptions",
    "adaptive_remediation",
    "homework",
    "revision_notes",
    "summary",
    "parent_notes",
    "mentor_notes",
    "ai_teaching_object",
    "assessment",
)
FIXTURE_NOT_IMPORTED: tuple[tuple[str, str], ...] = (
    ("audio_ref (all fields)", "points to audio files that do not exist in the repository"),
    ("visual_concepts", "references a media asset (`m-fraction-circle`) that does not exist"),
    ("offline_package", "names a package that has not been built"),
    ("accessibility_notes", "states that audio and an image are provided; neither exists"),
)


# --------------------------------------------------------------------------------- fingerprints


def _jsonable(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: _jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k.value if isinstance(k, Enum) else k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def fingerprint(value: Any) -> str:
    blob = json.dumps(_jsonable(value), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _recorded_hashes(tags: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in tags:
        if t.startswith(HASH_TAG) and "=" in t:
            name, digest = t[len(HASH_TAG) :].split("=", 1)
            out[name] = digest
    return out


# --------------------------------------------------------------------------------- conversion


def _loc(b: Bilingual) -> LocalizedText:
    text: dict[Locale, str] = {}
    if b.ur:
        text[Locale.UR] = b.ur
    if b.en:
        text[Locale.EN] = b.en
    return LocalizedText(text=text)


def _strip_audio(value: Any) -> Any:
    """Deep-copy ``value`` with every audio pointer removed (the files do not exist)."""
    value = copy.deepcopy(value)

    def walk(v: Any) -> None:
        if isinstance(v, LocalizedText):
            v.audio_ref = {}
        elif isinstance(v, VocabularyTerm):
            v.pronunciation_audio_ref = ""
        if dataclasses.is_dataclass(v) and not isinstance(v, type):
            for f in dataclasses.fields(v):
                walk(getattr(v, f.name))
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(value)
    return value


def doc_fields(o: Objective, c: AuthoredContent) -> dict[str, Any]:
    """Studio field values for one section's authored content (only what the section states)."""
    out: dict[str, Any] = {}
    if c.vocabulary:
        out["vocabulary"] = [
            VocabularyTerm(term=_loc(t), definition=LocalizedText()) for t in c.vocabulary
        ]
    if c.worked_example_steps:
        out["worked_examples"] = [
            WorkedExample(prompt=LocalizedText(), steps=[_loc(s) for s in c.worked_example_steps])
        ]
    if c.hints:
        out["hints"] = [Hint(trigger=f"hint-ladder:{lvl}", hint=_loc(h)) for lvl, h in c.hints]
    if c.misconceptions:
        out["common_misconceptions"] = [
            Misconception(misconception=_loc(m.misconception), correction=_loc(m.correction))
            for m in c.misconceptions
        ]
    if c.homework:
        out["homework"] = [
            AssessmentItem(
                item_id=f"hw-{o.code.lower()}-1",
                type=ItemType.SHORT,
                objective_ref=o.code,
                competency=Competency(o.competency),
                stem=_loc(c.homework),
            )
        ]
    if c.parent_note:
        out["parent_notes"] = _loc(c.parent_note)
    if c.teacher_note:
        out["mentor_notes"] = _loc(c.teacher_note)
    return out


def language_coverage(value: Any) -> str:
    """ "" when every text in ``value`` has both sides; else which side the documents gave."""
    sides: set[str] = set()

    def walk(v: Any) -> None:
        if isinstance(v, LocalizedText):
            ur, en = v.has(Locale.UR), v.has(Locale.EN)
            if ur or en:
                sides.add("both" if ur and en else ("ur" if ur else "en"))
            return
        if dataclasses.is_dataclass(v) and not isinstance(v, type):
            for f in dataclasses.fields(v):
                walk(getattr(v, f.name))
        elif isinstance(v, (list, tuple)):
            for x in v:
                walk(x)

    walk(value)
    one_sided = sides - {"both"}
    if not one_sided:
        return ""
    if sides == {"en"}:
        return "English only"
    if sides == {"ur"}:
        return "Urdu only"
    return "partly one language"


def fixture_fields(fixture: Lesson) -> dict[str, Any]:
    return {name: _strip_audio(getattr(fixture, name)) for name in FIXTURE_FIELDS}


def content_manifest(
    spine: Spine,
    contents: Mapping[str, AuthoredContent],
    fixture: Lesson | None,
    drafts: Mapping[str, AIDraft] | None = None,
) -> dict[str, Any]:
    """Per objective: the import sources and a fingerprint of every field that would be imported.

    Published in ``spine.json`` so ``--check`` also catches drift in the authored prose.
    """
    manifest: dict[str, Any] = {}
    for o in spine.objectives:
        values, sources, _not, ai = _planned(o, contents, fixture, drafts or {})
        if values:
            manifest[o.code] = {
                "sources": sources,
                "status": PROVISIONAL_TAGS[1] if len(ai) < len(values) else AI_TAGS[1],
                "fields": {name: fingerprint(values[name]) for name in sorted(values)},
            }
            if ai:
                manifest[o.code]["ai_drafted_fields"] = sorted(ai)
    return manifest


# --------------------------------------------------------------------------------- import


@dataclass
class ImportEntry:
    code: str
    lesson_id: str
    sources: list[str] = field(default_factory=list)
    imported: list[str] = field(default_factory=list)  # written this run
    unchanged: list[str] = field(default_factory=list)  # already equal to the import
    author_edited: list[str] = field(default_factory=list)  # kept: an author changed it
    not_imported: list[tuple[str, str]] = field(default_factory=list)
    ai_drafted: list[str] = field(default_factory=list)  # fields whose value is an AI draft
    one_language: dict[str, str] = field(default_factory=dict)  # field -> "English only" etc.
    skipped_state: str = ""  # non-draft lesson: nothing touched

    @property
    def current(self) -> list[str]:
        """Fields whose value is (still) the imported one."""
        return sorted(set(self.imported) | set(self.unchanged))


@dataclass
class ImportResult:
    entries: list[ImportEntry] = field(default_factory=list)

    def by_code(self) -> dict[str, ImportEntry]:
        return {e.code: e for e in self.entries}

    @property
    def updated(self) -> list[ImportEntry]:
        return [e for e in self.entries if e.imported]


def _planned(
    o: Objective,
    contents: Mapping[str, AuthoredContent],
    fixture: Lesson | None,
    drafts: Mapping[str, AIDraft],
) -> tuple[dict[str, Any], list[str], list[tuple[str, str]], set[str]]:
    """(values, sources, not imported, AI-drafted field names). Human text always wins: the
    documents first, then the FR-01 fixture; an AI draft fills only the fields still empty, plus
    the missing language of a human text field written in one language only."""
    values: dict[str, Any] = {}
    sources: list[str] = []
    not_imported: list[tuple[str, str]] = []
    c = contents.get(o.code)
    if c is not None:
        values.update(doc_fields(o, c))
        sources.append(c.source)
        not_imported += c.not_imported
    if o.code == FIXTURE_CODE and fixture is not None:
        for name, value in fixture_fields(fixture).items():
            values.setdefault(name, value)  # the doc section's own text wins where both exist
        sources.append(f"{FIXTURE_SOURCE} (build_fractions_lesson)")
        not_imported += list(FIXTURE_NOT_IMPORTED)
    ai: set[str] = set()
    d = drafts.get(o.code)
    if d is not None:
        for name, value in d.values.items():
            if name not in values:
                values[name] = value
                ai.add(name)
            elif isinstance(value, LocalizedText) and isinstance(values[name], LocalizedText):
                # A human text written in one language only: the draft supplies the missing side.
                merged = copy.deepcopy(values[name])
                for loc, text in value.text.items():
                    if not merged.has(loc):
                        merged.text[loc] = text
                if merged != values[name]:
                    values[name] = merged
                    ai.add(name)
        if ai:
            sources.append(f"{d.source} (AI draft)")
    return values, sources, not_imported, ai


def _retag(
    tags: list[str], sources: list[str], hashes: dict[str, str], ai_fields: list[str]
) -> list[str]:
    keep = [
        t
        for t in tags
        if not t.startswith((HASH_TAG, SOURCE_TAG, NOTE_TAG, AI_FIELD_TAG))
        and t not in PROVISIONAL_TAGS
        and t not in AI_TAGS
    ]
    ai = (
        list(AI_TAGS) + [f"{NOTE_TAG}{AI_DRAFT_NOTE}"] + [f"{AI_FIELD_TAG}{n}" for n in ai_fields]
        if ai_fields
        else []
    )
    return (
        keep
        + list(PROVISIONAL_TAGS)
        + [f"{SOURCE_TAG}{s}" for s in sources]
        + [f"{NOTE_TAG}{PROVENANCE_NOTE}"]
        + ai
        + [f"{HASH_TAG}{name}={digest}" for name, digest in sorted(hashes.items())]
    )


def import_authored(
    spine: Spine,
    service: CurriculumStudioService,
    contents: Mapping[str, AuthoredContent],
    baseline: Callable[[Objective], Lesson],
    lesson_ids: Mapping[str, str],
    fixture: Lesson | None = None,
    drafts: Mapping[str, AIDraft] | None = None,
) -> ImportResult:
    """Write authored content into the matching drafts (non-destructive, idempotent).

    ``baseline(o)`` is the empty spine draft for ``o`` (what a never-edited field equals);
    ``lesson_ids`` maps objective code -> the lesson that carries it.
    """
    result = ImportResult()
    for o in spine.objectives:
        values, sources, not_imported, ai = _planned(o, contents, fixture, drafts or {})
        if not values:
            continue
        lesson = service.get(lesson_ids[o.code])
        entry = ImportEntry(o.code, lesson.lesson_id, sources, not_imported=not_imported)
        result.entries.append(entry)
        if lesson.workflow.state is not WorkflowState.DRAFT:
            entry.skipped_state = lesson.workflow.state.value
            continue
        empty = baseline(o)
        recorded = _recorded_hashes(lesson.metadata.tags)
        hashes = dict(recorded)
        changed = False
        for name in sorted(values):
            new = values[name]
            coverage = language_coverage(new)
            if coverage:
                entry.one_language[name] = coverage
            new_fp = fingerprint(new)
            cur_fp = fingerprint(getattr(lesson, name))
            last = recorded.get(name)
            if last is not None and cur_fp != last:
                entry.author_edited.append(name)
                continue
            if last is None and cur_fp not in (new_fp, fingerprint(getattr(empty, name))):
                entry.author_edited.append(name)  # authored in the Studio before any import
                continue
            if cur_fp == new_fp:
                entry.unchanged.append(name)
            else:
                setattr(lesson, name, new)
                entry.imported.append(name)
                changed = True
            hashes[name] = new_fp
        entry.ai_drafted = sorted(ai & set(entry.current))
        tags = (
            _retag(lesson.metadata.tags, sources, hashes, entry.ai_drafted)
            if entry.current
            else None
        )
        if tags is not None and tags != lesson.metadata.tags:
            lesson.metadata.tags = tags
            changed = True
        if changed:
            updated = service.update(lesson)
            if updated.workflow.state is not WorkflowState.DRAFT:  # pragma: no cover - defensive
                raise RuntimeError(f"{updated.lesson_id} left draft state on update")
    return result


__all__ = [
    "FIXTURE_CODE",
    "PROVISIONAL_TAGS",
    "content_manifest",
    "ImportEntry",
    "ImportResult",
    "doc_fields",
    "fingerprint",
    "fixture_fields",
    "import_authored",
]
