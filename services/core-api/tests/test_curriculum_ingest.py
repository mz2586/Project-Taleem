"""Phase B ingestion: Grade 4 design documents -> Curriculum Studio drafts.

Covers the parser over the real documents (counts per subject), prerequisite-DAG validation (cycle +
dangling prereq fixtures), idempotency, provenance enforcement (a prohibited source is refused),
drafts-only (no lesson leaves ``draft``, no gate is recorded, nothing authored is invented), the
``--check`` staleness mode, and an end-to-end write over SQLite and a PostgreSQL-gated variant.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from taleem_core.contexts.curriculum_studio.adapters.persistence import (
    create_db_engine,
    create_session_factory,
    unit_of_work,
)
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.content import Locale
from taleem_core.contexts.curriculum_studio.domain.lesson import Lesson
from taleem_core.contexts.curriculum_studio.domain.provenance import Derivation, ProvenanceError
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction, WorkflowState
from taleem_core.tools import curriculum_ingest as ci
from taleem_core.tools import curriculum_spine as cs
from taleem_core.vertical_slice.fractions_lesson import LESSON_KEY, build_fractions_lesson

ROOT = Path(__file__).resolve().parents[3]

EXPECTED_BY_PREFIX = {
    "MATH": 31,
    "URD": 20,
    "ENG": 20,
    "SCI": 20,
    "SOC": 16,
    "ISL": 16,
    "ETH": 16,
}
EXPECTED_BY_SUBJECT = {
    "math": 31,
    "urdu": 20,
    "english": 20,
    "science": 20,
    "social_studies": 16,
    "islamiat_ethics": 32,
}
TOTAL = 139


@pytest.fixture(scope="module")
def spine() -> cs.Spine:
    return cs.load_spine(ROOT)


def _fixture_doc(rows: list[str], *, header_extra: str = "", provenance: bool = True) -> str:
    declared = "`authored-original`" if provenance else "original"
    body = "\n".join(rows)
    return f"""# Grade 4 — General Science

Status: fixture; {declared}.
{header_extra}

## 1. Domains + objective map

| Domain | Tag | Objectives |
| --- | --- | --- |
| Living things | `LIV` | SCI-G4-LIV-01 … 03 |

## 2. Units + lessons

### Unit U1 — Living things

| Objective | Outcome | Diff | Comp | Dur | Prereq | Assess |
| --- | --- | --- | --- | --- | --- | --- |
{body}

