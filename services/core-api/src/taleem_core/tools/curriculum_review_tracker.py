"""Grade 4 review tracker: generated from the AI draft files, so it cannot drift from them.

Reads ``curriculum/grade-4/spine.json`` and every ``curriculum/grade-4/ai-drafts/*.json`` and
writes two files into ``curriculum/grade-4/review/``:

- ``REVIEW_TRACKER.md``: per subject, unit and objective, the status, the open ``review_flags``
  (counted and routed to the Studio review stage that should resolve them), the extra sign-offs
  (scholar, safeguarding) and the data problems found in the drafts.
- ``review_flags.csv``: one row per flag with empty reviewer / decision / date columns, for a
  review team to load into a sheet.

Both files start with the banner ``AI-GENERATED DRAFT — NOT REVIEWED — NOT OFFICIAL CURRICULUM``.

The tracker only describes the draft files. It never reads the Studio database and never records a
review: every objective's status is ``ai-draft-unreviewed`` because the draft format has no place
for a review result. Real review state lives in the Studio workflow (``domain/workflow.py``).

Flag routing is a deterministic keyword rule over the flag's text (most flags start with the
reviewer they need, e.g. ``"language editor: ..."``). It is a triage aid; the flag text itself is
what the reviewer must act on.

Usage (from ``services/core-api``)::

    python -m taleem_core.tools.curriculum_review_tracker          # regenerate the two files
    python -m taleem_core.tools.curriculum_review_tracker --check  # exit 1 if they are stale
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..contexts.curriculum_studio.domain.workflow import REVIEW_CHAIN, STATE_ROLE

# Repo root: .../services/core-api/src/taleem_core/tools/<this file> -> parents[5].
DEFAULT_ROOT = Path(__file__).resolve().parents[5]
SPINE = "curriculum/grade-4/spine.json"
DRAFTS_DIR = "curriculum/grade-4/ai-drafts"
OUT_DIR = "curriculum/grade-4/review"
TRACKER_MD = f"{OUT_DIR}/REVIEW_TRACKER.md"
FLAGS_CSV = f"{OUT_DIR}/review_flags.csv"

BANNER = "AI-GENERATED DRAFT — NOT REVIEWED — NOT OFFICIAL CURRICULUM"
# The only status a draft file can have. The tracker has no code path that sets another one.
STATUS = "ai-draft-unreviewed"

# The five Studio review roles, in stage order (single source: the workflow state machine).
STUDIO_ROLES: tuple[str, ...] = tuple(STATE_ROLE[s] for s in REVIEW_CHAIN)
# Extra sign-offs the Studio has no role for. They are recorded in the review note of the stage
# shown, by a person qualified for them (see REVIEWER_CHECKLISTS.md).
SCHOLAR = "scholar"
SAFEGUARDING = "safeguarding"
EXTRA_LANES: dict[str, str] = {SCHOLAR: "subject_expert", SAFEGUARDING: "safety_officer"}
LANES: tuple[str, ...] = (*STUDIO_ROLES, SCHOLAR, SAFEGUARDING)
LANE_ABBR: dict[str, str] = {
    "subject_expert": "SE",
    "instructional_designer": "ID",
    "a11y_specialist": "A11y",
    "language_editor": "LE",
    "safety_officer": "SO",
    SCHOLAR: "Scholar",
    SAFEGUARDING: "Safeg.",
}
# Islamiat: every lesson needs a scholar, whatever its flags say.
SCHOLAR_PREFIXES = ("ISL",)

# Routing rules over the flag's leading "<reviewer>:" label, first match wins. A label naming two
# reviewers ("child-safety + subject expert") matches every rule it contains.
_LABEL_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("scholar", "religious subject expert"), SCHOLAR),
    (("safeguarding",), SAFEGUARDING),
    (("child-safety", "child safety", "safety", "religious-sensitivity"), "safety_officer"),
    (
        ("accessibility", "illustration", "rendering", "design", "audio", "blocker for release"),
        "a11y_specialist",
    ),
    (("language editor", "terminology", "translation"), "language_editor"),
    (
        ("interaction contract", "mentor", "assessment", "inclusion", "equity"),
        "instructional_designer",
    ),
    (("subject expert", "health", "anthem"), "subject_expert"),
)
# For flags with no recognised label: keywords over the whole text, then the subject expert.
_TEXT_RULES: tuple[tuple[str, str], ...] = (
    ("render", "a11y_specialist"),
    ("translation", "language_editor"),
    ("urdu", "language_editor"),
    ("inclusive", "instructional_designer"),
    ("distress", "safety_officer"),
)
_DEFAULT_LANE = "subject_expert"
_LABEL = re.compile(r"^([^:]{1,100}):")
_PLACEHOLDER = re.compile(r"\[[^\[\]]*to be supplied by a scholar[^\[\]]*\]")


def route_flag(text: str) -> tuple[str, ...]:
    """The review lanes a flag belongs to (deterministic; at least one)."""
    match = _LABEL.match(text)
    label = match.group(1).lower() if match else ""
    lanes: list[str] = []
    if label:
        consumed = label
        for keys, lane in _LABEL_RULES:
            if any(k in consumed for k in keys):
                if lane not in lanes:
                    lanes.append(lane)
                for k in keys:  # "religious subject expert" must not also match "subject expert"
                    consumed = consumed.replace(k, " ")
    if lanes:
        return tuple(sorted(lanes, key=LANES.index))
    lowered = text.lower()
    for key, lane in _TEXT_RULES:
        if key in lowered:
            return (lane,)
    return (_DEFAULT_LANE,)


def is_widget_flag(text: str) -> bool:
    return "bespoke widget" in text


def is_release_blocker(text: str) -> bool:
    lowered = text.lower()
    return lowered.startswith("audio:") or lowered.startswith("blocker")


@dataclass
class Flag:
    number: int
    text: str
    lanes: tuple[str, ...]


@dataclass
class Row:
    code: str
    prefix: str
    subject_key: str
    unit: str
    title_en: str
    title_ur: str
    exemplar: bool
    mentor_mediated: bool
    status: str = STATUS
    drafted_fields: int = 0
    flags: list[Flag] = field(default_factory=list)
    placeholders: int = 0

    @property
    def scholar_required(self) -> bool:
        return self.prefix in SCHOLAR_PREFIXES or any(SCHOLAR in f.lanes for f in self.flags)

    @property
    def safeguarding_required(self) -> bool:
        return any(SAFEGUARDING in f.lanes for f in self.flags)

    @property
    def widgets(self) -> int:
        return sum(is_widget_flag(f.text) for f in self.flags)

    @property
    def release_blockers(self) -> int:
        return sum(is_release_blocker(f.text) for f in self.flags)

    def lane_counts(self) -> Counter[str]:
        return Counter(lane for f in self.flags for lane in f.lanes)

    def signoffs(self) -> str:
        needs = ((SCHOLAR, self.scholar_required), (SAFEGUARDING, self.safeguarding_required))
        extra = [x for x, need in needs if need]
        return " + ".join(["5 stages", *extra])


@dataclass
class Track:
    prefix: str
    title: str
    subject_key: str
    units: list[tuple[str, str]]  # (unit key, unit title) in spine order


@dataclass
class Tracker:
    tracks: list[Track]
    rows: list[Row]
    problems: list[str]

    def rows_for(self, prefix: str, unit: str | None = None) -> list[Row]:
        return [r for r in self.rows if r.prefix == prefix and (unit is None or r.unit == unit)]


def _strings(node: Any) -> Iterator[tuple[str, str]]:
    """Every (locale-or-key, string) leaf in a draft value."""
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str):
                yield key, value
            else:
                yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


def load(root: Path) -> Tracker:
    spine = json.loads((root / SPINE).read_text(encoding="utf-8"))
    tracks: list[Track] = []
    for subject in spine["hierarchy"]["subjects"]:
        for track in subject["tracks"]:
            units = [
                (c["key"], c["title"])
                for c in subject["chapters"]
                if c["key"].startswith(track["prefix"] + "-")
            ]
            tracks.append(Track(track["prefix"], track["title"], subject["key"], units))

    problems: list[str] = []
    drafts_dir = root / DRAFTS_DIR
    files = {p.stem: p for p in sorted(drafts_dir.glob("*.json"))}
    rows: list[Row] = []
    seen: set[str] = set()
    for obj in spine["objectives"]:
        code = obj["code"]
        seen.add(code)
        row = Row(
            code=code,
            prefix=obj["prefix"],
            subject_key=obj["subject_key"],
            unit=obj["unit"],
            title_en=obj.get("title_en", ""),
            title_ur=obj.get("title_ur", ""),
            exemplar=bool(obj.get("exemplar")),
            mentor_mediated=bool(obj.get("mentor_mediated")),
        )
        rows.append(row)
        path = files.get(code)
        if path is None:
            problems.append(f"`{code}`: in the spine but has no draft file")
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("code") != code:
            problems.append(f"`{path.name}`: `code` is `{data.get('code')}`, not `{code}`")
        flags = data.get("review_flags") or []
        if not flags:
            problems.append(f"`{code}`: draft has no `review_flags`")
        texts = [str(t).strip() for t in flags]
        for text, n in Counter(texts).items():
            if n > 1:
                problems.append(f"`{code}`: flag repeated {n} times: {text[:60]}")
        row.flags = [Flag(i, t, route_flag(t)) for i, t in enumerate(texts, start=1)]
        row.drafted_fields = len(set(data) - {"code", "review_flags"})
        row.placeholders = sum(
            1 for key, s in _strings(data) if key == "en" for _ in _PLACEHOLDER.finditer(s)
        )
        if row.prefix in SCHOLAR_PREFIXES and not any(SCHOLAR in f.lanes for f in row.flags):
            problems.append(f"`{code}`: Islamiat draft has no scholar flag")
        if row.placeholders and row.prefix not in SCHOLAR_PREFIXES:
            problems.append(f"`{code}`: scripture placeholder outside Islamiat")
    for stem in sorted(set(files) - seen):
        problems.append(f"`{stem}.json`: draft file for an objective not in the spine")
    return Tracker(tracks, rows, problems)


# ------------------------------------------------------------------------------------ render


def _lane_cell(counts: Counter[str]) -> str:
    return " · ".join(f"{LANE_ABBR[lane]} {counts[lane]}" for lane in LANES if counts[lane])


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(t: Tracker) -> str:
    rows = t.rows
    total_flags = sum(len(r.flags) for r in rows)
    lines: list[str] = [
        f"> **{BANNER}**",
        ">",
        "> Every objective below is an AI first draft that no human has reviewed. Nothing here is",
        "> approved, published or seen by a child.",
        "",
        "# Grade 4 Review Tracker",
        "",
        "Generated by `python -m taleem_core.tools.curriculum_review_tracker` from",
        "[`spine.json`](../spine.json) and [`ai-drafts/`](../ai-drafts/).",
        "**Do not edit by hand**: `--check` fails when this file or",
        "[`review_flags.csv`](review_flags.csv) is stale.",
        "",
        "How to use it: [REVIEW_PLAN.md](REVIEW_PLAN.md) (order of work) and",
        "[REVIEWER_CHECKLISTS.md](REVIEWER_CHECKLISTS.md) (what each role checks). The flag format",
        "and import rules are in the [reviewer guide](../ai-drafts/README.md).",
        "",
        f"Status `{STATUS}` is the only status a draft file can carry. Review decisions are",
        "recorded in the Curriculum Studio workflow, never here.",
        "",
        "## Summary",
        "",
        f"- Objectives: **{len(rows)}**, every one `{STATUS}`.",
        f"- Open review flags: **{total_flags}**.",
        f"- Lessons needing a scholar: **{sum(r.scholar_required for r in rows)}**; "
        f"scripture placeholders to fill: **{sum(r.placeholders for r in rows)}**.",
        f"- Lessons needing the safeguarding reviewer: "
        f"**{sum(r.safeguarding_required for r in rows)}**.",
        f"- Activities that are bespoke widgets (not playable yet): "
        f"**{sum(r.widgets for r in rows)}**.",
        f"- Flags that block release until audio exists: "
        f"**{sum(r.release_blockers for r in rows)}**.",
        "",
        "Every lesson needs all five Studio stages, in order, by five different people, none of",
        "them its author: " + " → ".join(f"`{r}`" for r in STUDIO_ROLES) + ".",
        "",
        "| Track | Studio subject | Objectives | Units | Exemplar ★ | Mentor-mediated "
        "| Open flags | Flags per objective | Scholar | Safeguarding | Placeholders | Widgets "
        "| Audio blockers |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for tr in t.tracks:
        rs = t.rows_for(tr.prefix)
        nf = sum(len(r.flags) for r in rs)
        lines.append(
            f"| {tr.title} (`{tr.prefix}`) | `{tr.subject_key}` | {len(rs)} | {len(tr.units)} "
            f"| {sum(r.exemplar for r in rs)} | {sum(r.mentor_mediated for r in rs)} | {nf} "
            f"| {nf / len(rs):.1f} | {sum(r.scholar_required for r in rs)} "
            f"| {sum(r.safeguarding_required for r in rs)} | {sum(r.placeholders for r in rs)} "
            f"| {sum(r.widgets for r in rs)} | {sum(r.release_blockers for r in rs)} |"
            if rs
            else f"| {tr.title} (`{tr.prefix}`) | `{tr.subject_key}` | 0 | | | | | | | | | | |"
        )
    lines += [
        f"| **Total** | | **{len(rows)}** | **{sum(len(tr.units) for tr in t.tracks)}** "
        f"| **{sum(r.exemplar for r in rows)}** | **{sum(r.mentor_mediated for r in rows)}** "
        f"| **{total_flags}** | **{total_flags / max(len(rows), 1):.1f}** "
        f"| **{sum(r.scholar_required for r in rows)}** "
        f"| **{sum(r.safeguarding_required for r in rows)}** "
        f"| **{sum(r.placeholders for r in rows)}** | **{sum(r.widgets for r in rows)}** "
        f"| **{sum(r.release_blockers for r in rows)}** |",
        "",
        "## Flags by review lane",
        "",
        "Each flag is routed to the lane that should resolve it first (a flag naming two reviewers "
        "counts in both). Scholar flags are resolved at the `subject_expert` stage by a qualified "
        "scholar; safeguarding flags at the `safety_officer` stage with the safeguarding reviewer.",
        "",
        "| Track | " + " | ".join(f"`{lane}`" for lane in LANES) + " |",
        "| --- |" + " --- |" * len(LANES),
    ]
    for tr in t.tracks:
        counts: Counter[str] = Counter()
        for r in t.rows_for(tr.prefix):
            counts.update(r.lane_counts())
        lines.append(f"| `{tr.prefix}` | " + " | ".join(str(counts[x]) for x in LANES) + " |")
    total: Counter[str] = Counter()
    for r in rows:
        total.update(r.lane_counts())
    lines += [
        "| **Total** | " + " | ".join(f"**{total[x]}**" for x in LANES) + " |",
        "",
        "Lane abbreviations in the tables below: "
        + ", ".join(f"{LANE_ABBR[x]} = `{x}`" for x in LANES)
        + ".",
        "",
        "## Data checks",
        "",
    ]
    if t.problems:
        lines += [f"- {p}" for p in t.problems]
    else:
        lines.append(
            "- None found: every spine objective has exactly one draft file with a matching "
            "`code` and at least one flag; no flag repeats; every Islamiat draft has a scholar "
            "flag; scripture placeholders occur only in Islamiat."
        )
    lines.append("")
    for tr in t.tracks:
        lines += [f"## {tr.title} (`{tr.prefix}`)", ""]
        for unit_key, unit_title in tr.units:
            rs = t.rows_for(tr.prefix, unit_key)
            lines += [
                f"### `{unit_key}` — {_md_escape(unit_title)}",
                "",
                "| Objective | Title | Status | Open flags | By lane | Sign-offs | Notes |",
                "| --- | --- | --- | --- | --- | --- | --- |",
            ]
            for r in rs:
                notes = []
                if r.exemplar:
                    notes.append("exemplar ★")
                if r.mentor_mediated:
                    notes.append("mentor-mediated")
                if r.placeholders:
                    notes.append(f"{r.placeholders} scripture placeholder(s)")
                if r.widgets:
                    notes.append(f"{r.widgets} widget")
                if r.release_blockers:
                    notes.append("audio blocks release")
                notes.append(f"{r.drafted_fields} drafted fields")
                lines.append(
                    f"| `{r.code}` | {_md_escape(r.title_en)} | `{r.status}` | {len(r.flags)} "
                    f"| {_lane_cell(r.lane_counts())} | {r.signoffs()} | {'; '.join(notes)} |"
                )
            lines += ["", "Open flags:", ""]
            for r in rs:
                for f in r.flags:
                    lane = ", ".join(LANE_ABBR[x] for x in f.lanes)
                    lines.append(f"- `{r.code}` F{f.number} [{lane}] {_md_escape(f.text)}")
            lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


CSV_COLUMNS = (
    "objective",
    "track",
    "unit",
    "objective_status",
    "flag_no",
    "lanes",
    "studio_stage_role",
    "extra_signoff",
    "flag",
    "flag_status",
    "reviewer",
    "decision",
    "date",
    "studio_note",
)


def render_csv(t: Tracker) -> str:
    buf = io.StringIO()
    buf.write(f"# {BANNER}\n")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for r in t.rows:
        for f in r.flags:
            stage_roles = sorted({EXTRA_LANES.get(x, x) for x in f.lanes}, key=STUDIO_ROLES.index)
            extra = [x for x in f.lanes if x in EXTRA_LANES]
            writer.writerow(
                (
                    r.code,
                    r.prefix,
                    r.unit,
                    r.status,
                    f.number,
                    ";".join(f.lanes),
                    ";".join(stage_roles),
                    ";".join(extra),
                    f.text,
                    "open",
                    "",
                    "",
                    "",
                    "",
                )
            )
    return buf.getvalue()


def outputs(root: Path) -> dict[str, str]:
    tracker = load(root)
    return {TRACKER_MD: render_markdown(tracker), FLAGS_CSV: render_csv(tracker)}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m taleem_core.tools.curriculum_review_tracker",
        description=__doc__.split("\n")[0],
    )
    parser.add_argument("--check", action="store_true", help="exit 1 if the outputs are stale")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repository root")
    args = parser.parse_args(argv)
    root: Path = args.root
    stale = []
    for rel, text in outputs(root).items():
        path = root / rel
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if args.check:
            stale.append(rel)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"wrote {rel}")
    if stale:
        print("stale (run without --check to regenerate): " + ", ".join(stale), file=sys.stderr)
        return 1
    if args.check:
        print("review tracker is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
