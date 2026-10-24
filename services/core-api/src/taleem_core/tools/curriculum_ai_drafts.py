"""AI-drafted Grade 4 lessons: one JSON file per objective in ``curriculum/grade-4/ai-drafts``.

The curriculum authoring guide allows AI to *draft* and requires humans to own, review and sign
off (``docs/10-curriculum-studio/CURRICULUM_AUTHORING_GUIDE.md`` §4). These files are such drafts.
They are a separate, labelled source from the human-authored design documents:

- The import never lets an AI draft replace human-authored text: a field the documents (or the
  FR-01 fixture) supply is taken from them; the AI draft fills only fields they leave empty.
- Every lesson that takes any field from a draft is tagged ``ai-drafted`` +
  ``content-status:ai-draft-pending-review`` and ``ai-drafted-field:<name>`` per field, so no
  report or UI can mistake it for reviewed or human-written curriculum.
- Drafts carry no audio, media or offline-package pointer (none of those assets exist), and they
  never set a review, approval or quality-gate result. Every lesson stays a draft.
- Provenance stays ``authored-original``: the drafts are original writing aligned to the
  objective's re-expressed outcome; no textbook or third-party text is used.

File format (all text fields are ``{"ur": "...", "en": "..."}``; see ``FIELDS``)::

    {
      "code": "URD-G4-GR-02",
      "title": {...}, "description": {...},
      "keywords": ["..."],
      "vocabulary": [{"term": {...}, "definition": {...}}],
      "teacher_script": {...}, "student_explanation": {...},
      "worked_examples": [{"prompt": {...}, "steps": [{...}]}],
      "interactive_activities": [ITEM], "practice_questions": [ITEM, ITEM, ITEM, ...],
      "challenge_problems": [ITEM], "homework": [ITEM],
      "hints": [{"trigger": "first_wrong", "hint": {...}}],
      "common_misconceptions": [{"misconception": {...}, "correction": {...}}],
      "adaptive_remediation": [{"signal": "...", "remediation_ref": "<objective code>"}],
      "revision_notes": {...}, "summary": {...}, "parent_notes": {...},
      "mentor_notes": {...}, "accessibility_notes": {...},
      "ai_teaching_object": {"teaching_strategy": "...", "questioning_strategy": "...",
                             "hint_policy": "...", "escalation_rules": ["..."],
                             "forbidden_behaviours": ["..."], ...},
      "review_flags": ["what a human reviewer must check first"]
    }

    ITEM = {"id": "p1", "type": "mcq", "competency": "application", "stem": {...},
            "options": [{...}], "answer_key": {"correct_option": 0},
            "accepted_variants": [], "hints": [{"trigger": "wrong", "hint": {...}}],
            "explanation": {...}, "rubric": {"criteria": "...", "max_score": 2,
                                             "levels": [{"level": 1, "descriptor": {...}}]}}

Validate the files with ``python -m taleem_core.tools.curriculum_ai_drafts [CODE ...]``.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..contexts.curriculum_studio.domain.ai_teaching import AITeachingObject
from ..contexts.curriculum_studio.domain.assessment import (
    AssessmentBlueprint,
    AssessmentItem,
    Competency,
    ItemType,
    Rubric,
    RubricLevel,
)
from ..contexts.curriculum_studio.domain.content import (
    Hint,
    Locale,
    LocalizedText,
    Misconception,
    VocabularyTerm,
    WorkedExample,
)
from ..contexts.curriculum_studio.domain.lesson import RemediationRoute
from .curriculum_spine import Objective, Spine

DRAFTS_DIR = "curriculum/grade-4/ai-drafts"
AI_TAGS: tuple[str, ...] = ("ai-drafted", "content-status:ai-draft-pending-review")
AI_FIELD_TAG = "ai-drafted-field:"

_TEXT_FIELDS = (
    "title",
    "description",
    "teacher_script",
    "student_explanation",
    "revision_notes",
    "summary",
    "parent_notes",
    "mentor_notes",
    "accessibility_notes",
)
_ITEM_FIELDS = ("interactive_activities", "practice_questions", "challenge_problems", "homework")
# Every Studio field a draft may carry, in Lesson order. ``assessment`` is derived (formative =
# practice questions), as in the FR-01 fixture.
FIELDS: tuple[str, ...] = (
    "title",
    "description",
    "keywords",
    "vocabulary",
    "teacher_script",
    "student_explanation",
    "worked_examples",
    "interactive_activities",
    "practice_questions",
    "hints",
    "common_misconceptions",
    "adaptive_remediation",
    "challenge_problems",
    "homework",
    "revision_notes",
    "summary",
    "parent_notes",
    "mentor_notes",
    "accessibility_notes",
    "ai_teaching_object",
    "assessment",
)
_ALLOWED_KEYS = (set(FIELDS) - {"assessment"}) | {"code", "review_flags"}
_OPTION_TYPES = frozenset({ItemType.MCQ, ItemType.TRUE_FALSE})
_AUDIO_MARKERS = (".mp3", ".wav", ".ogg", ".m4a", "audio/")


class AIDraftError(ValueError):
    """A draft file that does not match the format (the message names the file and path)."""


@dataclass
class AIDraft:
    code: str
    source: str  # repo-relative path of the file
    values: dict[str, Any] = field(default_factory=dict)  # Studio field name -> domain value
    review_flags: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------- parsing


class _Reader:
    def __init__(self, source: str, code: str) -> None:
        self.source, self.code = source, code

    def fail(self, where: str, msg: str) -> AIDraftError:
        return AIDraftError(f"{self.source}: {where}: {msg}")

    def text(self, raw: Any, where: str) -> LocalizedText:
        if not isinstance(raw, dict) or set(raw) - {"ur", "en"}:
            raise self.fail(where, 'expected {"ur": ..., "en": ...}')
        out: dict[Locale, str] = {}
        for tag in ("ur", "en"):
            value = raw.get(tag, "")
            if not isinstance(value, str):
                raise self.fail(where, f"{tag} must be a string")
            if any(m in value.lower() for m in _AUDIO_MARKERS):
                raise self.fail(where, "drafts may not point at audio assets")
            if value.strip():
                out[Locale(tag)] = value.strip()
        if not out:
            raise self.fail(where, "empty text")
        return LocalizedText(text=out)

    def strings(self, raw: Any, where: str) -> list[str]:
        if not isinstance(raw, list) or not all(isinstance(s, str) and s.strip() for s in raw):
            raise self.fail(where, "expected a list of non-empty strings")
        return [s.strip() for s in raw]

    def items(self, raw: Any, where: str) -> list[Any]:
        if not isinstance(raw, list) or not raw:
            raise self.fail(where, "expected a non-empty list")
        return raw

    def hint(self, raw: Any, where: str) -> Hint:
        if not isinstance(raw, dict) or not isinstance(raw.get("trigger"), str):
            raise self.fail(where, 'expected {"trigger": str, "hint": text}')
        return Hint(trigger=raw["trigger"], hint=self.text(raw.get("hint"), f"{where}.hint"))

    def assessment_item(self, raw: Any, where: str, prefix: str) -> AssessmentItem:
        if not isinstance(raw, dict) or not isinstance(raw.get("id"), str):
            raise self.fail(where, 'item needs a string "id"')
        try:
            kind = ItemType(str(raw.get("type")))
            competency = Competency(str(raw.get("competency")))
        except ValueError as exc:
            raise self.fail(where, str(exc)) from exc
        options = [
            self.text(o, f"{where}.options[{i}]") for i, o in enumerate(raw.get("options", []))
        ]
        answer_key = raw.get("answer_key", {})
        if not isinstance(answer_key, dict):
            raise self.fail(where, "answer_key must be an object")
        if kind in {ItemType.MCQ, ItemType.TRUE_FALSE}:
            correct = answer_key.get("correct_option")
            if not isinstance(correct, int) or not 0 <= correct < len(options) or len(options) < 2:
                raise self.fail(
                    where, "mcq/true_false needs >=2 options and a valid correct_option"
                )
        rubric = None
        if raw.get("rubric") is not None:
            r = raw["rubric"]
            if not isinstance(r, dict):
                raise self.fail(where, "rubric must be an object")
            rubric = Rubric(
                criteria=str(r.get("criteria", "")),
                max_score=int(r.get("max_score", 0)),
                levels=[
                    RubricLevel(
                        level=int(lv.get("level", 0)),
                        descriptor=self.text(lv.get("descriptor"), f"{where}.rubric.levels[{i}]"),
                    )
                    for i, lv in enumerate(r.get("levels", []))
                ],
            )
        item = AssessmentItem(
            item_id=f"{prefix}-{self.code.lower()}-{raw['id']}",
            type=kind,
            objective_ref=self.code,
            competency=competency,
            stem=self.text(raw.get("stem"), f"{where}.stem"),
            answer_key=answer_key,
            accepted_variants=(
                self.strings(raw.get("accepted_variants", []), where)
                if raw.get("accepted_variants")
                else []
            ),
            options=options,
            rubric=rubric,
            auto_marking_guidance=str(raw.get("auto_marking_guidance", "")),
            mentor_review_guidance=str(raw.get("mentor_review_guidance", "")),
            hints=[self.hint(h, f"{where}.hints[{i}]") for i, h in enumerate(raw.get("hints", []))],
            explanation=(
                self.text(raw["explanation"], f"{where}.explanation")
                if raw.get("explanation")
                else LocalizedText()
            ),
        )
        if item.needs_rubric() and (rubric is None or not rubric.levels):
            raise self.fail(where, f"{kind.value} items need a rubric with levels")
        return item

    def ai_teaching(self, raw: Any, where: str) -> AITeachingObject:
        if not isinstance(raw, dict):
            raise self.fail(where, "expected an object")
        obj = AITeachingObject(
            learning_goals=[self.code],
            teaching_strategy=str(raw.get("teaching_strategy", "")),
            questioning_strategy=str(raw.get("questioning_strategy", "")),
            slow_down_signals=(
                self.strings(raw.get("slow_down_signals", []), where)
                if raw.get("slow_down_signals")
                else []
            ),
            hint_policy=str(raw.get("hint_policy", "")),
            example_policy=str(raw.get("example_policy", "")),
            misconception_detectors=(
                self.strings(raw.get("misconception_detectors", []), where)
                if raw.get("misconception_detectors")
                else []
            ),
            critical_thinking_prompts=(
                self.strings(raw.get("critical_thinking_prompts", []), where)
                if raw.get("critical_thinking_prompts")
                else []
            ),
            personalization_rules=str(raw.get("personalization_rules", "")),
            escalation_rules=self.strings(raw.get("escalation_rules", []), where),
            forbidden_behaviours=self.strings(raw.get("forbidden_behaviours", []), where),
        )
        missing = obj.missing_required()
        if missing:
            raise self.fail(where, "missing " + ", ".join(missing))
        return obj


def parse_draft(raw: Any, source: str, objective: Objective, known_codes: set[str]) -> AIDraft:
    """Turn one file's JSON into Studio field values (raises ``AIDraftError`` on any mismatch)."""
    if not isinstance(raw, dict):
        raise AIDraftError(f"{source}: expected a JSON object")
    if raw.get("code") != objective.code:
        raise AIDraftError(f"{source}: code {raw.get('code')!r} != file objective {objective.code}")
    unknown = set(raw) - _ALLOWED_KEYS
    if unknown:
        raise AIDraftError(f"{source}: unknown field(s) {sorted(unknown)}")
    r = _Reader(source, objective.code)
    v: dict[str, Any] = {}
    for name in _TEXT_FIELDS:
        if name in raw:
            v[name] = r.text(raw[name], name)
    if "keywords" in raw:
        v["keywords"] = r.strings(raw["keywords"], "keywords")
    if "vocabulary" in raw:
        v["vocabulary"] = [
            VocabularyTerm(
                term=r.text(t.get("term"), f"vocabulary[{i}].term"),
                definition=r.text(t.get("definition"), f"vocabulary[{i}].definition"),
            )
            for i, t in enumerate(r.items(raw["vocabulary"], "vocabulary"))
        ]
    if "worked_examples" in raw:
        v["worked_examples"] = [
            WorkedExample(
                prompt=r.text(w.get("prompt"), f"worked_examples[{i}].prompt"),
                steps=[
                    r.text(s, f"worked_examples[{i}].steps[{j}]")
                    for j, s in enumerate(r.items(w.get("steps"), f"worked_examples[{i}].steps"))
                ],
            )
            for i, w in enumerate(r.items(raw["worked_examples"], "worked_examples"))
        ]
    prefixes = {
        "interactive_activities": "ai-a",
        "practice_questions": "ai-p",
        "challenge_problems": "ai-c",
        "homework": "ai-hw",
    }
    for name in _ITEM_FIELDS:
        if name in raw:
            v[name] = [
                r.assessment_item(x, f"{name}[{i}]", prefixes[name])
                for i, x in enumerate(r.items(raw[name], name))
            ]
    # The learner runtime scores practice by the chosen option only (``learning.domain.scorer``):
    # a fill-blank/matching/ordering/short item there could never be answered. Those types belong
    # in interactive_activities / challenge_problems until the activity runtime exists.
    unplayable = [i.item_id for i in v.get("practice_questions", []) if i.type not in _OPTION_TYPES]
    if unplayable:
        raise AIDraftError(
            f"{source}: practice_questions must be mcq/true_false (the runtime scores a chosen "
            f"option); move {unplayable} to interactive_activities"
        )
    ids = [i.item_id for name in _ITEM_FIELDS for i in v.get(name, [])]
    if len(ids) != len(set(ids)):
        raise AIDraftError(f"{source}: duplicate item ids")
    if "hints" in raw:
        v["hints"] = [
            r.hint(h, f"hints[{i}]") for i, h in enumerate(r.items(raw["hints"], "hints"))
        ]
    if "common_misconceptions" in raw:
        v["common_misconceptions"] = [
            Misconception(
                misconception=r.text(m.get("misconception"), f"common_misconceptions[{i}]"),
                correction=r.text(m.get("correction"), f"common_misconceptions[{i}].correction"),
            )
            for i, m in enumerate(r.items(raw["common_misconceptions"], "common_misconceptions"))
        ]
    if "adaptive_remediation" in raw:
        routes = []
        for i, a in enumerate(r.items(raw["adaptive_remediation"], "adaptive_remediation")):
            ref = a.get("remediation_ref") if isinstance(a, dict) else None
            if ref not in known_codes:
                raise r.fail(f"adaptive_remediation[{i}]", f"unknown objective {ref!r}")
            routes.append(RemediationRoute(signal=str(a.get("signal", "")), remediation_ref=ref))
        v["adaptive_remediation"] = routes
    if "ai_teaching_object" in raw:
        v["ai_teaching_object"] = r.ai_teaching(raw["ai_teaching_object"], "ai_teaching_object")
    if "practice_questions" in v:
        v["assessment"] = AssessmentBlueprint(formative=list(v["practice_questions"]))
    flags = r.strings(raw["review_flags"], "review_flags") if raw.get("review_flags") else []
    return AIDraft(objective.code, source, v, flags)