## 3. Exemplar lesson — ★ SCI-G4-LIV-01
"""


_OK_ROWS = [
    "| ★ SCI-G4-LIV-01 | Tell living from non-living | INTRO | C | 18 | — | MCQ |",
    "| SCI-G4-LIV-02 | Name plant parts | CORE | K | 18 | LIV-01 | label + MCQ |",
    "| SCI-G4-LIV-03 | Describe needs | STRETCH | An | 18 | LIV-01…02 | constructed (mentor) |",
]


# ---------------------------------------------------------------- parser over the real docs


def test_parser_counts_per_subject_over_real_docs(spine: cs.Spine) -> None:
    assert spine.counts_by_prefix() == EXPECTED_BY_PREFIX
    assert spine.counts_by_subject() == EXPECTED_BY_SUBJECT
    assert len(spine.objectives) == TOTAL
    assert len({o.code for o in spine.objectives}) == TOTAL
    assert {p.derivation for p in spine.provenance} == {"authored-original"}


def test_parser_reads_spine_fields_faithfully(spine: cs.Spine) -> None:
    by = spine.by_code()
    gr05 = by["ENG-G4-GR-05"]  # "GR-01…04" range
    assert gr05.prerequisites == tuple(f"ENG-G4-GR-0{i}" for i in range(1, 5))
    wr02 = by["URD-G4-WR-02"]  # "GR-05, WR-01"
    assert wr02.prerequisites == ("URD-G4-GR-05", "URD-G4-WR-01")
    assert by["MATH-G4-AS-04"].prerequisites == ("MATH-G4-NB-04", "MATH-G4-AS-03")
    nb01 = by["MATH-G4-NB-01"]
    assert nb01.prerequisites == ()
    assert nb01.external_prerequisites  # Grade 3 prior knowledge, not an edge
    assert (nb01.title_ur, nb01.title_en) == ("اعداد پڑھنا لکھنا", "Read & write numbers")
    assert nb01.lesson_id == "L-math-g4-nb-read-write"
    assert by["MATH-G4-FR-01"].lesson_id == LESSON_KEY
    rd03 = by["URD-G4-RD-03"]
    assert (rd03.difficulty, rd03.studio_difficulty) == ("CORE", "developing")
    assert rd03.duration_min == 20
    assert rd03.exemplar and rd03.competency == "comprehension"
    assert by["SCI-G4-INQ-03"].mentor_mediated
    assert by["ISL-G4-SIR-01"].track == "islamiat" and by["ETH-G4-HON-01"].track == "ethics"
    assert by["ETH-G4-HON-01"].unit == "ETH-G4-U1"  # no unit headings: one unit per domain


def test_spine_json_round_trip(spine: cs.Spine) -> None:
    data = json.loads(spine.to_json())
    assert data["counts"]["by_prefix"] == EXPECTED_BY_PREFIX
    assert [o["code"] for o in data["objectives"]] == [o.code for o in spine.objectives]
    order = data["prerequisite_dag"]["topological_order"]
    position = {c: i for i, c in enumerate(order)}
    for o in data["objectives"]:
        for p in o["prerequisites"]:
            assert position[p] < position[o["code"]]
    # Deterministic: a second build of the same text is byte-identical.
    assert cs.load_spine(ROOT).to_json() == spine.to_json()


def test_committed_spine_is_fresh(spine: cs.Spine) -> None:
    """CI drift guard: curriculum/grade-4/spine.json matches the markdown."""
    assert cs.SPINE_PATH not in ci.stale_artifacts(
        ROOT, spine
    ), "spine.json is stale: run `python -m taleem_core.tools.curriculum_ingest --dry-run`"


def test_hierarchy_is_grade4_subjects_chapters_topics(spine: cs.Spine) -> None:
    system = ci.build_hierarchy(spine)
    (grade,) = system.grades
    assert grade.key == "G4"
    assert sorted(s.key for s in grade.subjects) == sorted(EXPECTED_BY_SUBJECT)
    urdu = next(s for s in grade.subjects if s.key == "urdu")
    u1 = urdu.chapters[0]
    assert u1.title.text[Locale.UR] == "روانی سے پڑھنا"
    assert u1.title.text[Locale.EN] == "Reading fluently"
    assert {t.key for t in u1.topics} == {"URD-G4-U1-RD", "URD-G4-U1-VO"}


def test_split_bilingual_never_translates() -> None:
    assert cs.split_bilingual("Phonics & fluent reading") == ("", "Phonics & fluent reading")
    assert cs.split_bilingual("قواعد (Grammar)") == ("قواعد", "Grammar")
    assert cs.split_bilingual("لکھنا — Writing") == ("لکھنا", "Writing")
    assert cs.split_bilingual("صرف اردو") == ("صرف اردو", "")


# ---------------------------------------------------------------- DAG validation


def test_fixture_doc_parses() -> None:
    sp = cs.build_spine({"fixture/SCI.md": _fixture_doc(_OK_ROWS)})
    assert [o.code for o in sp.objectives] == ["SCI-G4-LIV-01", "SCI-G4-LIV-02", "SCI-G4-LIV-03"]
    assert sp.objectives[2].prerequisites == ("SCI-G4-LIV-01", "SCI-G4-LIV-02")


def test_cycle_is_rejected() -> None:
    rows = [
        "| SCI-G4-LIV-01 | A | INTRO | C | 18 | LIV-03 | MCQ |",
        "| SCI-G4-LIV-02 | B | CORE | K | 18 | LIV-01 | MCQ |",
        "| SCI-G4-LIV-03 | C | CORE | K | 18 | LIV-02 | MCQ |",
    ]
    with pytest.raises(cs.SpineError) as exc:
        cs.build_spine({"fixture/SCI.md": _fixture_doc(rows)})
    assert any("cycle" in p for p in exc.value.problems)


def test_self_loop_is_rejected() -> None:
    rows = list(_OK_ROWS)
    rows[1] = "| SCI-G4-LIV-02 | B | CORE | K | 18 | LIV-02 | MCQ |"
    with pytest.raises(cs.SpineError, match="itself"):
        cs.build_spine({"fixture/SCI.md": _fixture_doc(rows)})


def test_dangling_prerequisite_is_rejected() -> None:
    rows = list(_OK_ROWS)
    rows[1] = "| SCI-G4-LIV-02 | B | CORE | K | 18 | LIV-09 | MCQ |"
    with pytest.raises(cs.SpineError) as exc:
        cs.build_spine({"fixture/SCI.md": _fixture_doc(rows)})
    assert any("SCI-G4-LIV-09 does not resolve" in p for p in exc.value.problems)


def test_domain_map_and_tables_must_agree() -> None:
    with pytest.raises(cs.SpineError, match="no unit-table row"):
        cs.build_spine({"fixture/SCI.md": _fixture_doc(_OK_ROWS[:2])})


def test_unknown_difficulty_is_rejected() -> None:
    rows = list(_OK_ROWS)
    rows[0] = "| SCI-G4-LIV-01 | A | EASY | C | 18 | — | MCQ |"
    with pytest.raises(cs.SpineError, match="unknown difficulty"):
        cs.build_spine({"fixture/SCI.md": _fixture_doc(rows)})


# ---------------------------------------------------------------- provenance


def test_doc_without_authored_original_declaration_is_rejected() -> None:
    with pytest.raises(cs.SpineError, match="authored-original"):
        cs.build_spine({"fixture/SCI.md": _fixture_doc(_OK_ROWS, provenance=False)})


def test_prohibited_source_is_refused_and_nothing_is_created() -> None:
    doc = _fixture_doc(_OK_ROWS, header_extra="Source: scanned PCTB textbook (e-books)")
    sp = cs.build_spine({"fixture/SCI.md": doc})
    assert sp.provenance[0].source.startswith("scanned")
    service = ci.in_memory_service()
    with pytest.raises(ProvenanceError, match="prohibited"):
        ci.ingest(sp, service)
    assert service.list() == []


# ---------------------------------------------------------------- ingest behaviour


def _assert_untouched_draft(lesson: Lesson) -> None:
    assert lesson.workflow.state is WorkflowState.DRAFT
    assert lesson.workflow.history == []
    assert lesson.quality_gate_results == []
    assert lesson.version == 0
    assert lesson.provenance.derivation is Derivation.AUTHORED_ORIGINAL
    # Nothing authored is invented: no scripts, items, hints, media, or audio pointers.
    for name in ("student_explanation", "teacher_script", "summary", "parent_notes"):
        assert getattr(lesson, name).text == {}
    assert not (lesson.hints or lesson.practice_questions or lesson.interactive_activities)
    assert not (lesson.homework or lesson.common_misconceptions or lesson.visual_concepts)
    assert not lesson.offline_package
    blob = json.dumps(lesson.to_dict(), default=str, ensure_ascii=False)
    assert 'audio_ref": {}' in blob and ".mp3" not in blob
    assert lesson.ai_teaching_object.missing_required() != []


def test_ingest_creates_one_draft_per_objective(spine: cs.Spine) -> None:
    service = ci.in_memory_service()
    result = ci.ingest(spine, service)
    assert len(result.created) == TOTAL and not result.skipped
    lessons = service.list()
    assert len(lessons) == TOTAL
    for lesson in lessons:
        _assert_untouched_draft(lesson)
    by = {lesson.lesson_id: lesson for lesson in lessons}
    nb02 = by["L-math-g4-nb-place-value"]
    assert nb02.learning_outcomes == ["MATH-G4-NB-02"]
    assert nb02.prerequisites == ["MATH-G4-NB-01"]
    assert nb02.provenance.aligned_slo_codes == ["MATH-G4-NB-02"]
    assert "unit:MATH-G4-U1" in nb02.metadata.tags


def test_ingest_is_idempotent(spine: cs.Spine) -> None:
    service = ci.in_memory_service()
    ci.ingest(spine, service)
    again = ci.ingest(spine, service)
    assert not again.created and len(again.skipped) == TOTAL
    assert len(service.list()) == TOTAL


def test_existing_lesson_for_a_code_is_skipped_untouched(spine: cs.Spine) -> None:
    """The live FR-01 lesson (any state) is never duplicated or edited."""
    service = ci.in_memory_service()
    service.create(build_fractions_lesson())
    service.submit(LESSON_KEY, "subject_author")
    service.review(LESSON_KEY, ReviewAction.APPROVE, "subject_expert")
    before = service.get(LESSON_KEY).to_dict()
    result = ci.ingest(spine, service)
    assert len(result.created) == TOTAL - 1
    (skip,) = result.skipped
    assert (skip.code, skip.existing_state) == ("MATH-G4-FR-01", "educational_qa")
    assert service.get(LESSON_KEY).to_dict() == before
    assert len(service.list()) == TOTAL


def test_lesson_id_clash_without_matching_code_fails_closed(spine: cs.Spine) -> None:
    service = ci.in_memory_service()
    impostor = build_fractions_lesson()
    impostor.lesson_id = "L-math-g4-nb-read-write"
    impostor.learning_outcomes = ["MATH-G4-ZZ-99"]
    service.create(impostor)
    with pytest.raises(cs.SpineError, match="does not carry objective"):
        ci.ingest(spine, service)
    assert len(service.list()) == 1


def test_gate_report_is_honest(spine: cs.Spine) -> None:
    _spine_text, report, rows = ci.generate(spine)
    assert len(rows) == TOTAL
    assert all(r.state == "draft" for r in rows)
    assert sum(1 for r in rows if not r.failing) == 0  # no draft is publishable
    for r in rows:
        failing = {g.gate.value for g in r.failing}
        # The five human-certified gates can only pass through review, which ingestion never does.
        assert {"technical_accuracy", "educational_review", "age_appropriateness"} <= failing
        assert {"language", "ai_safety", "accessibility", "performance"} <= failing
        assert r.blockers  # every draft is blocked from submission
    assert "Lessons passing all 9 quality gates: **0**" in report
    assert report.count("| `draft` |") == TOTAL
    assert report.endswith("\n") and not report.endswith("\n\n")


# ---------------------------------------------------------------- CLI: --dry-run / --check


def _copy_docs(dest: Path) -> Path:
    for rel in cs.default_sources():
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / rel, target)
    return dest


def test_check_detects_stale_spine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CS_DATABASE_URL", raising=False)
    root = _copy_docs(tmp_path)
    assert ci.main(["--check", "--root", str(root)]) == 1  # nothing generated yet
    assert ci.main(["--dry-run", "--root", str(root)]) == 0
    assert (root / cs.SPINE_PATH).exists() and (root / cs.REPORT_PATH).exists()
    assert ci.main(["--check", "--root", str(root)]) == 0
    # Drift: an author changes a duration in the markdown but forgets to regenerate.
    eng = root / "curriculum/grade-4/ENGLISH.md"
    text = eng.read_text(encoding="utf-8")
    edited = text.replace("letter patterns | CORE | A | 18 |", "letter patterns | CORE | A | 19 |")
    assert edited != text
    eng.write_text(edited, encoding="utf-8")
    assert ci.main(["--check", "--root", str(root)]) == 1
    # The report shows gates, not durations, so only the spine drifts here.
    assert ci.stale_artifacts(root, cs.load_spine(root)) == [cs.SPINE_PATH]


def test_inconsistent_docs_exit_nonzero(tmp_path: Path) -> None:
    root = _copy_docs(tmp_path)
    eng = root / "curriculum/grade-4/ENGLISH.md"
    eng.write_text(
        eng.read_text(encoding="utf-8").replace("| RD-03 | MCQ |", "| RD-09 | MCQ |", 1),
        encoding="utf-8",
    )
    assert ci.main(["--check", "--root", str(root)]) == 1


def test_write_mode_requires_a_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CS_DATABASE_URL", raising=False)
    assert ci.main(["--root", str(ROOT)]) == 2


# ---------------------------------------------------------------- end to end (database)


def _db_lessons(url: str) -> list[Lesson]:
    engine = create_db_engine(url)
    try:
        with unit_of_work(create_session_factory(engine)) as uow:
            return CurriculumStudioService(uow.lessons, uow.publish).list()
    finally:
        engine.dispose()


def _end_to_end(url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = _copy_docs(tmp_path)
    monkeypatch.setenv("CS_DATABASE_URL", url)
    assert ci.main(["--dry-run", "--root", str(root)]) == 0  # read-only plan
    assert _db_lessons(url) == []
    assert ci.main(["--root", str(root)]) == 0
    lessons = _db_lessons(url)
    assert len(lessons) == TOTAL
    for lesson in lessons:
        _assert_untouched_draft(lesson)
    assert ci.main(["--root", str(root)]) == 0  # idempotent re-run
    assert len(_db_lessons(url)) == TOTAL


def test_end_to_end_over_sqlite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _end_to_end(f"sqlite:///{tmp_path / 'studio.db'}", tmp_path, monkeypatch)


PG_URL = os.environ.get("CS_DATABASE_URL")


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_end_to_end_over_postgres(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    _end_to_end(PG_URL or "", tmp_path, monkeypatch)
