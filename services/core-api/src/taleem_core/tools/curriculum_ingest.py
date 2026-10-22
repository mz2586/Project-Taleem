"""Phase B ingestion: Grade 4 curriculum design documents -> Curriculum Studio **draft** lessons.

Reads the Grade 4 design documents into a validated objective spine (``curriculum_spine``), then
creates one Studio draft lesson per objective **through the application service**
(``CurriculumStudioService.create``) — never by writing tables directly.

Honesty rules (non-negotiable, enforced here and asserted by ``tests/test_curriculum_ingest.py``):

- Ingested lessons are **drafts**. This tool never submits, reviews, approves or publishes, and
  never records a quality-gate result.
- It carries only what the spine states: code, ``[RE-EXPRESSED]`` outcome, difficulty, duration,
  prerequisites, competency, assessment type, unit/topic placement (as tags) and, for
  mathematics, the bilingual title from ``LESSON_CATALOG.md``. It does **not** write Urdu
  explanations, scripts, questions, hints, misconceptions, media, or audio references, and no AI
  writes lesson content.
- Provenance is ``authored-original`` exactly as the documents declare; the Studio's provenance rule
  (``check_provenance``) runs before anything is created, so a prohibited source is refused.
- Idempotent: an objective that already has a lesson (matched by objective code or lesson id) is
  skipped, whatever its state. Re-running never duplicates and never edits.

The ``--dry-run`` report runs the Studio validation on every draft and lists, per lesson, which of
the 9 quality gates fail and why: that report is the honest content-gap list.

Usage (from ``services/core-api``)::

    python -m taleem_core.tools.curriculum_ingest --dry-run   # report + regenerate spine/report
    python -m taleem_core.tools.curriculum_ingest --check     # fail if spine/report are stale
    python -m taleem_core.tools.curriculum_ingest             # write drafts to CS_DATABASE_URL
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ..contexts.curriculum_studio.application.repository import (
    InMemoryLessonRepository,
    RecordingPublishPort,
)
from ..contexts.curriculum_studio.application.service import STAGE_GATES, CurriculumStudioService
from ..contexts.curriculum_studio.domain.ai_teaching import AITeachingObject
from ..contexts.curriculum_studio.domain.assessment import AssessmentBlueprint
from ..contexts.curriculum_studio.domain.content import Difficulty, Locale, LocalizedText
from ..contexts.curriculum_studio.domain.hierarchy import (
    Chapter,
    EducationSystem,
    Grade,
    Subject,
    Topic,
    is_valid_grade_subject,
)
from ..contexts.curriculum_studio.domain.lesson import Lesson, Metadata
from ..contexts.curriculum_studio.domain.provenance import (
    Derivation,
    Provenance,
    ProvenanceError,
    check_provenance,
)
from ..contexts.curriculum_studio.domain.quality import ALL_GATES, AUTOMATED_GATES, Gate
from ..contexts.curriculum_studio.domain.workflow import STATE_ROLE, WorkflowState
from .curriculum_spine import (
    GRADE_KEY,
    PREFIX_ORDER,
    PREFIXES,
    REPORT_PATH,
    SPINE_PATH,
    SYSTEM_KEY,
    Objective,
    Spine,
    SpineError,
    load_spine,
    split_bilingual,
)

INGEST_TAG = "ingest:grade4-spine"

# Repo root: .../services/core-api/src/taleem_core/tools/curriculum_ingest.py -> parents[5].
DEFAULT_ROOT = Path(__file__).resolve().parents[5]


# --------------------------------------------------------------------------------- building


def lesson_provenance(spine: Spine, objective: Objective) -> Provenance:
    """Provenance exactly as the objective's source document declares it."""
    declared = spine.provenance_for(objective.source)
    return Provenance(
        derivation=Derivation(declared.derivation),
        source=declared.source,
        license="authored-original",
        aligned_slo_codes=[objective.code],
    )