def _load_one(path: Path, spine: Spine) -> AIDraft:
    by_code = spine.by_code()
    code = path.stem
    rel = f"{DRAFTS_DIR}/{path.name}"
    if code not in by_code:
        raise AIDraftError(f"{rel}: no objective {code} in the spine")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AIDraftError(f"{rel}: invalid JSON: {exc}") from exc
    return parse_draft(raw, rel, by_code[code], set(by_code))


def load_drafts(root: Path, spine: Spine, codes: Sequence[str] | None = None) -> dict[str, AIDraft]:
    """Draft files under ``root/DRAFTS_DIR`` (only ``codes`` when given); any bad file is an
    error, including a file for an objective the spine does not have."""
    folder = root / DRAFTS_DIR
    if not folder.is_dir():
        return {}
    paths = sorted(folder.glob("*.json"))
    if codes is not None:
        paths = [p for p in paths if p.stem in set(codes)]
    return {p.stem: _load_one(p, spine) for p in paths}


# --------------------------------------------------------------------------------- CLI


def _check(root: Path, codes: Sequence[str]) -> int:
    """Parse the drafts, merge them as the ingest would, and print what still blocks each lesson."""
    from .curriculum_ingest import generate_service, load_inputs

    spine, contents = load_inputs(root)
    drafts = load_drafts(root, spine, codes or None)
    service, lesson_ids = generate_service(spine, contents, drafts)
    expected = {"offline_package", "visual_concepts"}
    bad = 0
    for code in codes or sorted(drafts):
        if code not in drafts:
            print(f"{code}: no draft file")
            bad += 1
            continue
        result = service.validate(lesson_ids[code])
        blockers = sorted(
            {f.field or f.message for f in result.structural if f.severity.value == "blocker"}
            - expected
        )
        readable = next(g for g in result.gate_results if g.gate.value == "readability")
        problems = blockers + [f.message for f in readable.findings]
        print(f"{code}: {'ok' if not problems else '; '.join(problems)}")
        bad += bool(problems)
    return 1 if bad else 0


def main(argv: Sequence[str] | None = None) -> int:
    from .curriculum_ingest import DEFAULT_ROOT

    parser = argparse.ArgumentParser(
        prog="python -m taleem_core.tools.curriculum_ai_drafts",
        description="validate AI-drafted Grade 4 lesson files",
    )
    parser.add_argument("codes", nargs="*", help="objective codes (default: every draft)")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT, help="repository root")
    args = parser.parse_args(argv)
    try:
        return _check(args.root, args.codes)
    except AIDraftError as exc:
        print(f"error: {exc}")
        return 2


def draft_fields(drafts: Mapping[str, AIDraft], code: str) -> dict[str, Any]:
    d = drafts.get(code)
    return dict(d.values) if d is not None else {}


__all__ = [
    "AI_FIELD_TAG",
    "AI_TAGS",
    "AIDraft",
    "AIDraftError",
    "DRAFTS_DIR",
    "FIELDS",
    "draft_fields",
    "load_drafts",
    "parse_draft",
]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
