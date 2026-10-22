"""Deterministic parser: Grade 4 curriculum design documents -> a structured objective spine.

The Grade 4 design documents (``curriculum/grade-4/*.md``, ``GRADE4_MATH_CURRICULUM.md`` and
``LESSON_CATALOG.md``) are *spines*: per objective they declare a code, a ``[RE-EXPRESSED]``
outcome, a difficulty band, a duration, prerequisites, a competency class and an assessment type.
This module reads exactly that — nothing is inferred, translated, or written that the documents do
not state.

Output is a :class:`Spine` (pure data, stdlib only) that serializes to a canonical JSON document
(``curriculum/grade-4/spine.json``). The same input always yields byte-identical JSON, so a
committed spine can be checked for staleness against the markdown.

Validation is strict and fails closed (:class:`SpineError`): every objective listed in a document's
domain map must appear in its unit tables (and vice versa), codes are unique, every prerequisite
resolves to a known objective, and the prerequisite graph is acyclic. Each document must declare its
content ``authored-original``; a declared ``Source:`` is carried into provenance so the Studio's
prohibited-source rule can refuse it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

GRADE_KEY = "G4"
SYSTEM_KEY = "PK-NCP"
SPINE_SCHEMA_VERSION = 1
GENERATOR = "taleem_core.tools.curriculum_ingest"

# Repository-relative source documents, in canonical (output) order.
SUBJECT_DOCS: tuple[str, ...] = (
    "curriculum/grade-4/URDU.md",
    "curriculum/grade-4/ENGLISH.md",
    "curriculum/grade-4/GENERAL_SCIENCE.md",
    "curriculum/grade-4/SOCIAL_STUDIES.md",
    "curriculum/grade-4/ISLAMIAT_ETHICS.md",
)
MATH_DOC = "GRADE4_MATH_CURRICULUM.md"
MATH_CATALOG = "LESSON_CATALOG.md"
PACKAGE_DOC = "curriculum/grade-4/GRADE4_PACKAGE.md"
# GRADE4_PACKAGE.md §2 subject names -> objective prefixes (Islamiat / Ethics is "16 / 16").
PACKAGE_SUBJECTS: dict[str, tuple[str, ...]] = {
    "Mathematics": ("MATH",),
    "Urdu": ("URD",),
    "English": ("ENG",),
    "General Science": ("SCI",),
    "Social Studies": ("SOC",),
    "Islamiat / Ethics": ("ISL", "ETH"),
}
SPINE_PATH = "curriculum/grade-4/spine.json"
REPORT_PATH = "curriculum/grade-4/INGESTION_REPORT.md"

# Objective-code prefix -> (Studio subject key, religious-education track or "", display name).
# Subject keys are the Studio's SUBJECT_ROSTER keys for G4; ISL/ETH are two tracks of one subject.
PREFIXES: dict[str, tuple[str, str, str]] = {
    "MATH": ("math", "", "Mathematics"),
    "URD": ("urdu", "", "Urdu"),
    "ENG": ("english", "", "English"),
    "SCI": ("science", "", "General Science"),
    "SOC": ("social_studies", "", "Social Studies"),
    "ISL": ("islamiat_ethics", "islamiat", "Islamiat"),
    "ETH": ("islamiat_ethics", "ethics", "Ethics / Akhlaqiat"),
}
PREFIX_ORDER: tuple[str, ...] = tuple(PREFIXES)

# The documents' difficulty bands -> the Studio ``Difficulty`` enum values. The documents say they
# use "the existing Difficulty enum (INTRO, CORE, STRETCH)"; the code's enum is
# intro/developing/secure/challenge, so the mapping is explicit and both values are kept.
DIFFICULTY_MAP: dict[str, str] = {"INTRO": "intro", "CORE": "developing", "STRETCH": "challenge"}
COMPETENCY_MAP: dict[str, str] = {
    "K": "knowledge",
    "C": "comprehension",
    "A": "application",
    "An": "analysis",
}

AUTHORED_ORIGINAL = "authored-original"

_CODE = r"[A-Z]{3,4}-G4-[A-Z]{2,3}-\d{2}"
_CODE_RE = re.compile(rf"^{_CODE}$")
_RANGE_SEP = r"\s*(?:…|\.\.\.)\s*"
# "ENG-G4-RD-01 … 05" (domain map) — first code + last two-digit number.
_DOMAIN_RANGE_RE = re.compile(
    rf"(?P<stem>[A-Z]{{3,4}}-G4-[A-Z]{{2,3}})-(?P<a>\d{{2}}){_RANGE_SEP}(?P<b>\d{{2}})"
)
# A prerequisite token: optional "<PREFIX>-G4-", a domain tag, a number, optional "…NN" range end.
_PREREQ_TOKEN_RE = re.compile(
    rf"(?:(?P<prefix>[A-Z]{{3,4}})-G4-)?(?P<tag>[A-Z]{{2,3}})-(?P<a>\d{{2}})"
    rf"(?:{_RANGE_SEP}(?P<b>\d{{2}}))?"
)
_UNIT_HEADING_RE = re.compile(r"^### Unit (?P<key>U\d+)\s+—\s+(?P<title>.+?)\s*$")
_MATH_UNIT_RE = re.compile(r"^### Unit (?P<n>\d+)\s+—\s+(?P<title>.+?)\s*$")
_MATH_LESSON_RE = re.compile(
    rf"^#### (?P<star>★ )?L\d+\.\d+ — (?P<title>.+?) \((?P<code>{_CODE})\)(?P<rest>.*)$"
)
_FIELD_RE = re.compile(r"^- \*\*(?P<label>.+?):\*\*\s*(?P<value>.*)$")
_EXEMPLAR_RE = re.compile(rf"^## \d+\. Exemplar lesson — (?:★ )?(?P<code>{_CODE})")
_SOURCE_RE = re.compile(r"^Source:\s*(?P<src>.+?)\s*$", re.MULTILINE)
_ARABIC_RE = re.compile(r"[؀-ۿ]")
_NO_PREREQ = ("—", "-", "", "none")


class SpineError(ValueError):
    """The design documents are internally inconsistent (fails closed; nothing is ingested)."""

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(self.problems))


# --------------------------------------------------------------------------------- data model


@dataclass(frozen=True)
class SourceProvenance:
    """What a source document declares about the provenance of its content."""

    path: str
    derivation: str  # "authored-original" when the document declares it, else ""
    source: str = "authored"  # an explicit ``Source:`` line, if the document has one


@dataclass(frozen=True)
class Objective:
    code: str
    prefix: str
    subject_key: str
    track: str
    domain: str
    unit: str  # unit key, e.g. "ENG-G4-U1"
    topic: str  # unit + domain, e.g. "ENG-G4-U1-RD"
    outcome: str  # the document's [RE-EXPRESSED] outcome, verbatim (markup stripped)
    difficulty: str  # the document's band: INTRO | CORE | STRETCH
    studio_difficulty: str  # mapped Studio Difficulty value
    competency: str  # Studio Competency value ("" when the document gives none)
    duration_min: int
    prerequisites: tuple[str, ...]
    external_prerequisites: tuple[str, ...]
    assessment: str
    mentor_mediated: bool
    exemplar: bool
    lesson_id: str
    title_en: str
    title_ur: str
    source: str


@dataclass(frozen=True)
class Topic:
    key: str
    title: str


@dataclass(frozen=True)
class Unit:
    key: str
    title: str
    topics: tuple[Topic, ...]
    objectives: tuple[str, ...]


@dataclass(frozen=True)
class Track:
    prefix: str
    subject_key: str
    track: str
    title: str
    source: str
    units: tuple[Unit, ...]


@dataclass
class Spine:
    tracks: list[Track]
    objectives: list[Objective]
    provenance: list[SourceProvenance]
    notes: list[str] = field(default_factory=list)

    # -- queries --------------------------------------------------------------------------

    def by_code(self) -> dict[str, Objective]:
        return {o.code: o for o in self.objectives}

    def counts_by_prefix(self) -> dict[str, int]:
        counts = dict.fromkeys(PREFIX_ORDER, 0)
        for o in self.objectives:
            counts[o.prefix] += 1
        return counts

    def counts_by_subject(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for o in self.objectives:
            counts[o.subject_key] = counts.get(o.subject_key, 0) + 1
        return counts

    def provenance_for(self, source: str) -> SourceProvenance:
        for p in self.provenance:
            if p.path == source:
                return p
        raise KeyError(source)

    # -- serialization --------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        order = topological_order(self.objectives)
        edges = sum(len(o.prerequisites) for o in self.objectives)
        return {
            "schema_version": SPINE_SCHEMA_VERSION,
            "generated_by": GENERATOR,
            "notice": (
                "GENERATED from the Grade 4 design documents - do not edit. Regenerate with "
                "`python -m taleem_core.tools.curriculum_ingest --dry-run`; "
                "`--check` fails when this file is stale."
            ),
            "system": SYSTEM_KEY,
            "grade": GRADE_KEY,
            "difficulty_mapping": DIFFICULTY_MAP,
            "sources": [asdict(p) for p in self.provenance],
            "counts": {
                "objectives": len(self.objectives),
                "by_prefix": self.counts_by_prefix(),
                "by_subject": self.counts_by_subject(),
            },
            "hierarchy": {
                "grade": GRADE_KEY,
                "subjects": _hierarchy(self.tracks),
            },
            "objectives": [_objective_dict(o) for o in self.objectives],
            "prerequisite_dag": {
                "edges": edges,
                "roots": [o.code for o in self.objectives if not o.prerequisites],
                "topological_order": order,
            },
            "notes": list(self.notes),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"


def _objective_dict(o: Objective) -> dict[str, Any]:
    d = asdict(o)
    d["prerequisites"] = list(o.prerequisites)
    d["external_prerequisites"] = list(o.external_prerequisites)
    return d


def _hierarchy(tracks: Iterable[Track]) -> list[dict[str, Any]]:
    subjects: dict[str, dict[str, Any]] = {}
    for t in tracks:
        subj = subjects.setdefault(
            t.subject_key, {"key": t.subject_key, "tracks": [], "chapters": []}
        )
        subj["tracks"].append({"prefix": t.prefix, "track": t.track, "title": t.title})
        for u in t.units:
            subj["chapters"].append(
                {
                    "key": u.key,
                    "title": u.title,
                    "topics": [{"key": tp.key, "title": tp.title} for tp in u.topics],
                    "objectives": list(u.objectives),
                }
            )
    return list(subjects.values())


# --------------------------------------------------------------------------------- helpers


def _clean(cell: str) -> str:
    """Strip inline markdown emphasis/code markers; collapse whitespace."""
    s = cell.replace("**", "").replace("`", "")
    return " ".join(s.split())


def _cells(line: str) -> list[str]:
    inner = line.strip()
    if inner.startswith("|"):
        inner = inner[1:]
    if inner.endswith("|"):
        inner = inner[:-1]
    return [c.strip() for c in inner.split("|")]


def _is_separator(cells: Sequence[str]) -> bool:
    return all(re.fullmatch(r":?-{3,}:?", c) for c in cells if c)


def split_bilingual(raw: str) -> tuple[str, str]:
    """Split a heading like ``"اردو متن (English)"`` or ``"اردو — English"`` into (ur, en).

    Text without Urdu script is English only. Nothing is translated: a side that the document does
    not state is returned empty.
    """
    text = _clean(raw)
    if not _ARABIC_RE.search(text):
        return "", text
    m = re.fullmatch(r"(?P<ur>.+?)\s+\((?P<en>[^()]*[A-Za-z][^()]*)\)", text)
    if m and not _ARABIC_RE.search(m.group("en")):
        return m.group("ur").strip(), m.group("en").strip()
    if " — " in text:
        ur, en = text.split(" — ", 1)
        if _ARABIC_RE.search(ur) and not _ARABIC_RE.search(en):
            return ur.strip(), en.strip()
    if " / " in text:
        ur, en = text.split(" / ", 1)
        if _ARABIC_RE.search(ur) and not _ARABIC_RE.search(en):
            return ur.strip(), en.strip()
    return text, ""


def _declared_provenance(path: str, text: str) -> SourceProvenance:
    derivation = AUTHORED_ORIGINAL if f"`{AUTHORED_ORIGINAL}`" in text else ""
    m = _SOURCE_RE.search(text)
    return SourceProvenance(
        path=path, derivation=derivation, source=m.group("src") if m else "authored"
    )


def _section(lines: Sequence[str], number: int) -> list[str]:
    """Lines of top-level section ``## <number>.`` (up to the next ``## `` heading)."""
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith("## "):
            if inside:
                break
            inside = bool(re.match(rf"^## {number}\.", line))
            continue
        if inside:
            out.append(line)
    return out