def _tags(o: Objective) -> list[str]:
    tags = [
        INGEST_TAG,
        f"unit:{o.unit}",
        f"topic:{o.topic}",
        f"domain:{o.domain}",
        f"competency:{o.competency}",
        f"spine-difficulty:{o.difficulty}",
        f"assessment:{o.assessment}",
    ]
    if o.track:
        tags.append(f"track:{o.track}")
    if o.exemplar:
        tags.append("exemplar")
    if o.mentor_mediated:
        tags.append("mentor-mediated")
    tags += [f"external-prerequisite:{e}" for e in o.external_prerequisites]
    return tags


def build_draft(spine: Spine, o: Objective) -> Lesson:
    """A draft carrying only the spine's metadata. Every authored-content field stays empty."""
    title = LocalizedText(text={Locale.EN: o.title_en})
    if o.title_ur:
        title.text[Locale.UR] = o.title_ur
    return Lesson(
        lesson_id=o.lesson_id,
        title=title,
        metadata=Metadata(grade_key=GRADE_KEY, subject_key=o.subject_key, tags=_tags(o)),
        provenance=lesson_provenance(spine, o),
        # Only the SLO the lesson advances; strategy/escalation/forbidden behaviours are authored.
        ai_teaching_object=AITeachingObject(learning_goals=[o.code]),
        assessment=AssessmentBlueprint(),
        description=LocalizedText(text={Locale.EN: o.outcome}),
        learning_outcomes=[o.code],
        prerequisites=list(o.prerequisites),
        estimated_duration_min=o.duration_min,
        difficulty=Difficulty(o.studio_difficulty),
    )


def build_hierarchy(spine: Spine) -> EducationSystem:
    """Grade G4 -> subjects -> chapters (units) -> topics, as Studio hierarchy objects.

    The Studio application service persists lessons only (there is no hierarchy repository/port),
    so the hierarchy is validated here, carried on each lesson as ``unit:``/``topic:`` tags, and
    published in ``spine.json``.
    """
    subjects: dict[str, Subject] = {}
    for t in spine.tracks:
        if not is_valid_grade_subject(GRADE_KEY, t.subject_key):
            raise SpineError([f"{t.subject_key} is not a {GRADE_KEY} subject in the Studio roster"])
        subj = subjects.setdefault(
            t.subject_key,
            Subject(
                subject_id=f"{GRADE_KEY}/{t.subject_key}",
                key=t.subject_key,
                title=LocalizedText(text={Locale.EN: t.title}),
            ),
        )
        for u in t.units:
            ur, en = split_bilingual(u.title)
            chapter = Chapter(chapter_id=u.key, key=u.key, title=_loc(ur, en))
            for tp in u.topics:
                tur, ten = split_bilingual(tp.title)
                chapter.topics.append(Topic(topic_id=tp.key, key=tp.key, title=_loc(tur, ten)))
            subj.chapters.append(chapter)
    grade = Grade(grade_id=GRADE_KEY, key=GRADE_KEY, subjects=list(subjects.values()))
    return EducationSystem(
        system_id=SYSTEM_KEY,
        key=SYSTEM_KEY,
        name="National Curriculum of Pakistan",
        grades=[grade],
    )


def _loc(ur: str, en: str) -> LocalizedText:
    text: dict[Locale, str] = {}
    if ur:
        text[Locale.UR] = ur
    if en:
        text[Locale.EN] = en
    return LocalizedText(text=text)


# --------------------------------------------------------------------------------- ingest


@dataclass
class PlanEntry:
    code: str
    lesson_id: str
    action: str  # "create" | "skip"
    existing_state: str = ""


@dataclass
class IngestResult:
    entries: list[PlanEntry] = field(default_factory=list)

    @property
    def created(self) -> list[PlanEntry]:
        return [e for e in self.entries if e.action == "create"]

    @property
    def skipped(self) -> list[PlanEntry]:
        return [e for e in self.entries if e.action == "skip"]


