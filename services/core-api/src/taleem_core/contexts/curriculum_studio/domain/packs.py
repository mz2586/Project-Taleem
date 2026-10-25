"""Curriculum packs (pure-stdlib): market specifics as versioned data, not core logic.

A *curriculum pack* describes one curriculum region / education system: its country, ordered grade
structure, subject roster per grade, academic-calendar descriptor, the locales its content may be
written in (with text direction), and the **instructional locales** it supports. Each instructional
locale carries its own publish rules — which locales every core field must be complete in, which
need recorded audio, and which are measured for readability (with per-locale, per-grade limits).

A lesson declares its pack (``Metadata.curriculum_pack``) and its instructional locale(s)
(``Metadata.instructional_locales``; empty = the pack's language of instruction). The validator
reads every market rule from there. A pack says nothing about the *interface* language: UI locale,
instructional locale, and curriculum region are independent settings.

Packs ship as JSON under ``curriculum_studio/packs/`` and are validated on load — a malformed pack
is an error, never a silently weaker rule set. Shipping a pack file is not a claim that the
curriculum is supported for learners; that needs qualified validation.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from .content import Locale

DEFAULT_PACK_ID = "PK-NCP"
PACK_SCHEMA_VERSION = 1

TEXT_DIRECTIONS = frozenset({"ltr", "rtl"})
# Unit-check (end-of-unit examination) defaults (PROGRESSION_AND_EXAMINATION_CONTRACT §2). A pack
# may override both in an optional ``unit_check`` object.
DEFAULT_UNIT_CHECK_ITEMS = 10
DEFAULT_UNIT_CHECK_PASS_PERCENT = 70
MAX_UNIT_CHECK_ITEMS = 50
NUMERAL_SYSTEMS = frozenset({"western", "eastern"})  # platform/i18n.NumeralSystem values

_PACKS_PACKAGE = "taleem_core.contexts.curriculum_studio.packs"


class PackError(ValueError):
    """A curriculum pack file is malformed or internally inconsistent."""


@dataclass(frozen=True)
class LocaleSpec:
    tag: Locale
    name: str  # human name used in findings, e.g. "Urdu"
    direction: str  # "ltr" | "rtl"


@dataclass(frozen=True)
class ReadabilityLimits:
    """Max average words per sentence, by grade, for text in one locale."""

    max_words: Mapping[str, int]
    default_max_words: int

    def for_grade(self, grade_key: str) -> int:
        return self.max_words.get(grade_key, self.default_max_words)


@dataclass(frozen=True)
class InstructionRules:
    """Publish rules for lessons taught in one instructional locale (or a union of several)."""

    required_locales: tuple[Locale, ...]  # every core field complete in all of these
    audio_required_locales: tuple[Locale, ...]  # student_explanation needs recorded audio in each
    readability_locales: tuple[Locale, ...]  # student_explanation measured in each


@dataclass(frozen=True)
class Term:
    key: str
    name: str


@dataclass(frozen=True)
class AcademicCalendar:
    """Descriptive only (not enforced): when the year starts and how it is divided."""

    year_start_month: int  # 1-12
    terms: tuple[Term, ...]
    notes: str = ""


@dataclass(frozen=True)
class CurriculumPack:
    pack_id: str
    version: str
    country: str  # ISO 3166-1 alpha-2
    education_system: str
    grade_keys: tuple[str, ...]
    subject_roster: Mapping[str, tuple[str, ...]]
    academic_calendar: AcademicCalendar
    language_of_instruction: Locale  # the primary instructional locale
    locales: Mapping[Locale, LocaleSpec]  # every locale content in this pack may be written in
    instructional_locales: Mapping[Locale, InstructionRules]
    readability: Mapping[Locale, ReadabilityLimits]
    default_numeral_system: str
    # Unit checks: the paper's length and the pass mark (percent of items correct).
    unit_check_items: int = DEFAULT_UNIT_CHECK_ITEMS
    unit_check_pass_percent: int = DEFAULT_UNIT_CHECK_PASS_PERCENT

    # ---- roster ----
    def subjects_for(self, grade_key: str) -> tuple[str, ...]:
        return self.subject_roster.get(grade_key, ())

    def is_valid_grade_subject(self, grade_key: str, subject_key: str) -> bool:
        return subject_key in self.subject_roster.get(grade_key, ())

    # ---- locales ----
    def supports_locale(self, tag: str) -> bool:
        return tag in self.locales

    def direction_for(self, tag: str) -> str:
        return self.locales[Locale(tag)].direction

    def locale_name(self, tag: str) -> str:
        spec = self.locales.get(Locale(tag))
        return spec.name if spec is not None else str(tag)

    # ---- publish rules ----
    def rules_for(self, instructional: Sequence[Locale]) -> InstructionRules:
        """The effective rules for a lesson taught in ``instructional`` (empty = primary).

        Several instructional locales combine as a *union* (strictest of each), so declaring an
        extra instructional locale can only add requirements. Raises ``KeyError`` for a locale the
        pack does not offer as instructional (callers turn that into a BLOCKER finding).
        """
        chosen = list(instructional) or [self.language_of_instruction]
        selected = [self.instructional_locales[loc] for loc in chosen]

        def union(attr: str) -> tuple[Locale, ...]:
            out: list[Locale] = []
            for rules in selected:
                for loc in getattr(rules, attr):
                    if loc not in out:
                        out.append(loc)
            return tuple(out)

        return InstructionRules(
            required_locales=union("required_locales"),
            audio_required_locales=union("audio_required_locales"),
            readability_locales=union("readability_locales"),
        )

    def summary(self) -> dict[str, Any]:
        """Public, read-only description (the pack listing API)."""
        return {
            "pack_id": self.pack_id,
            "version": self.version,
            "country": self.country,
            "education_system": self.education_system,
            "language_of_instruction": str(self.language_of_instruction),
            "instructional_locales": [str(t) for t in self.instructional_locales],
            "locales": [
                {"tag": str(s.tag), "name": s.name, "direction": s.direction}
                for s in self.locales.values()
            ],
        }


# ---------------------------------------------------------------------------------------------
# Parsing + validation of a pack document
# ---------------------------------------------------------------------------------------------


def _req(data: Mapping[str, Any], key: str, kind: type | tuple[type, ...], src: str) -> Any:
    if key not in data:
        raise PackError(f"{src}: missing required field {key!r}")
    value = data[key]
    if not isinstance(value, kind) or isinstance(value, bool) and kind is not bool:
        raise PackError(f"{src}: field {key!r} has the wrong type")
    return value


def _locale(tag: Any, where: str, src: str) -> Locale:
    try:
        return Locale(tag)
    except ValueError as exc:
        raise PackError(f"{src}: {where}: {exc}") from exc


def _str_list(value: Any, where: str, src: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise PackError(f"{src}: {where} must be a list of non-empty strings")
    if len(set(value)) != len(value):
        raise PackError(f"{src}: {where} contains duplicates")
    return list(value)


def _known_locales(
    tags: Any, where: str, locales: Mapping[Locale, LocaleSpec], src: str
) -> tuple[Locale, ...]:
    out = tuple(_locale(t, where, src) for t in _str_list(tags, where, src))
    for loc in out:
        if loc not in locales:
            raise PackError(f"{src}: {where} uses locale {loc!r} not declared in 'locales'")
    return out


def _positive_int(value: Any, where: str, src: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise PackError(f"{src}: {where} must be a positive integer")
    return value


def parse_pack(data: Any, source: str = "<pack>") -> CurriculumPack:
    """Build a ``CurriculumPack`` from a decoded JSON document, validating it fully."""
    src = source
    if not isinstance(data, dict):
        raise PackError(f"{src}: a pack must be a JSON object")
    schema = _req(data, "schema_version", int, src)
    if schema != PACK_SCHEMA_VERSION:
        raise PackError(f"{src}: unsupported schema_version {schema} (expected 1)")

    pack_id = _req(data, "pack_id", str, src).strip()
    if not pack_id:
        raise PackError(f"{src}: pack_id must be non-empty")
    src = f"{source} [{pack_id}]"
    version = _req(data, "version", str, src).strip()
    if not version:
        raise PackError(f"{src}: version must be non-empty")
    country = _req(data, "country", str, src)
    if len(country) != 2 or not country.isascii() or not country.isupper():
        raise PackError(f"{src}: country must be an ISO 3166-1 alpha-2 code, got {country!r}")
    education_system = _req(data, "education_system", str, src).strip()
    if not education_system:
        raise PackError(f"{src}: education_system must be non-empty")

    # Grades + roster.
    grades = tuple(_str_list(_req(data, "grades", list, src), "grades", src))
    if not grades:
        raise PackError(f"{src}: grades must not be empty")
    roster_raw = _req(data, "subject_roster", dict, src)
    roster: dict[str, tuple[str, ...]] = {}
    for grade, subjects in roster_raw.items():
        if grade not in grades:
            raise PackError(f"{src}: subject_roster names unknown grade {grade!r}")
        roster[grade] = tuple(_str_list(subjects, f"subject_roster[{grade}]", src))
    missing = [g for g in grades if g not in roster]
    if missing:
        raise PackError(f"{src}: subject_roster has no entry for grade(s) {missing}")
    # Keep the roster in the pack's declared grade order.
    roster = {g: roster[g] for g in grades}

    # Calendar.
    cal = _req(data, "academic_calendar", dict, src)
    start = _req(cal, "year_start_month", int, f"{src} academic_calendar")
    if not 1 <= start <= 12:
        raise PackError(f"{src}: academic_calendar.year_start_month must be 1-12")
    terms_raw = _req(cal, "terms", list, f"{src} academic_calendar")
    terms: list[Term] = []
    for i, t in enumerate(terms_raw):
        if not isinstance(t, dict):
            raise PackError(f"{src}: academic_calendar.terms[{i}] must be an object")
        terms.append(
            Term(
                key=_req(t, "key", str, f"{src} terms[{i}]"),
                name=_req(t, "name", str, f"{src} terms[{i}]"),
            )
        )
    if not terms:
        raise PackError(f"{src}: academic_calendar.terms must not be empty")
    if len({t.key for t in terms}) != len(terms):
        raise PackError(f"{src}: academic_calendar.terms has duplicate keys")
    notes = cal.get("notes", "")
    if not isinstance(notes, str):
        raise PackError(f"{src}: academic_calendar.notes must be a string")
    calendar = AcademicCalendar(year_start_month=start, terms=tuple(terms), notes=notes)

    # Locales (content-writing locales, each with a text direction).
    locales_raw = _req(data, "locales", dict, src)
    if not locales_raw:
        raise PackError(f"{src}: locales must not be empty")
    locales: dict[Locale, LocaleSpec] = {}
    for tag, spec in locales_raw.items():
        loc = _locale(tag, "locales", src)
        if not isinstance(spec, dict):
            raise PackError(f"{src}: locales[{tag}] must be an object")
        if "direction" not in spec:
            raise PackError(f"{src}: locale {tag!r} is missing its text direction")
        direction = spec["direction"]
        if direction not in TEXT_DIRECTIONS:
            raise PackError(f"{src}: locale {tag!r} direction must be 'ltr' or 'rtl'")
        name = _req(spec, "name", str, f"{src} locales[{tag}]").strip()
        if not name:
            raise PackError(f"{src}: locale {tag!r} needs a name")
        locales[loc] = LocaleSpec(tag=loc, name=name, direction=direction)

    # Readability limits per locale.
    readability_raw = _req(data, "readability", dict, src)
    readability: dict[Locale, ReadabilityLimits] = {}
    for tag, lim in readability_raw.items():
        loc = _locale(tag, "readability", src)
        if loc not in locales:
            raise PackError(f"{src}: readability uses locale {tag!r} not declared in 'locales'")
        if not isinstance(lim, dict):
            raise PackError(f"{src}: readability[{tag}] must be an object")
        per_grade = _req(lim, "max_words_per_sentence", dict, f"{src} readability[{tag}]")
        for grade in per_grade:
            if grade not in grades:
                raise PackError(f"{src}: readability[{tag}] names unknown grade {grade!r}")
        missing_r = [g for g in grades if g not in per_grade]
        if missing_r:
            raise PackError(f"{src}: readability[{tag}] has no limit for grade(s) {missing_r}")
        readability[loc] = ReadabilityLimits(
            max_words={
                g: _positive_int(per_grade[g], f"readability[{tag}][{g}]", src) for g in grades
            },
            default_max_words=_positive_int(
                _req(lim, "default_max_words", int, src), f"readability[{tag}].default", src
            ),
        )

    # Instructional locales and their publish rules.
    instr_raw = _req(data, "instructional_locales", dict, src)
    if not instr_raw:
        raise PackError(f"{src}: instructional_locales must not be empty")
    instructional: dict[Locale, InstructionRules] = {}
    for tag, rules in instr_raw.items():
        loc = _locale(tag, "instructional_locales", src)
        where = f"instructional_locales[{tag}]"
        if loc not in locales:
            raise PackError(f"{src}: {where}: locale not declared in 'locales'")
        if not isinstance(rules, dict):
            raise PackError(f"{src}: {where} must be an object")
        required = _known_locales(
            _req(rules, "required_locales", list, src), f"{where}.required_locales", locales, src
        )
        if loc not in required:
            raise PackError(f"{src}: {where}: the instructional locale must itself be required")
        audio = _known_locales(
            _req(rules, "audio_required_locales", list, src),
            f"{where}.audio_required_locales",
            locales,
            src,
        )
        readable = _known_locales(
            _req(rules, "readability_locales", list, src),
            f"{where}.readability_locales",
            locales,
            src,
        )
        if not readable:
            raise PackError(f"{src}: {where}.readability_locales must not be empty")
        for group, label in ((audio, "audio_required_locales"), (readable, "readability_locales")):
            for r in group:
                if r not in required:
                    raise PackError(f"{src}: {where}.{label}: {r!r} is not a required locale")
        for r in readable:
            if r not in readability:
                raise PackError(f"{src}: {where}: no readability limits for locale {r!r}")
        instructional[loc] = InstructionRules(required, audio, readable)

    primary = _locale(
        _req(data, "language_of_instruction", str, src), "language_of_instruction", src
    )
    if primary not in instructional:
        raise PackError(f"{src}: language_of_instruction {primary!r} is not instructional")

    numerals = _req(data, "default_numeral_system", str, src)
    if numerals not in NUMERAL_SYSTEMS:
        raise PackError(f"{src}: default_numeral_system must be one of {sorted(NUMERAL_SYSTEMS)}")

    check_items, check_pass = _unit_check(data.get("unit_check"), src)

    return CurriculumPack(
        pack_id=pack_id,
        version=version,
        country=country,
        education_system=education_system,
        grade_keys=grades,
        subject_roster=roster,
        academic_calendar=calendar,
        language_of_instruction=primary,
        locales=locales,
        instructional_locales=instructional,
        readability=readability,
        default_numeral_system=numerals,
        unit_check_items=check_items,
        unit_check_pass_percent=check_pass,
    )


def _unit_check(value: Any, src: str) -> tuple[int, int]:
    """The optional ``unit_check`` settings: ``{"items": 1..50, "pass_mark_percent": 1..100}``."""
    if value is None:
        return DEFAULT_UNIT_CHECK_ITEMS, DEFAULT_UNIT_CHECK_PASS_PERCENT
    if not isinstance(value, dict):
        raise PackError(f"{src}: unit_check must be an object")
    unknown = sorted(set(value) - {"items", "pass_mark_percent"})
    if unknown:
        raise PackError(f"{src}: unit_check has unknown field(s) {unknown}")
    items = value.get("items", DEFAULT_UNIT_CHECK_ITEMS)
    passing = value.get("pass_mark_percent", DEFAULT_UNIT_CHECK_PASS_PERCENT)
    _positive_int(items, "unit_check.items", src)
    _positive_int(passing, "unit_check.pass_mark_percent", src)
    if items > MAX_UNIT_CHECK_ITEMS:
        raise PackError(f"{src}: unit_check.items must be at most {MAX_UNIT_CHECK_ITEMS}")
    if passing > 100:
        raise PackError(f"{src}: unit_check.pass_mark_percent must be at most 100")
    return int(items), int(passing)


def load_pack_file(path: Path) -> CurriculumPack:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PackError(f"{path.name}: invalid JSON: {exc}") from exc
    return parse_pack(data, source=path.name)


# ---------------------------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------------------------


class PackRegistry:
    """The set of curriculum packs the platform knows, keyed by ``pack_id``."""

    def __init__(self, packs: Iterable[CurriculumPack]) -> None:
        self._packs: dict[str, CurriculumPack] = {}
        for pack in packs:
            if pack.pack_id in self._packs:
                raise PackError(f"duplicate curriculum pack id {pack.pack_id!r}")
            self._packs[pack.pack_id] = pack

    @classmethod
    def from_directory(cls, directory: Path) -> PackRegistry:
        files = sorted(directory.glob("*.json"))
        return cls(load_pack_file(f) for f in files)

    def get(self, pack_id: str) -> CurriculumPack | None:
        return self._packs.get(pack_id)

    def require(self, pack_id: str) -> CurriculumPack:
        pack = self._packs.get(pack_id)
        if pack is None:
            raise PackError(f"unknown curriculum pack {pack_id!r}")
        return pack

    def packs(self) -> list[CurriculumPack]:
        return list(self._packs.values())

    def ids(self) -> list[str]:
        return list(self._packs)

    def is_known_locale(self, tag: str) -> bool:
        """A locale is usable iff some registered pack declares it."""
        return any(p.supports_locale(tag) for p in self._packs.values())


def shipped_packs_dir() -> Path:
    return Path(str(resources.files(_PACKS_PACKAGE)))


@lru_cache(maxsize=1)
def default_registry() -> PackRegistry:
    """The packs shipped with the package (loaded and validated once)."""
    return PackRegistry.from_directory(shipped_packs_dir())


def default_pack() -> CurriculumPack:
    return default_registry().require(DEFAULT_PACK_ID)