_DomainRow = tuple[str, str, list[str]]  # (tag, display name, codes)


def _parse_domain_map(lines: Iterable[str], problems: list[str]) -> dict[str, list[_DomainRow]]:
    """Read domain-map rows ``| name | `TAG` | PFX-G4-TAG-01 … 05 |``.

    Returns ``{prefix: [(tag, name, codes)]}``.
    """
    result: dict[str, list[_DomainRow]] = {}
    for line in lines:
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        if len(cells) != 3 or _is_separator(cells):
            continue
        tag_m = re.fullmatch(r"`(?P<tag>[A-Z]{2,3})`", cells[1])
        rng = _DOMAIN_RANGE_RE.search(cells[2])
        if not tag_m or not rng:
            continue
        stem = rng.group("stem")
        prefix = stem.split("-", 1)[0]
        if not stem.endswith("-" + tag_m.group("tag")):
            problems.append(f"domain map row tag `{tag_m.group('tag')}` does not match {stem}")
        a, b = int(rng.group("a")), int(rng.group("b"))
        codes = [f"{stem}-{n:02d}" for n in range(a, b + 1)]
        result.setdefault(prefix, []).append((tag_m.group("tag"), _clean(cells[0]), codes))
    return result


def _expand_prereqs(
    raw: str, prefix: str, problems: list[str], where: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Resolve a prerequisite cell into (objective codes, external prerequisite notes)."""
    text = _clean(raw)
    if text.lower().split(" ", 1)[0].rstrip(".,;") in _NO_PREREQ:
        return (), ()
    codes: list[str] = []
    for m in _PREREQ_TOKEN_RE.finditer(text):
        pfx = m.group("prefix") or prefix
        a = int(m.group("a"))
        b = int(m.group("b")) if m.group("b") else a
        if b < a:
            problems.append(f"{where}: descending prerequisite range {m.group(0)!r}")
        for n in range(a, b + 1):
            code = f"{pfx}-G4-{m.group('tag')}-{n:02d}"
            if code not in codes:
                codes.append(code)
    if codes:
        return tuple(codes), ()
    return (), (text,)


# --------------------------------------------------------------------------------- subject docs


def parse_subject_doc(path: str, text: str) -> tuple[list[Track], list[Objective], list[str]]:
    """Parse one subject design document (Urdu/English/Science/Social Studies/Islamiat-Ethics)."""
    problems: list[str] = []
    notes: list[str] = []
    lines = text.splitlines()
    domains = _parse_domain_map(_section(lines, 1), problems)
    if not domains:
        raise SpineError([f"{path}: no domain map (§1) found"])

    unit_key: str | None = None
    unit_title = ""
    header: list[str] | None = None
    # prefix -> ordered unit key -> (title, [objective])
    per_track: dict[str, dict[str, tuple[str, list[Objective]]]] = {p: {} for p in domains}
    objectives: list[Objective] = []
    with_prereq_column: set[str] = set()
    for line in _section(lines, 2):
        if line.startswith("### "):
            m = _UNIT_HEADING_RE.match(line)
            unit_key, unit_title = (m.group("key"), m.group("title")) if m else (None, "")
            header = None
            continue
        if not line.startswith("|"):
            header = None
            continue
        cells = _cells(line)
        if _is_separator(cells):
            continue
        if cells and cells[0] == "Objective":
            header = [_clean(c).lower() for c in cells]
            if any(h.startswith("prereq") for h in header):
                with_prereq_column.update(domains)
            continue
        if header is None:
            continue
        row = dict(zip(header, cells, strict=False))
        if len(cells) != len(header):
            problems.append(f"{path}: row has {len(cells)} cells, header has {len(header)}: {line}")
            continue
        obj_cell = _clean(row["objective"])
        exemplar = obj_cell.startswith("★")
        code = obj_cell.lstrip("★ ").strip()
        if not _CODE_RE.match(code):
            problems.append(f"{path}: malformed objective code {code!r}")
            continue
        prefix, _g, tag, _n = code.split("-")
        if prefix not in PREFIXES:
            problems.append(f"{path}: unknown objective prefix {prefix!r} in {code}")
            continue
        subject_key, track, _name = PREFIXES[prefix]
        domain_list = domains.get(prefix, [])
        domain_tags = [d[0] for d in domain_list]
        if tag not in domain_tags:
            problems.append(f"{path}: {code} uses domain `{tag}` absent from the domain map")
            continue
        if unit_key is not None:
            u_key, u_title = f"{prefix}-G4-{unit_key}", _clean(unit_title)
        else:
            # No unit headings (Islamiat/Ethics): each domain is one unit, in domain-map order.
            idx = domain_tags.index(tag)
            u_key, u_title = f"{prefix}-G4-U{idx + 1}", domain_list[idx][1]
        outcome_col = next((h for h in header if "outcome" in h), "")
        prereq_col = next((h for h in header if h.startswith("prereq")), "")
        diff = _clean(row.get("diff", ""))
        comp = _clean(row.get("comp", ""))
        if diff not in DIFFICULTY_MAP:
            problems.append(f"{path}: {code} has unknown difficulty {diff!r}")
            continue
        if comp not in COMPETENCY_MAP:
            problems.append(f"{path}: {code} has unknown competency {comp!r}")
            continue
        try:
            duration = int(_clean(row.get("dur", "")))
        except ValueError:
            problems.append(f"{path}: {code} has a non-integer duration {row.get('dur')!r}")
            continue
        prereqs, external = (
            _expand_prereqs(row[prereq_col], prefix, problems, f"{path}: {code}")
            if prereq_col
            else ((), ())
        )
        assessment = _clean(row.get("assess", ""))
        outcome = _clean(row.get(outcome_col, ""))
        obj = Objective(
            code=code,
            prefix=prefix,
            subject_key=subject_key,
            track=track,
            domain=tag,
            unit=u_key,
            topic=f"{u_key}-{tag}",
            outcome=outcome,
            difficulty=diff,
            studio_difficulty=DIFFICULTY_MAP[diff],
            competency=COMPETENCY_MAP[comp],
            duration_min=duration,
            prerequisites=prereqs,
            external_prerequisites=external,
            assessment=assessment,
            mentor_mediated="mentor" in assessment.lower(),
            exemplar=exemplar,
            lesson_id=f"L-{code.lower()}",
            title_en=outcome,
            title_ur="",
            source=path,
        )
        objectives.append(obj)
        per_track[prefix].setdefault(u_key, (u_title, []))[1].append(obj)

    # Every domain-map code must be in a unit table and vice versa.
    for prefix, dl in domains.items():
        declared = {c for _t, _n, codes in dl for c in codes}
        found = {o.code for o in objectives if o.prefix == prefix}
        for missing in sorted(declared - found):
            problems.append(f"{path}: {missing} is in the domain map but has no unit-table row")
        for extra in sorted(found - declared):
            problems.append(f"{path}: {extra} has a unit-table row but is not in the domain map")
        if prefix not in with_prereq_column and found:
            notes.append(
                f"`{path}`: the `{prefix}-G4-*` tables declare no prerequisites column, so those "
                "objectives have no prerequisite edges (the package claims a per-subject DAG)."
            )

    # Exemplar sections vs the ★ marks in the tables.
    starred = {o.code for o in objectives if o.exemplar}
    for line in lines:
        m = _EXEMPLAR_RE.match(line)
        if m and m.group("code") not in starred:
            notes.append(
                f"`{path}`: the exemplar section is headed ★ `{m.group('code')}`, but that "
                "objective is not marked ★ in its unit table."
            )

    if problems:
        raise SpineError(problems)
    tracks = [
        Track(
            prefix=prefix,
            subject_key=PREFIXES[prefix][0],
            track=PREFIXES[prefix][1],
            title=PREFIXES[prefix][2],
            source=path,
            units=tuple(
                _unit(k, title, objs, domains[prefix]) for k, (title, objs) in units.items()
            ),
        )
        for prefix, units in per_track.items()
    ]
    return tracks, objectives, notes


def _unit(key: str, title: str, objs: Sequence[Objective], domains: Sequence[_DomainRow]) -> Unit:
    names = {tag: name for tag, name, _codes in domains}
    topics: dict[str, Topic] = {}
    for o in objs:
        topics.setdefault(o.topic, Topic(key=o.topic, title=names.get(o.domain, o.domain)))
    return Unit(
        key=key,
        title=title,
        topics=tuple(topics.values()),
        objectives=tuple(o.code for o in objs),
    )


# --------------------------------------------------------------------------------- mathematics


@dataclass(frozen=True)
class _CatalogRow:
    lesson_id: str
    unit: str
    code: str
    title_ur: str
    title_en: str
    difficulty: str
    competency: str
    duration_min: int
    prerequisites: tuple[str, ...]
    items: int


def parse_math_catalog(path: str, text: str) -> dict[str, _CatalogRow]:
    problems: list[str] = []
    rows: dict[str, _CatalogRow] = {}
    header: list[str] | None = None
    for line in _section(text.splitlines(), 1):
        if not line.startswith("|"):
            continue
        cells = _cells(line)
        if _is_separator(cells):
            continue
        if cells[0] == "lesson_id":
            header = [_clean(c).lower() for c in cells]
            continue
        if header is None or len(cells) != len(header):
            problems.append(f"{path}: malformed catalog row: {line}")
            continue
        row = dict(zip(header, cells, strict=True))
        code = _clean(row["objective"])
        title = _clean(row["title (ur / en)"]).replace("(LIVE)", "").strip()
        ur, en = split_bilingual(title)
        prereqs, _external = _expand_prereqs(row["prereqs"], "MATH", problems, f"{path}: {code}")
        try:
            duration, items = int(_clean(row["dur (min)"])), int(_clean(row["items"]))
        except ValueError:
            problems.append(f"{path}: {code} has a non-integer duration/items")
            continue
        if code in rows:
            problems.append(f"{path}: duplicate catalog objective {code}")
        rows[code] = _CatalogRow(
            lesson_id=_clean(row["lesson_id"]),
            unit=_clean(row["unit"]),
            code=code,
            title_ur=ur,
            title_en=en,
            difficulty=_clean(row["diff"]),
            competency=_clean(row["comp"]),
            duration_min=duration,
            prerequisites=prereqs,
            items=items,
        )
    if problems:
        raise SpineError(problems)
    return rows


def parse_math_doc(
    path: str, text: str, catalog_path: str, catalog: Mapping[str, _CatalogRow]
) -> tuple[list[Track], list[Objective], list[str]]:
    """Parse GRADE4_MATH_CURRICULUM.md §7 and cross-check every field against LESSON_CATALOG.md."""
    problems: list[str] = []
    notes: list[str] = []
    lines = text.splitlines()
    domains = _parse_domain_map(_section(lines, 2), problems).get("MATH", [])
    if not domains:
        raise SpineError([f"{path}: no MATH domain map (§2) found"])

    # (unit number, title, starred, code, fields)
    lessons: list[tuple[str, str, bool, str, dict[str, str]]] = []
    unit_n = ""
    unit_titles: dict[str, str] = {}
    current: dict[str, str] | None = None
    last_label = ""
    for line in _section(lines, 7):
        um = _MATH_UNIT_RE.match(line)
        if um:
            unit_n = um.group("n")
            unit_titles[unit_n] = _clean(um.group("title"))
            current = None
            continue
        lm = _MATH_LESSON_RE.match(line)
        if lm:
            current = {}
            title, code = _clean(lm.group("title")), lm.group("code")
            lessons.append((unit_n, title, bool(lm.group("star")), code, current))
            if "EXISTING" in lm.group("rest"):
                notes.append(
                    f"`{path}`: `{code}` is marked EXISTING; its authored content lives in "
                    "`vertical_slice/fractions_lesson.py` (a test fixture). The ingest builds a "
                    "spine draft only and does not copy that fixture."
                )
            last_label = ""
            continue
        if line.startswith("#"):
            current = None
            continue
        if current is None:
            continue
        fm = _FIELD_RE.match(line)
        if fm:
            label = re.sub(r"`[^`]*`", "", fm.group("label")).strip().lower()
            last_label = label
            current[label] = fm.group("value").strip()
        elif line.startswith("  ") and last_label and not line.lstrip().startswith("- "):
            current[last_label] = f"{current[last_label]} {line.strip()}"
        elif not line.startswith("  "):
            last_label = ""

    domain_tags = [d[0] for d in domains]
    objectives: list[Objective] = []
    units: dict[str, tuple[str, list[Objective]]] = {}
    for unit_no, _title, star, code, fields in lessons:
        where = f"{path}: {code}"
        tag = code.split("-")[2]
        if tag not in domain_tags:
            problems.append(f"{where} uses domain `{tag}` absent from the domain map")
            continue
        outcome = _clean(fields.get("learning outcome", ""))
        diff = _clean(fields.get("difficulty", ""))
        dur_m = re.match(r"(\d+)\s*min", _clean(fields.get("estimated duration", "")))
        assessment = next((_clean(v) for k, v in fields.items() if k.startswith("assessment")), "")
        if not outcome:
            problems.append(f"{where} has no learning outcome")
        if diff not in DIFFICULTY_MAP:
            problems.append(f"{where} has unknown difficulty {diff!r}")
            continue
        if dur_m is None:
            problems.append(f"{where} has no estimated duration")
            continue
        prereq_text = fields.get("prerequisites", "")
        prereqs, external = _expand_prereqs(prereq_text, "MATH", problems, where)
        cat = catalog.get(code)
        if cat is None:
            problems.append(f"{where} is missing from {catalog_path}")
            continue
        duration = int(dur_m.group(1))
        unit_key = f"MATH-G4-U{unit_no}"
        # Cross-check the two math documents; any disagreement is a hard error.
        if cat.unit != f"U{unit_no}":
            problems.append(f"{where}: unit U{unit_no} but catalog says {cat.unit}")
        if cat.difficulty != diff:
            problems.append(f"{where}: difficulty {diff} but catalog says {cat.difficulty}")
        if cat.duration_min != duration:
            problems.append(f"{where}: duration {duration} but catalog says {cat.duration_min}")
        if tuple(sorted(cat.prerequisites)) != tuple(sorted(prereqs)):
            problems.append(
                f"{where}: prerequisites {list(prereqs)} but catalog says {list(cat.prerequisites)}"
            )
        if cat.competency not in COMPETENCY_MAP:
            problems.append(f"{catalog_path}: {code} has unknown competency {cat.competency!r}")
            continue
        obj = Objective(
            code=code,
            prefix="MATH",
            subject_key="math",
            track="",
            domain=tag,
            unit=unit_key,
            topic=f"{unit_key}-{tag}",
            outcome=outcome,
            difficulty=diff,
            studio_difficulty=DIFFICULTY_MAP[diff],
            competency=COMPETENCY_MAP[cat.competency],
            duration_min=duration,
            prerequisites=prereqs,
            external_prerequisites=external,
            assessment=assessment or f"formative; {cat.items}-item pool",
            mentor_mediated="mentor" in assessment.lower(),
            exemplar=star,
            lesson_id=cat.lesson_id,
            title_en=cat.title_en,
            title_ur=cat.title_ur,
            source=path,
        )
        objectives.append(obj)
        units.setdefault(unit_key, (unit_titles.get(unit_no, ""), []))[1].append(obj)

    declared = {c for _t, _n, codes in domains for c in codes}
    found = {o.code for o in objectives}
    for missing in sorted(declared - found):
        problems.append(f"{path}: {missing} is in the domain map but has no lesson section")
    for extra in sorted(found - declared):
        problems.append(f"{path}: {extra} has a lesson section but is not in the domain map")
    for orphan in sorted(set(catalog) - found):
        problems.append(f"{catalog_path}: {orphan} has no lesson section in {path}")
    if problems:
        raise SpineError(problems)
    track = Track(
        prefix="MATH",
        subject_key="math",
        track="",
        title=PREFIXES["MATH"][2],
        source=path,
        units=tuple(_unit(k, t, objs, domains) for k, (t, objs) in units.items()),
    )
    return [track], objectives, notes


# --------------------------------------------------------------------------------- package


def check_package(
    path: str, text: str, tracks: Sequence[Track], objectives: Sequence[Objective]
) -> tuple[list[str], list[str]]:
    """Cross-check GRADE4_PACKAGE.md §2 "at a glance" against the parsed subject documents.

    Objective counts must agree (hard error). Unit/domain counts that disagree are notes: the
    package counts revision-only units that have no objective rows.
    """
    problems: list[str] = []
    notes: list[str] = []
    counts: dict[str, int] = dict.fromkeys(PREFIX_ORDER, 0)
    for o in objectives:
        counts[o.prefix] += 1
    units = {t.prefix: len(t.units) for t in tracks}
    seen: set[str] = set()
    for line in _section(text.splitlines(), 2):
        if not line.startswith("|"):
            continue
        cells = [_clean(c) for c in _cells(line)]
        if len(cells) < 4 or cells[0] not in PACKAGE_SUBJECTS:
            continue
        prefixes = PACKAGE_SUBJECTS[cells[0]]
        seen.add(cells[0])
        declared = [int(n) for n in re.findall(r"\d+", cells[2])]
        if len(declared) != len(prefixes):
            problems.append(f"{path}: cannot read the objective count for {cells[0]!r}")
            continue
        for prefix, n in zip(prefixes, declared, strict=True):
            if counts[prefix] != n:
                problems.append(
                    f"{path}: declares {n} {prefix}-G4 objectives; the subject document has "
                    f"{counts[prefix]}"
                )
        m = re.match(r"(\d+)", cells[3])
        for prefix in prefixes:
            if m and units.get(prefix, 0) != int(m.group(1)):
                notes.append(
                    f"`{path}`: declares {m.group(1)} teaching units for {cells[0]}; the "
                    f"`{prefix}-G4-*` tables group objectives into {units.get(prefix, 0)}."
                )
    for missing in sorted(set(PACKAGE_SUBJECTS) - seen):
        problems.append(f"{path}: §2 has no row for {missing!r}")
    return problems, notes


# --------------------------------------------------------------------------------- DAG


def validate_dag(objectives: Sequence[Objective]) -> list[str]:
    """Return DAG problems: duplicate codes, dangling prerequisites, self-loops, and cycles."""
    problems: list[str] = []
    codes: dict[str, Objective] = {}
    for o in objectives:
        if o.code in codes:
            first = codes[o.code].source
            problems.append(f"duplicate objective code {o.code} ({first}, {o.source})")
        codes[o.code] = o
    for o in objectives:
        for p in o.prerequisites:
            if p == o.code:
                problems.append(f"{o.code} lists itself as a prerequisite")
            elif p not in codes:
                problems.append(f"{o.code} ({o.source}): prerequisite {p} does not resolve")
    if problems:
        return problems
    # Iterative DFS cycle detection (white/grey/black), deterministic order.
    state: dict[str, int] = dict.fromkeys(codes, 0)
    for start in codes:
        if state[start]:
            continue
        stack: list[tuple[str, int]] = [(start, 0)]
        path: list[str] = [start]
        state[start] = 1
        while stack:
            node, idx = stack[-1]
            prereqs = codes[node].prerequisites
            if idx < len(prereqs):
                stack[-1] = (node, idx + 1)
                nxt = prereqs[idx]
                if state[nxt] == 1:
                    cycle = path[path.index(nxt) :] + [nxt]
                    problems.append("prerequisite cycle: " + " -> ".join(cycle))
                    return problems
                if state[nxt] == 0:
                    state[nxt] = 1
                    stack.append((nxt, 0))
                    path.append(nxt)
            else:
                state[node] = 2
                stack.pop()
                path.pop()
    return problems


def topological_order(objectives: Sequence[Objective]) -> list[str]:
    """Kahn's algorithm, ties broken by document order (prerequisites before dependants)."""
    position = {o.code: i for i, o in enumerate(objectives)}
    remaining = {o.code: set(o.prerequisites) for o in objectives}
    order: list[str] = []
    while remaining:
        ready = sorted((c for c, deps in remaining.items() if not deps), key=position.__getitem__)
        if not ready:
            raise SpineError(["prerequisite cycle (topological sort did not converge)"])
        nxt = ready[0]
        order.append(nxt)
        del remaining[nxt]
        for deps in remaining.values():
            deps.discard(nxt)
    return order


# --------------------------------------------------------------------------------- entrypoint


def build_spine(docs: Mapping[str, str]) -> Spine:
    """Build a validated spine from ``{repo-relative path: markdown text}``.

    ``docs`` must contain :data:`MATH_DOC`, :data:`MATH_CATALOG` and any subject documents. Raises
    :class:`SpineError` on any inconsistency (nothing partial is returned).
    """
    problems: list[str] = []
    tracks: list[Track] = []
    objectives: list[Objective] = []
    notes: list[str] = [
        "Difficulty: the documents state they use the existing `Difficulty` enum "
        "(`INTRO`/`CORE`/`STRETCH`); the Studio enum is `intro`/`developing`/`secure`/`challenge`. "
        "The ingest maps INTRO->intro, CORE->developing, STRETCH->challenge and keeps both values."
    ]
    provenance: list[SourceProvenance] = []
    for path in sorted(docs):
        prov = _declared_provenance(path, docs[path])
        provenance.append(prov)
        if prov.derivation != AUTHORED_ORIGINAL:
            problems.append(f"{path}: does not declare its content `{AUTHORED_ORIGINAL}`")
    if problems:
        raise SpineError(problems)

    if MATH_DOC in docs:
        if MATH_CATALOG not in docs:
            raise SpineError([f"{MATH_DOC} requires {MATH_CATALOG} for cross-checking"])
        catalog = parse_math_catalog(MATH_CATALOG, docs[MATH_CATALOG])
        t, o, n = parse_math_doc(MATH_DOC, docs[MATH_DOC], MATH_CATALOG, catalog)
        tracks += t
        objectives += o
        notes += n
    for path in sorted(p for p in docs if p not in (MATH_DOC, MATH_CATALOG, PACKAGE_DOC)):
        try:
            t, o, n = parse_subject_doc(path, docs[path])
        except SpineError as exc:
            problems += exc.problems
            continue
        tracks += t
        objectives += o
        notes += n
    if PACKAGE_DOC in docs and not problems:
        pkg_problems, pkg_notes = check_package(PACKAGE_DOC, docs[PACKAGE_DOC], tracks, objectives)
        problems += pkg_problems
        notes += pkg_notes
    problems += validate_dag(objectives)
    seen_ids: dict[str, str] = {}
    for obj in objectives:
        if obj.lesson_id in seen_ids:
            problems.append(
                f"lesson_id {obj.lesson_id} used by {seen_ids[obj.lesson_id]} and {obj.code}"
            )
        seen_ids[obj.lesson_id] = obj.code
    if problems:
        raise SpineError(problems)

    rank = {p: i for i, p in enumerate(PREFIX_ORDER)}
    tracks.sort(key=lambda t: rank[t.prefix])
    order = {o.code: i for i, o in enumerate(objectives)}
    objectives.sort(key=lambda o: (rank[o.prefix], order[o.code]))
    return Spine(tracks=tracks, objectives=objectives, provenance=provenance, notes=notes)


def default_sources() -> tuple[str, ...]:
    return (MATH_DOC, MATH_CATALOG, PACKAGE_DOC, *SUBJECT_DOCS)


def read_docs(root: Path, sources: Iterable[str] | None = None) -> dict[str, str]:
    return {p: (root / p).read_text(encoding="utf-8") for p in (sources or default_sources())}


def load_spine(root: Path) -> Spine:
    return build_spine(read_docs(root))


__all__ = [
    "GRADE_KEY",
    "REPORT_PATH",
    "SPINE_PATH",
    "Objective",
    "Spine",
    "SpineError",
    "Track",
    "build_spine",
    "load_spine",
    "read_docs",
    "split_bilingual",
    "topological_order",
    "validate_dag",
]