def plan(spine: Spine, existing: Iterable[Lesson]) -> IngestResult:
    """Decide create/skip per objective, keyed by objective code (and lesson id)."""
    by_code: dict[str, Lesson] = {}
    by_id: dict[str, Lesson] = {}
    for lesson in existing:
        by_id[lesson.lesson_id] = lesson
        for code in lesson.learning_outcomes:
            by_code.setdefault(code, lesson)
    result = IngestResult()
    for o in spine.objectives:
        found = by_code.get(o.code)
        clash = by_id.get(o.lesson_id)
        if found is None and clash is not None:
            raise SpineError(
                [f"lesson id {o.lesson_id} exists but does not carry objective {o.code}"]
            )
        if found is not None:
            result.entries.append(
                PlanEntry(o.code, found.lesson_id, "skip", found.workflow.state.value)
            )
        else:
            result.entries.append(PlanEntry(o.code, o.lesson_id, "create"))
    return result


def ingest(spine: Spine, service: CurriculumStudioService) -> IngestResult:
    """Create the missing drafts through the application service. Fails closed on provenance.

    Every draft is built and provenance-checked before the first ``create``, so a refused source
    leaves nothing behind.
    """
    build_hierarchy(spine)  # validates grade/subject placement
    result = plan(spine, service.list())
    by_code = spine.by_code()
    drafts: list[Lesson] = []
    for entry in result.created:
        draft = build_draft(spine, by_code[entry.code])
        findings = check_provenance(draft.provenance)
        if draft.provenance.derivation is not Derivation.AUTHORED_ORIGINAL:
            findings.append("ingested Grade 4 drafts must be authored-original")
        if findings:
            raise ProvenanceError(f"{entry.code}: " + "; ".join(findings))
        drafts.append(draft)
    for draft in drafts:
        created = service.create(draft)
        if created.workflow.state is not WorkflowState.DRAFT:  # pragma: no cover - defensive
            raise RuntimeError(f"{created.lesson_id} left draft state on create")
    return result


# --------------------------------------------------------------------------------- gate report

_HUMAN_STAGE: dict[Gate, WorkflowState] = {
    gate: stage for stage, gates in STAGE_GATES.items() for gate in gates
}


@dataclass
class GateStatus:
    gate: Gate
    passed: bool
    reasons: list[str]
    vacuous: bool = False


@dataclass
class LessonGateRow:
    code: str
    lesson_id: str
    prefix: str
    state: str
    gates: list[GateStatus]
    blockers: list[str]  # structural findings (field names) that block submission

    @property
    def failing(self) -> list[GateStatus]:
        return [g for g in self.gates if not g.passed]


def gate_rows(spine: Spine, service: CurriculumStudioService) -> list[LessonGateRow]:
    """Run the Studio validation on each objective's lesson; classify all 9 gates."""
    rows: list[LessonGateRow] = []
    index = {e.code: e for e in plan(spine, service.list()).entries}
    for o in spine.objectives:
        lesson = service.get(index[o.code].lesson_id)
        result = service.validate(lesson.lesson_id)
        auto = {r.gate: r for r in result.gate_results}
        certified = {r.gate for r in lesson.quality_gate_results if r.passed and r.mode == "human"}
        statuses: list[GateStatus] = []
        for gate in ALL_GATES:
            reasons: list[str] = []
            auto_result = auto.get(gate)
            if auto_result is not None and not auto_result.passed:
                reasons += [f.message for f in auto_result.findings] or ["automated check failed"]
            stage = _HUMAN_STAGE.get(gate)
            if stage is not None and gate not in certified:
                reasons.append(f"not certified: needs `{STATE_ROLE[stage]}` approval")
            vacuous = (
                gate is Gate.READABILITY
                and not reasons
                and not lesson.student_explanation.has(Locale.UR)
            )
            statuses.append(GateStatus(gate, not reasons, reasons, vacuous))
        blockers = sorted({f.field or f.message for f in result.structural})
        rows.append(
            LessonGateRow(
                o.code, lesson.lesson_id, o.prefix, lesson.workflow.state.value, statuses, blockers
            )
        )
    return rows


