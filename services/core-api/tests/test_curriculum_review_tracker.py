"""Grade 4 review tracker (``curriculum/grade-4/review``), generated from the AI draft files.

The committed tracker must match the drafts (so it cannot drift), carry the AI-draft banner, count
exactly the flags the files hold, and never show any status other than ``ai-draft-unreviewed``.
"""

from __future__ import annotations

import csv
import io
import json
import shutil
from pathlib import Path

import pytest

from taleem_core.contexts.curriculum_studio.domain.workflow import STATE_ROLE
from taleem_core.tools import curriculum_review_tracker as crt

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def tracker() -> crt.Tracker:
    return crt.load(ROOT)


def _draft_files() -> list[Path]:
    return sorted((ROOT / crt.DRAFTS_DIR).glob("*.json"))


def test_committed_outputs_are_fresh() -> None:
    for rel, text in crt.outputs(ROOT).items():
        assert (ROOT / rel).read_text(
            encoding="utf-8"
        ) == text, f"{rel} is stale: run python -m taleem_core.tools.curriculum_review_tracker"
    assert crt.main(["--check", "--root", str(ROOT)]) == 0


def test_render_is_deterministic() -> None:
    assert crt.outputs(ROOT) == crt.outputs(ROOT)


def test_every_output_starts_with_the_banner() -> None:
    for text in crt.outputs(ROOT).values():
        assert crt.BANNER in text.splitlines()[0]


def test_counts_match_the_draft_files(tracker: crt.Tracker) -> None:
    files = _draft_files()
    flags = sum(len(json.loads(p.read_text(encoding="utf-8"))["review_flags"]) for p in files)
    assert len(tracker.rows) == len(files)
    assert sum(len(r.flags) for r in tracker.rows) == flags
    rows = list(csv.reader(io.StringIO(crt.render_csv(tracker))))
    assert rows[1] == list(crt.CSV_COLUMNS)
    assert len(rows) - 2 == flags
    assert not tracker.problems


def test_nothing_is_ever_marked_reviewed(tracker: crt.Tracker) -> None:
    assert {r.status for r in tracker.rows} == {"ai-draft-unreviewed"}
    rows = list(csv.DictReader(io.StringIO(crt.render_csv(tracker).split("\n", 1)[1])))
    assert {r["objective_status"] for r in rows} == {"ai-draft-unreviewed"}
    assert {r["flag_status"] for r in rows} == {"open"}
    assert all(not r["reviewer"] and not r["decision"] and not r["date"] for r in rows)


def test_studio_roles_come_from_the_workflow() -> None:
    assert set(crt.STUDIO_ROLES) == set(STATE_ROLE.values())
    assert len(crt.STUDIO_ROLES) == 5


def test_every_islamiat_lesson_needs_a_scholar(tracker: crt.Tracker) -> None:
    isl = [r for r in tracker.rows if r.prefix == "ISL"]
    assert isl
    assert all(r.scholar_required for r in isl)
    assert all(not r.scholar_required for r in tracker.rows if r.prefix != "ISL")
    assert sum(r.placeholders for r in isl) > 0


@pytest.mark.parametrize(
    ("text", "lanes"),
    [
        ("subject expert: check the sum", ("subject_expert",)),
        ("language editor: Urdu term", ("language_editor",)),
        ("Urdu terminology: confirm", ("language_editor",)),
        ("scholar (religious subject expert) review REQUIRED: supply text", ("scholar",)),
        ("SAFEGUARDING REVIEWER: whole lesson", ("safeguarding",)),
        ("child-safety + subject expert: road steps", ("subject_expert", "safety_officer")),
        ("interaction contract: a1 is a bespoke widget", ("instructional_designer",)),
        ("illustration reviewer: no depiction", ("a11y_specialist",)),
        ("audio: the story must be recorded", ("a11y_specialist",)),
        ("check the arrow renders right-to-left", ("a11y_specialist",)),
        ("check the sandwich chunking", ("subject_expert",)),
    ],
)
def test_route_flag(text: str, lanes: tuple[str, ...]) -> None:
    assert crt.route_flag(text) == lanes


def test_data_problems_are_reported(tmp_path: Path) -> None:
    shutil.copytree(ROOT / "curriculum/grade-4/ai-drafts", tmp_path / crt.DRAFTS_DIR)
    shutil.copy(ROOT / crt.SPINE, tmp_path / crt.SPINE)
    drafts = tmp_path / crt.DRAFTS_DIR
    (drafts / "MATH-G4-NB-01.json").unlink()
    isl = drafts / "ISL-G4-AKH-01.json"
    data = json.loads(isl.read_text(encoding="utf-8"))
    data["review_flags"] = ["subject expert: one", "subject expert: one"]
    isl.write_text(json.dumps(data), encoding="utf-8")
    (drafts / "XYZ-G4-AA-01.json").write_text('{"code": "XYZ-G4-AA-01"}', encoding="utf-8")

    problems = "\n".join(crt.load(tmp_path).problems)
    assert "`MATH-G4-NB-01`: in the spine but has no draft file" in problems
    assert "`ISL-G4-AKH-01`: flag repeated 2 times" in problems
    assert "`ISL-G4-AKH-01`: Islamiat draft has no scholar flag" in problems
    assert "`XYZ-G4-AA-01.json`: draft file for an objective not in the spine" in problems
    assert crt.main(["--check", "--root", str(tmp_path)]) == 1
