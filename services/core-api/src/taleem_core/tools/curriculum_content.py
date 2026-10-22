"""Read the *authored* lesson prose already in the Grade 4 design documents (verbatim, no fill).

Two kinds of section carry human-authored, ``authored-original`` lesson content:

- the exemplar section (``## 3. Exemplar lesson — ★ <code>``) of each subject document;
- each lesson section (``#### L<u>.<n> — <title> (<code>)``) of ``GRADE4_MATH_CURRICULUM.md`` §7.

This module extracts only the fields that map onto a Studio field without rewriting anything:

==========================  =======================================================================
Document field              Imported as
==========================  =======================================================================
Vocabulary                  ``vocabulary`` — each ``ur (en)`` / ``en = ur`` pair, split, not glossed
Worked example (script)     ``worked_examples`` — script lines verbatim (only fields labelled
                            *script*; an unlabelled "Worked example" is an author specification)
Hint ladder                 ``hints`` — only the quoted H1/H2 texts (H3 is a re-teach instruction)
Misconception(s)            ``common_misconceptions`` — the referenced rows of the doc's library
Homework                    ``homework`` — one short task, text verbatim
Parent note / Teacher note  ``parent_notes`` / ``mentor_notes``
==========================  =======================================================================

Text is split into Urdu and English only where the document itself writes both (``ur — en``,
``"ur" (en)``, ``ur (en)``). A side the document does not write stays empty — nothing is translated.
Every other field present in a section is listed in :attr:`AuthoredContent.not_imported` with the
reason, so the report shows the gap honestly.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .curriculum_spine import (
    _ARABIC_RE,
    _CODE,
    _EXEMPLAR_RE,
    _MATH_LESSON_RE,
    MATH_DOC,
    _cells,
    _clean,
    _is_separator,
    _section,
    split_bilingual,
)

_BULLET_RE = re.compile(r"^- \*\*(?P<label>.+?):\*\*\s*(?P<value>.*)$")
_SUB_BULLET_RE = re.compile(r"^\s{2,}- (?P<value>.+)$")
_HINT_RE = re.compile(r'H(?P<level>\d)\s+"(?P<text>[^"]+)"')
_REF_RE = re.compile(r"`(?P<ref>m-[a-z0-9-]+)`")
_TRAILING_ANNOTATION_RE = re.compile(r"\s*\*\([^)]*\)\*\s*$")
_QUOTED_GLOSS_RE = re.compile(r'^"(?P<ur>[^"]+)"\s*\((?P<en>[^()]*)\)\.?$')

# Fields that are spine metadata (already carried by the draft) — not "content gaps".
_SPINE_LABELS = (
    "learning outcome",
    "difficulty",
    "estimated duration",
    "prerequisites",
)
# Labels present in sections that have no faithful Studio target (reported, never guessed into one).
_NOT_IMPORTED_REASONS: dict[str, str] = {
    "examples / worked example": "authored in `vertical_slice/fractions_lesson.py` (imported)",
    "note": "a note to authors, no Studio field",
    "examples": "no Studio field for unworked examples",
    "worked example": "an author specification, not a student-facing script",
    "practice": "an item specification; the document gives no item wording or answer key",
    "assessment": "pool/mastery specification (metadata), no items",
    "revision triggers": "trigger specification; no Studio text field",
    "construct rule": "an authoring rule, no Studio field",
}


@dataclass(frozen=True)
class Bilingual:
    ur: str = ""
    en: str = ""

    def __bool__(self) -> bool:
        return bool(self.ur or self.en)


@dataclass(frozen=True)
class MisconceptionRow:
    ref: str
    misconception: Bilingual
    correction: Bilingual


@dataclass
class AuthoredContent:
    code: str
    source: str  # "<doc> §<section> <lesson>" — the provenance note for imported fields
    vocabulary: list[Bilingual] = field(default_factory=list)
    worked_example_steps: list[Bilingual] = field(default_factory=list)
    hints: list[tuple[str, Bilingual]] = field(default_factory=list)  # (level "H1", text)
    misconceptions: list[MisconceptionRow] = field(default_factory=list)
    homework: Bilingual = field(default_factory=Bilingual)
    parent_note: Bilingual = field(default_factory=Bilingual)
    teacher_note: Bilingual = field(default_factory=Bilingual)
    not_imported: list[tuple[str, str]] = field(default_factory=list)  # (field, reason)


# --------------------------------------------------------------------------------- text helpers


def _strip_quotes(text: str) -> str:
    t = text.strip()
    if len(t) >= 2 and t[0] == '"' and t[-1] == '"' and t.count('"') == 2:
        return t[1:-1].strip()
    return t


def bilingual(text: str) -> Bilingual:
    """Split document text into Urdu/English exactly as written; never translate."""
    t = _TRAILING_ANNOTATION_RE.sub("", _clean(text)).strip()
    m = _QUOTED_GLOSS_RE.match(t)
    if m and _ARABIC_RE.search(m.group("ur")) and not _ARABIC_RE.search(m.group("en")):
        return Bilingual(ur=m.group("ur").strip(), en=m.group("en").strip())
    t = _strip_quotes(t)
    if " — " in t:
        ur, en = t.split(" — ", 1)
        en = _strip_quotes(en)
        if _ARABIC_RE.search(ur) and en and not _ARABIC_RE.search(en):
            return Bilingual(ur=ur.strip(), en=en.strip())
    ur, en = split_bilingual(t)
    return Bilingual(ur=ur, en=en)


def _split_top_level(text: str) -> list[str]:
    """Split on commas that are not inside parentheses."""
    parts: list[str] = []
    depth = 0
    cur = ""
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return [p.strip().rstrip(".").strip() for p in parts if p.strip()]


def _vocabulary(value: str) -> list[Bilingual]:
    terms: list[Bilingual] = []
    for part in _split_top_level(_clean(value)):
        if " = " in part:  # English doc: "present = حال"
            en, ur = (s.strip() for s in part.split(" = ", 1))
            terms.append(Bilingual(ur=ur, en=en))
        else:
            ur, en = split_bilingual(part)
            terms.append(Bilingual(ur=ur, en=en))
    return terms


def _bullets(lines: Iterable[str]) -> list[tuple[str, str, list[str]]]:
    """``- **Label:** value`` bullets with wrapped continuation lines and ``  - `` sub-bullets."""
    out: list[tuple[str, str, list[str]]] = []
    for line in lines:
        bm = _BULLET_RE.match(line)
        if bm:
            label = re.sub(r"`[^`]*`", "", bm.group("label")).strip().lower()
            out.append((label, bm.group("value").strip(), []))
            continue
        if not out:
            continue
        sm = _SUB_BULLET_RE.match(line)
        if sm:
            out[-1][2].append(sm.group("value").strip())
        elif line.startswith("  ") and line.strip():
            label, value, subs = out[-1]
            if subs:
                subs[-1] = f"{subs[-1]} {line.strip()}"
            else:
                out[-1] = (label, f"{value} {line.strip()}", subs)
        elif not line.strip() or line.startswith("#"):
            continue
    return out


def _library(lines: Sequence[str]) -> dict[str, tuple[str, str]]:
    """The misconception library table: ref -> (misconception, correction) raw cells."""
    rows: dict[str, tuple[str, str]] = {}
    header: list[str] | None = None
    for line in lines:
        if not line.startswith("|"):
            header = None
            continue
        cells = _cells(line)
        if _is_separator(cells):
            continue
        if cells[0] == "Ref":
            header = [_clean(c).lower() for c in cells]
            continue
        if header is None or len(cells) != len(header):
            continue
        row = dict(zip(header, cells, strict=True))
        ref = _clean(row["ref"])
        correction = next(v for k, v in row.items() if k.startswith("correction"))
        rows[ref] = (row["misconception"], correction)
    return rows


# --------------------------------------------------------------------------------- extraction


def _content_from_bullets(
    code: str,
    source: str,
    bullets: Sequence[tuple[str, str, list[str]]],
    library: dict[str, tuple[str, str]],
) -> AuthoredContent:
    c = AuthoredContent(code=code, source=source)
    for label, value, subs in bullets:
        if label.startswith(_SPINE_LABELS):
            continue
        if label.startswith("vocabulary"):
            c.vocabulary = _vocabulary(value)
        elif label.startswith("worked example") and "script" in label:
            lines = subs or [value]
            c.worked_example_steps = [bilingual(s) for s in lines if s.strip()]
        elif label.startswith("hint ladder"):
            c.hints = [
                (f"H{m.group('level')}", bilingual(m.group("text")))
                for m in _HINT_RE.finditer(value)
            ]
            quoted = dict(c.hints)
            unquoted = [lvl for lvl in re.findall(r"H(\d)", value) if f"H{lvl}" not in quoted]
            if unquoted:
                levels = "H" + "/H".join(unquoted)
                reason = f"{levels} is a re-teach instruction, not hint text"
                c.not_imported.append(("hints", reason))
        elif label.startswith("misconception"):
            if "correction:" in value:
                c.not_imported.append(
                    (
                        "common_misconceptions",
                        "the section's inline correction is not the library row; the library row "
                        "is imported (the two are not translations of each other)",
                    )
                )
            for m in _REF_RE.finditer(value):
                ref = m.group("ref")
                if ref not in library:
                    c.not_imported.append(
                        ("common_misconceptions", f"`{ref}` is not in the document's library")
                    )
                    continue
                mis, corr = library[ref]
                c.misconceptions.append(MisconceptionRow(ref, bilingual(mis), bilingual(corr)))
            if not _REF_RE.search(value):
                c.not_imported.append(("common_misconceptions", "no library reference given"))
        elif label.startswith("homework"):
            c.homework = bilingual(value)
        elif label.startswith("parent note"):
            c.parent_note = bilingual(value)
        elif label.startswith("teacher note"):
            c.teacher_note = bilingual(value)
        else:
            key = next((k for k in _NOT_IMPORTED_REASONS if label.startswith(k)), "")
            reason = _NOT_IMPORTED_REASONS.get(key, "no matching Studio field")
            c.not_imported.append((label, reason))
    return c


def parse_subject_exemplars(path: str, text: str) -> list[AuthoredContent]:
    """The ★ exemplar section(s) of a subject document."""
    lines = text.splitlines()
    library = _library(_section(lines, 4))
    out: list[AuthoredContent] = []
    for i, line in enumerate(lines):
        m = _EXEMPLAR_RE.match(line)
        if not m:
            continue
        number = line.split(".", 1)[0].removeprefix("## ")
        body: list[str] = []
        for nxt in lines[i + 1 :]:
            if nxt.startswith("## ") or nxt.startswith("---"):
                break
            body.append(nxt)
        out.append(
            _content_from_bullets(
                m.group("code"), f"{path} §{number} (exemplar)", _bullets(body), library
            )
        )
    return out


def parse_math_lessons(text: str, path: str = MATH_DOC) -> list[AuthoredContent]:
    """Every lesson section of GRADE4_MATH_CURRICULUM.md §7."""
    lines = text.splitlines()
    library = _library(_section(lines, 4))
    out: list[AuthoredContent] = []
    current: tuple[str, str, list[str]] | None = None
    for line in _section(lines, 7) + ["### end"]:
        lm = _MATH_LESSON_RE.match(line)
        if lm or line.startswith("#"):
            if current is not None:
                code, lesson, body = current
                out.append(
                    _content_from_bullets(code, f"{path} §7 {lesson}", _bullets(body), library)
                )
                current = None
            if lm:
                num = re.match(r"^#### (?:★ )?(L\d+\.\d+)", line)
                current = (lm.group("code"), num.group(1) if num else "", [])
            continue
        if current is not None:
            current[2].append(line)
    return out


def parse_authored_content(docs: dict[str, str]) -> dict[str, AuthoredContent]:
    """``{objective code: AuthoredContent}`` over the given ``{path: markdown}`` documents."""
    found: dict[str, AuthoredContent] = {}
    for path in sorted(docs):
        if path == MATH_DOC:
            items = parse_math_lessons(docs[path], path)
        elif re.search(r"^## \d+\. Exemplar lesson", docs[path], re.MULTILINE):
            items = parse_subject_exemplars(path, docs[path])
        else:
            continue
        for item in items:
            if re.fullmatch(_CODE, item.code):
                found[item.code] = item
    return found


__all__ = [
    "AuthoredContent",
    "Bilingual",
    "MisconceptionRow",
    "bilingual",
    "parse_authored_content",
    "parse_math_lessons",
    "parse_subject_exemplars",
]