def _esc(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_report(spine: Spine, rows: Sequence[LessonGateRow]) -> str:
    """The generated, markdownlint-clean INGESTION_REPORT.md (deterministic)."""
    n = len(rows)
    all_green = [r for r in rows if not r.failing]
    out: list[str] = [
        "# Grade 4 Ingestion Report",
        "",
        "Generated by `python -m taleem_core.tools.curriculum_ingest --dry-run` from the Grade 4 "
        "design documents. **Do not edit by hand**: `--check` fails when this file or "
        "[`spine.json`](spine.json) is stale.",
        "",
        "This is the honest content-gap list. Each lesson below is a Curriculum Studio **draft** "
        "built from the objective spine only. The ingest never advances a lesson through review, "
        "never records an approval, and never writes Urdu explanations, questions, hints, "
        "misconceptions, media or audio references.",
        "",
        "## Summary",
        "",
        f"- Objectives parsed: **{len(spine.objectives)}** across {len(spine.tracks)} tracks "
        f"({len(spine.counts_by_subject())} Studio subjects).",
        f"- Drafts the ingest creates: **{n}**, every one in state `draft`, with "
        "`Provenance.derivation == authored-original` as the documents declare.",
        f"- Lessons passing all 9 quality gates: **{len(all_green)}**.",
        "- Why: the spine supplies metadata only (code, outcome, difficulty, duration, "
        "prerequisites, competency, assessment type). Every lesson still needs authored bilingual "
        "content, recorded Urdu audio, an offline package, and five human review stages. Those "
        "cannot be produced by a parser and are not faked here.",
        "",
        "| Track | Studio subject | Source | Objectives | Units | Exemplar ★ |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    counts = spine.counts_by_prefix()
    for t in spine.tracks:
        stars = sum(1 for o in spine.objectives if o.prefix == t.prefix and o.exemplar)
        out.append(
            f"| {t.title} (`{t.prefix}-G4-*`) | `{t.subject_key}` | `{t.source}` | "
            f"{counts[t.prefix]} | {len(t.units)} | {stars} |"
        )
    out += [
        f"| **Total** | | | **{len(spine.objectives)}** | "
        f"**{sum(len(t.units) for t in spine.tracks)}** | "
        f"**{sum(1 for o in spine.objectives if o.exemplar)}** |",
        "",
        "## What the ingest carries",
        "",
        "- **Carried from the spine:** objective code (`learning_outcomes`, "
        "`provenance.aligned_slo_codes`, `ai_teaching_object.learning_goals`), the "
        "`[RE-EXPRESSED]` outcome (English `description`), difficulty, duration, resolved "
        "prerequisites, and placement plus competency and assessment type as `metadata.tags`.",
        "- **Titles:** mathematics titles are the bilingual titles in `LESSON_CATALOG.md`. The "
        "other subjects' documents state no lesson title, so the English title is the outcome "
        "and the Urdu title is left empty.",
        "- **Hierarchy:** grade `G4` → subjects → chapters (units) → topics (unit × domain) "
        "is built and validated as Studio hierarchy objects. The Studio service has no hierarchy "
        "persistence port, so placement travels as `unit:`/`topic:` tags and in `spine.json`.",
        "- **Not carried:** `GRADE4_MATH_CURRICULUM.md` and each exemplar section contain authored "
        "prose (vocabulary, worked examples, hint ladders, homework, notes). It is not "
        "transferred: it is prose, not structured bilingual Studio items, and splitting it "
        "into items, hints or scripts would be machine authoring. An author transfers it in the "
        "Studio.",
        "- **Offline packages:** none are set. The catalog's planned `pkg/…` ids name packages "
        "that do not exist yet; they are built after publish.",
        "",
        "## Gate status across all drafts",
        "",
        "| Gate | Checked by | Drafts passing | Drafts failing | Why it fails |",
        "| --- | --- | --- | --- | --- |",
    ]
    for gi, gate in enumerate(ALL_GATES):
        statuses = [r.gates[gi] for r in rows]
        passing = sum(1 for s in statuses if s.passed)
        reasons = sorted({reason for s in statuses for reason in s.reasons})
        checked = _checked_by(gate, _HUMAN_STAGE.get(gate))
        why = "; ".join(_esc(r) for r in reasons) or "—"
        if any(s.vacuous for s in statuses):
            why = "passes vacuously: there is no Urdu `student_explanation` text to measure"
        out.append(f"| `{gate.value}` | {checked} | {passing} | {n - passing} | {why} |")
    blocker_counts: dict[str, int] = {}
    for r in rows:
        for b in r.blockers:
            blocker_counts[b] = blocker_counts.get(b, 0) + 1
    out += [
        "",
        "## Submission blockers",
        "",
        "Structural findings from the Studio validator. Any one blocks `:submit`.",
        "",
        "| Field | Drafts blocked |",
        "| --- | --- |",
    ]
    for name, count in sorted(blocker_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        out.append(f"| `{_esc(name)}` | {count} |")
    out += ["", "## Per-lesson gate failures", ""]
    for prefix in PREFIX_ORDER:
        prefix_rows = [r for r in rows if r.prefix == prefix]
        if not prefix_rows:
            continue
        out += [
            f"### {PREFIXES[prefix][2]} (`{prefix}-G4-*`)",
            "",
            "| Objective | Lesson | State | Gates failing | Why (automated checks) | Blockers |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
        for r in prefix_rows:
            failing = ", ".join(f"`{g.gate.value}`" for g in r.failing) or "none"
            auto_why = "; ".join(
                f"`{g.gate.value}`: " + _esc(reason)
                for g in r.failing
                for reason in g.reasons
                if not reason.startswith("not certified")
            )
            human = [g for g in r.failing if g.gate in _HUMAN_STAGE]
            why = auto_why or "—"
            if human:
                why += f"; {len(human)} gates await human review"
            out.append(
                f"| `{r.code}` | `{r.lesson_id}` | `{r.state}` | {len(r.failing)}/9: {failing} | "
                f"{why} | {len(r.blockers)} |"
            )
        out.append("")
    dag_edges = sum(len(o.prerequisites) for o in spine.objectives)
    cross = sum(
        1 for o in spine.objectives for p in o.prerequisites if p.split("-", 1)[0] != o.prefix
    )
    out += [
        "## Prerequisite DAG",
        "",
        f"- {dag_edges} prerequisite edges; every one resolves to a parsed objective; no cycles "
        f"({cross} cross-subject).",
        f"- {sum(1 for o in spine.objectives if not o.prerequisites)} entry objectives (no "
        "in-grade prerequisite).",
        f"- {sum(1 for o in spine.objectives if o.external_prerequisites)} objective(s) cite a "
        "prior-grade prerequisite, kept as an `external-prerequisite:` tag, not an edge.",
        "",
        "## Source consistency notes",
        "",
        "Found by the parser. None blocks ingestion; each needs an owner's decision.",
        "",
    ]
    out += [f"- {note}" for note in spine.notes]
    return "\n".join(out) + "\n"


def _checked_by(gate: Gate, stage: WorkflowState | None) -> str:
    parts: list[str] = []
    if gate in AUTOMATED_GATES:
        parts.append("automated pre-check")
    if stage is not None:
        parts.append(f"`{STATE_ROLE[stage]}` review")
    return " + ".join(parts) or "—"


# --------------------------------------------------------------------------------- artifacts


def in_memory_service() -> CurriculumStudioService:
    return CurriculumStudioService(InMemoryLessonRepository(), RecordingPublishPort())


def generate(spine: Spine) -> tuple[str, str, list[LessonGateRow]]:
    """(spine.json text, INGESTION_REPORT.md text, gate rows) — independent of any database."""
    service = in_memory_service()
    ingest(spine, service)
    rows = gate_rows(spine, service)
    return spine.to_json(), render_report(spine, rows), rows


def stale_artifacts(root: Path, spine: Spine) -> list[str]:
    """Repo-relative paths whose committed content differs from a fresh generation."""
    spine_text, report_text, _rows = generate(spine)
    stale: list[str] = []
    for rel, fresh in ((SPINE_PATH, spine_text), (REPORT_PATH, report_text)):
        path = root / rel
        if not path.exists() or path.read_text(encoding="utf-8") != fresh:
            stale.append(rel)
    return stale


def write_artifacts(root: Path, spine: Spine) -> list[LessonGateRow]:
    spine_text, report_text, rows = generate(spine)
    (root / SPINE_PATH).write_text(spine_text, encoding="utf-8")
    (root / REPORT_PATH).write_text(report_text, encoding="utf-8")
    return rows


# --------------------------------------------------------------------------------- database


def run_with_database(
    url: str, fn: Callable[[CurriculumStudioService], IngestResult], *, commit: bool
) -> IngestResult:
    """Open one Unit of Work on ``url`` and run ``fn`` against a service bound to it.

    The whole ingest is one transaction: it commits only when ``commit`` is true and ``fn`` returns.
    """
    from ..contexts.curriculum_studio.adapters.persistence import (
        Base,
        create_db_engine,
        create_session_factory,
        unit_of_work,
    )

    engine = create_db_engine(url)
    if engine.dialect.name == "sqlite":  # dev/test only; PostgreSQL uses the Alembic schema
        Base.metadata.create_all(engine)
    try:
        with unit_of_work(create_session_factory(engine)) as uow:
            service = CurriculumStudioService(uow.lessons, uow.publish)
            result = fn(service)
            if commit:
                uow.commit()
            else:
                uow.rollback()
            return result
    finally:
        engine.dispose()


# --------------------------------------------------------------------------------- CLI


def _print_plan(result: IngestResult, *, verb: str) -> None:
    print(f"{verb}: {len(result.created)} draft(s); skip {len(result.skipped)} existing.")
    for e in result.skipped:
        print(f"  skip {e.code} -> {e.lesson_id} (state {e.existing_state})")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m taleem_core.tools.curriculum_ingest", description=__doc__.split("\n")[0]
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="print the gate report, regenerate spine.json + INGESTION_REPORT.md; no DB writes",
    )
    mode.add_argument(
        "--check", action="store_true", help="exit 1 if spine.json/INGESTION_REPORT.md are stale"
    )
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repository root")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("CS_DATABASE_URL", ""),
        help="target database (default: $CS_DATABASE_URL)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root

    try:
        spine = load_spine(root)
    except SpineError as exc:
        print("curriculum documents are inconsistent:", file=sys.stderr)
        for p in exc.problems:
            print(f"  - {p}", file=sys.stderr)
        return 1

    if args.check:
        stale = stale_artifacts(root, spine)
        if stale:
            for rel in stale:
                print(f"STALE: {rel} (regenerate with --dry-run)", file=sys.stderr)
            return 1
        print(f"OK: {SPINE_PATH} and {REPORT_PATH} match the design documents.")
        return 0

    if args.dry_run:
        rows = write_artifacts(root, spine)
        print((root / REPORT_PATH).read_text(encoding="utf-8"))
        green = sum(1 for r in rows if not r.failing)
        print(f"wrote {SPINE_PATH} and {REPORT_PATH}; {green}/{len(rows)} lessons all-gates-green.")
        if args.database_url:
            result = run_with_database(
                args.database_url, lambda s: plan(spine, s.list()), commit=False
            )
            _print_plan(result, verb="against the configured database, would create")
        else:
            print("CS_DATABASE_URL not set: plan shown against an empty database.")
        return 0

    if not args.database_url:
        print(
            "CS_DATABASE_URL is not set (or pass --database-url); nothing written.", file=sys.stderr
        )
        return 2
    try:
        result = run_with_database(args.database_url, lambda s: ingest(spine, s), commit=True)
    except (ProvenanceError, SpineError) as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 1
    _print_plan(result, verb="created")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
