"""AI-drafted Grade 4 lesson content (``curriculum/grade-4/ai-drafts``).

Covers the file format (every malformed shape is refused with the file and path named), the merge
rule (human text always wins; a draft fills only empty fields and the missing language of a
one-language human field), the labelling (``ai-drafted`` tags per lesson and per field),
idempotency and author-edit protection, and the committed drafts themselves: all parse, none
points at an asset, and every lesson they complete is blocked only by the assets that do not exist.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from taleem_core.contexts.curriculum_studio.domain.content import Locale, LocalizedText
from taleem_core.contexts.curriculum_studio.domain.provenance import Derivation
from taleem_core.contexts.curriculum_studio.domain.workflow import WorkflowState
from taleem_core.tools import curriculum_ai_drafts as cad
from taleem_core.tools import curriculum_content as cc
from taleem_core.tools import curriculum_import as cimp
from taleem_core.tools import curriculum_ingest as ci
from taleem_core.tools import curriculum_spine as cs

ROOT = Path(__file__).resolve().parents[3]
UR, EN = Locale.UR, Locale.EN
SAMPLE = "MATH-G4-NB-02"
ASSET_BLOCKERS = {"offline_package", "visual_concepts"}


@pytest.fixture(scope="module")
def spine() -> cs.Spine:
    return cs.load_spine(ROOT)


@pytest.fixture(scope="module")
def contents() -> dict[str, cc.AuthoredContent]:
    return cc.parse_authored_content(cs.read_docs(ROOT))


@pytest.fixture(scope="module")
def drafts(spine: cs.Spine) -> dict[str, cad.AIDraft]:
    return cad.load_drafts(ROOT, spine)


def _raw(code: str = SAMPLE) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (ROOT / cad.DRAFTS_DIR / f"{code}.json").read_text(encoding="utf-8")
    )
    return data


def _parse(spine: cs.Spine, raw: dict[str, Any]) -> cad.AIDraft:
    by_code = spine.by_code()
    return cad.parse_draft(raw, "test.json", by_code[SAMPLE], set(by_code))


# ---------------------------------------------------------------- format


def test_sample_parses_into_studio_fields(spine: cs.Spine) -> None:
    d = _parse(spine, _raw())
    assert d.code == SAMPLE
    assert d.values["student_explanation"].text[UR].startswith("ہر ہندسے کا ایک گھر")
    items = d.values["practice_questions"]
    assert len(items) >= 3
    assert all(i.objective_ref == SAMPLE for i in items)
    assert all(i.item_id.startswith(f"ai-p-{SAMPLE.lower()}-") for i in items)
    assert d.values["assessment"].formative == items
    assert d.values["ai_teaching_object"].learning_goals == [SAMPLE]
    assert d.review_flags


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda r: r.update(code="MATH-G4-NB-03"), "code"),
        (lambda r: r.update(visual_concepts=[]), "unknown field"),
        (lambda r: r.update(offline_package="pkg/x"), "unknown field"),
        (lambda r: r["summary"].update(ur="سنیں audio/ur/x.mp3"), "audio"),
        (lambda r: r.update(summary={"ur": "", "en": " "}), "empty text"),
        (lambda r: r.update(summary={"fr": "x"}), "ur"),
        (lambda r: r["practice_questions"][0]["answer_key"].update(correct_option=7), "mcq"),
        (lambda r: r["practice_questions"][0].update(type="essay"), "essay"),
        (lambda r: r["practice_questions"][1].update(id=r["practice_questions"][0]["id"]), "dup"),
        (lambda r: r["challenge_problems"][0].update(type="long"), "rubric"),
        (lambda r: r["adaptive_remediation"][0].update(remediation_ref="MATH-G4-ZZ-99"), "unknown"),
        (lambda r: r["ai_teaching_object"].update(forbidden_behaviours=[]), "forbidden"),
        (lambda r: r["ai_teaching_object"].pop("hint_policy"), "hint_policy"),
    ],
)
def test_malformed_drafts_are_refused(spine: cs.Spine, mutate: Any, message: str) -> None:
    raw = copy.deepcopy(_raw())
    mutate(raw)
    with pytest.raises(cad.AIDraftError, match=message):
        _parse(spine, raw)


def test_file_for_unknown_objective_is_refused(tmp_path: Path, spine: cs.Spine) -> None:
    folder = tmp_path / cad.DRAFTS_DIR
    folder.mkdir(parents=True)
    (folder / "MATH-G4-ZZ-99.json").write_text("{}", encoding="utf-8")
    with pytest.raises(cad.AIDraftError, match="no objective"):
        cad.load_drafts(tmp_path, spine)
    (folder / "MATH-G4-ZZ-99.json").unlink()
    (folder / f"{SAMPLE}.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(cad.AIDraftError, match="invalid JSON"):
        cad.load_drafts(tmp_path, spine)
    assert cad.load_drafts(tmp_path / "nowhere", spine) == {}


# ---------------------------------------------------------------- merge + labelling


def _run(
    spine: cs.Spine, contents: dict[str, cc.AuthoredContent], drafts: dict[str, cad.AIDraft]
) -> tuple[ci.CurriculumStudioService, ci.RunResult]:
    service = ci.in_memory_service()
    return service, ci.run(spine, contents, service, drafts)


def _lesson(service: ci.CurriculumStudioService, code: str) -> Any:
    return next(x for x in service.list() if x.learning_outcomes == [code])


def test_human_text_wins_and_drafts_fill_only_gaps(
    spine: cs.Spine, contents: dict[str, cc.AuthoredContent]
) -> None:
    draft = _parse(spine, _raw())
    # The draft also offers fields the math document already supplies.
    draft.values["hints"] = copy.deepcopy(draft.values["practice_questions"][0].hints)
    draft.values["parent_notes"] = LocalizedText(text={UR: "AI اردو", EN: "AI English"})
    service, result = _run(spine, contents, {SAMPLE: draft})
    lesson = _lesson(service, SAMPLE)
    human = cimp.doc_fields(spine.by_code()[SAMPLE], contents[SAMPLE])
    assert lesson.hints == human["hints"]  # the document's hint ladder, not the draft's
    assert lesson.vocabulary == human["vocabulary"]
    # The document wrote the parent note in English only: English stays verbatim, Urdu is drafted.
    assert lesson.parent_notes.text[EN] == human["parent_notes"].text[EN]
    assert lesson.parent_notes.text[UR] == "AI اردو"
    assert lesson.student_explanation == draft.values["student_explanation"]
    entry = result.imports.by_code()[SAMPLE]
    assert "parent_notes" in entry.ai_drafted and "student_explanation" in entry.ai_drafted
    assert "hints" not in entry.ai_drafted and "vocabulary" not in entry.ai_drafted
    tags = lesson.metadata.tags
    assert set(cad.AI_TAGS) <= set(tags) and set(cimp.PROVISIONAL_TAGS) <= set(tags)
    assert {t for t in tags if t.startswith(cad.AI_FIELD_TAG)} == {
        f"{cad.AI_FIELD_TAG}{n}" for n in entry.ai_drafted
    }
    assert f"{cimp.SOURCE_TAG}test.json (AI draft)" in tags
    assert lesson.workflow.state is WorkflowState.DRAFT and lesson.quality_gate_results == []


def test_lesson_without_a_draft_is_not_labelled_ai(
    spine: cs.Spine, contents: dict[str, cc.AuthoredContent]
) -> None:
    service, _ = _run(spine, contents, {SAMPLE: _parse(spine, _raw())})
    other = _lesson(service, "MATH-G4-NB-01")
    assert not set(cad.AI_TAGS) & set(other.metadata.tags)
    assert not any(t.startswith(cad.AI_FIELD_TAG) for t in other.metadata.tags)


def test_draft_import_is_idempotent_and_keeps_author_edits(
    spine: cs.Spine, contents: dict[str, cc.AuthoredContent]
) -> None:
    drafts = {SAMPLE: _parse(spine, _raw())}
    service, _ = _run(spine, contents, drafts)
    again = ci.run(spine, contents, service, drafts)
    assert not again.imports.by_code()[SAMPLE].imported
    lesson = _lesson(service, SAMPLE)
    lesson.summary = LocalizedText(text={UR: "مصنف کا خلاصہ", EN: "author's summary"})
    service.update(lesson)
    third = ci.run(spine, contents, service, drafts)
    assert "summary" in third.imports.by_code()[SAMPLE].author_edited
    assert _lesson(service, SAMPLE).summary.text[EN] == "author's summary"


# ---------------------------------------------------------------- the committed drafts


def test_committed_drafts_parse_and_point_at_no_asset(drafts: dict[str, cad.AIDraft]) -> None:
    assert SAMPLE in drafts
    for code, d in drafts.items():
        assert d.source == f"{cad.DRAFTS_DIR}/{code}.json"
        blob = json.dumps(cimp._jsonable(d.values), ensure_ascii=False).lower()
        assert ".mp3" not in blob and 'audio_ref": {"' not in blob


def test_committed_drafts_complete_their_lessons_except_assets(
    spine: cs.Spine, contents: dict[str, cc.AuthoredContent], drafts: dict[str, cad.AIDraft]
) -> None:
    """A drafted lesson is blocked only by the media and offline package that do not exist yet,
    and still fails every human-certified gate: AI text is never reviewed curriculum."""
    service, lesson_ids = ci.generate_service(spine, contents, drafts)
    for code in drafts:
        lesson = service.get(lesson_ids[code])
        assert lesson.provenance.derivation is Derivation.AUTHORED_ORIGINAL
        assert lesson.workflow.state is WorkflowState.DRAFT
        result = service.validate(lesson.lesson_id)
        blockers = {f.field for f in result.structural if f.severity.value == "blocker"}
        assert blockers <= ASSET_BLOCKERS, (code, blockers - ASSET_BLOCKERS)
        readability = next(g for g in result.gate_results if g.gate.value == "readability")
        assert readability.passed, (code, [f.message for f in readability.findings])
        assert not lesson.visual_concepts and not lesson.offline_package
        assert lesson.student_explanation.audio_ref == {}


def test_report_counts_ai_drafts_separately(
    spine: cs.Spine, contents: dict[str, cc.AuthoredContent], drafts: dict[str, cad.AIDraft]
) -> None:
    _spine_text, report, rows = ci.generate(spine, contents, drafts)
    assert sum(1 for r in rows if not r.failing) == 0  # still nothing publishable
    assert f"- Drafts carrying **AI-drafted** content: **{len(drafts)}**" in report
    assert "Lessons passing all 9 quality gates: **0**" in report
    assert "**(AI)**" in report


def test_cli_validates_named_codes(capsys: pytest.CaptureFixture[str]) -> None:
    assert cad.main([SAMPLE, "--root", str(ROOT)]) == 0
    assert f"{SAMPLE}: ok" in capsys.readouterr().out
    assert cad.main(["MATH-G4-ZZ-99", "--root", str(ROOT)]) == 1
