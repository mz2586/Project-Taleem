"""The curriculum knowledge hierarchy (pure-stdlib).

Education System → Grade → Subject → Chapter → Topic (→ Lesson lives in lesson.py).
See docs/10-curriculum-studio/CURRICULUM_ARCHITECTURE.md §3.

A persisted hierarchy is scoped by curriculum pack: the system's ``key`` is the pack id, every
grade must be a grade of that pack and every subject must be in the pack's roster for its grade.
Nodes are identified by their natural keys; ``*_id`` values are canonical paths derived from those
keys (``canonicalize``), so the same input always yields the same stored hierarchy.
"""

from __future__ import annotations

import copy
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Protocol

from .content import LocalizedText
from .packs import CurriculumPack, default_pack


@dataclass
class Topic:
    topic_id: str
    key: str
    title: LocalizedText


@dataclass
class Chapter:
    chapter_id: str
    key: str
    title: LocalizedText
    topics: list[Topic] = field(default_factory=list)


@dataclass
class Subject:
    subject_id: str
    key: str  # e.g. "math"
    title: LocalizedText
    chapters: list[Chapter] = field(default_factory=list)


@dataclass
class Grade:
    grade_id: str
    key: str  # a grade key of the education system's curriculum pack (PK-NCP: KG, G1..G10)
    subjects: list[Subject] = field(default_factory=list)


@dataclass
class EducationSystem:
    system_id: str
    key: str  # e.g. "PK-NCP"
    name: str
    grades: list[Grade] = field(default_factory=list)


# Grade structures and subject rosters are curriculum-pack data (packs.py, packs/*.json), not
# constants. These helpers keep the original API by delegating to the default pack (PK-NCP).


def subjects_for(grade_key: str) -> tuple[str, ...]:
    return default_pack().subjects_for(grade_key)


def is_valid_grade_subject(grade_key: str, subject_key: str) -> bool:
    return default_pack().is_valid_grade_subject(grade_key, subject_key)


def __getattr__(name: str) -> object:
    # Lazy compatibility for the former module constants (now the default pack's data).
    if name == "GRADE_KEYS":
        return default_pack().grade_keys
    if name == "SUBJECT_ROSTER":
        return dict(default_pack().subject_roster)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ---------------------------------------------------------------------------------------------
# Pack-scoped hierarchy rules (used by the application service before persisting)
# ---------------------------------------------------------------------------------------------


def _title_errors(where: str, title: LocalizedText, pack: CurriculumPack) -> list[str]:
    tags = set(title.text) | set(title.audio_ref)
    return [
        f"{where}: title locale {str(t)!r} is not declared by curriculum pack {pack.pack_id}"
        for t in sorted(tags)
        if not pack.supports_locale(t)
    ]


def _dupes(keys: list[str]) -> list[str]:
    return sorted(k for k, n in Counter(keys).items() if n > 1)


class _Keyed(Protocol):
    key: str


def _order(sequence: Sequence[str]) -> Callable[[_Keyed], int]:
    """Sort key: a node's position in ``sequence``; unknown keys sort last (stable)."""
    index = {k: i for i, k in enumerate(sequence)}
    return lambda node: index.get(node.key, len(index))


def check_against_pack(system: EducationSystem, pack: CurriculumPack) -> list[str]:
    """Every reason ``system`` cannot be stored under ``pack`` (empty = valid)."""
    errors: list[str] = []
    if system.key and system.key != pack.pack_id:
        errors.append(f"hierarchy key {system.key!r} does not match curriculum pack {pack.pack_id}")
    for dup in _dupes([g.key for g in system.grades]):
        errors.append(f"duplicate grade {dup!r}")
    for grade in system.grades:
        if grade.key not in pack.grade_keys:
            errors.append(f"grade {grade.key!r} is not a grade of curriculum pack {pack.pack_id}")
            continue
        for dup in _dupes([s.key for s in grade.subjects]):
            errors.append(f"{grade.key}: duplicate subject {dup!r}")
        for subj in grade.subjects:
            where = f"{grade.key}/{subj.key}"
            if not pack.is_valid_grade_subject(grade.key, subj.key):
                errors.append(f"{where}: not in the {pack.pack_id} roster for {grade.key}")
            errors += _title_errors(where, subj.title, pack)
            for dup in _dupes([c.key for c in subj.chapters]):
                errors.append(f"{where}: duplicate chapter {dup!r}")
            for ch in subj.chapters:
                cw = f"{where}/{ch.key}"
                if not ch.key.strip():
                    errors.append(f"{where}: chapter with an empty key")
                errors += _title_errors(cw, ch.title, pack)
                for dup in _dupes([t.key for t in ch.topics]):
                    errors.append(f"{cw}: duplicate topic {dup!r}")
                for tp in ch.topics:
                    if not tp.key.strip():
                        errors.append(f"{cw}: topic with an empty key")
                    errors += _title_errors(f"{cw}/{tp.key}", tp.title, pack)
    return errors


def _merge_title(old: LocalizedText, new: LocalizedText) -> LocalizedText:
    """Per-locale merge: a non-empty incoming value wins; nothing is ever erased."""
    out = copy.deepcopy(old)
    for loc, text in new.text.items():
        if text.strip():
            out.text[loc] = text
    for loc, ref in new.audio_ref.items():
        if ref.strip():
            out.audio_ref[loc] = ref
    return out


def merge_hierarchy(
    existing: EducationSystem | None, incoming: EducationSystem, pack: CurriculumPack
) -> EducationSystem:
    """Merge ``incoming`` into ``existing`` by natural key — idempotent and non-destructive.

    Grades, subjects, chapters and topics are matched by key; new ones are added, titles are merged
    per locale, and nothing absent from ``incoming`` is removed. Grades and subjects follow the
    pack's order; chapters and topics keep first-seen order. Ids are canonicalized.
    """
    base = copy.deepcopy(existing) if existing is not None else None
    result = EducationSystem(
        system_id=pack.pack_id,
        key=pack.pack_id,
        name=incoming.name.strip() or (base.name if base else "") or pack.education_system,
        grades=base.grades if base else [],
    )
    grades = {g.key: g for g in result.grades}
    for g_in in incoming.grades:
        grade = grades.setdefault(g_in.key, Grade(grade_id="", key=g_in.key))
        subjects = {s.key: s for s in grade.subjects}
        for s_in in g_in.subjects:
            subj = subjects.get(s_in.key)
            if subj is None:
                subj = Subject(subject_id="", key=s_in.key, title=LocalizedText())
                subjects[s_in.key] = subj
            subj.title = _merge_title(subj.title, s_in.title)
            chapters = {c.key: c for c in subj.chapters}
            for c_in in s_in.chapters:
                ch = chapters.get(c_in.key)
                if ch is None:
                    ch = Chapter(chapter_id="", key=c_in.key, title=LocalizedText())
                    chapters[c_in.key] = ch
                    subj.chapters.append(ch)
                ch.title = _merge_title(ch.title, c_in.title)
                topics = {t.key: t for t in ch.topics}
                for t_in in c_in.topics:
                    tp = topics.get(t_in.key)
                    if tp is None:
                        tp = Topic(topic_id="", key=t_in.key, title=LocalizedText())
                        topics[t_in.key] = tp
                        ch.topics.append(tp)
                    tp.title = _merge_title(tp.title, t_in.title)
        grade.subjects = sorted(subjects.values(), key=_order(pack.subjects_for(g_in.key)))
    result.grades = sorted(grades.values(), key=_order(pack.grade_keys))
    return canonicalize(result)


def canonicalize(system: EducationSystem) -> EducationSystem:
    """Set every ``*_id`` to its canonical key path (``PK-NCP/G4/math/u1/t1``), in place."""
    system.system_id = system.key
    for g in system.grades:
        g.grade_id = f"{system.key}/{g.key}"
        for s in g.subjects:
            s.subject_id = f"{g.grade_id}/{s.key}"
            for c in s.chapters:
                c.chapter_id = f"{s.subject_id}/{c.key}"
                for t in c.topics:
                    t.topic_id = f"{c.chapter_id}/{t.key}"
    return system


def placement_errors(
    system: EducationSystem | None,
    *,
    pack_id: str,
    grade_key: str,
    subject_key: str,
    chapter_key: str,
    topic_key: str,
) -> list[str]:
    """Why a lesson placement (chapter/topic keys) is not in the pack's stored hierarchy.

    An empty placement has no errors (it is unplaced, not misplaced). ``system`` is the stored
    hierarchy for ``pack_id``, or None when none is stored.
    """
    if not chapter_key and not topic_key:
        return []
    if not chapter_key:
        return [f"topic_key {topic_key!r} requires a chapter_key"]
    if system is None:
        return [f"no stored {pack_id} hierarchy: chapter {chapter_key!r} cannot be verified"]
    where = f"{grade_key}/{subject_key}"
    chapter = next(
        (
            c
            for g in system.grades
            if g.key == grade_key
            for s in g.subjects
            if s.key == subject_key
            for c in s.chapters
            if c.key == chapter_key
        ),
        None,
    )
    if chapter is None:
        return [f"chapter {chapter_key!r} is not in the stored {pack_id} hierarchy for {where}"]
    if topic_key and all(t.key != topic_key for t in chapter.topics):
        return [f"topic {topic_key!r} is not in chapter {chapter_key!r} ({pack_id} {where})"]
    return []
