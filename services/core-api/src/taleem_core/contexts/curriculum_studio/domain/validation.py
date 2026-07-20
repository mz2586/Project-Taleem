"""Lesson validator (pure-stdlib): structural + provenance + automated quality-gate pre-checks.

Runs on `:validate` before human review, so reviewers see complete, clean
lessons. See docs/10-curriculum-studio/QUALITY_ASSURANCE_STANDARD.md §2 and LESSON_STANDARD.md §2.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .content import Difficulty, Locale
from .hierarchy import is_valid_grade_subject
from .lesson import Lesson
from .provenance import check_provenance
from .quality import Finding, Gate, GateResult, Severity

# Readability: max average words/sentence by grade band (CONTENT_STYLE_GUIDE §2).
READABILITY_MAX_WORDS: dict[str, int] = {
    "KG": 8,
    "G1": 8,
    "G2": 8,
    "G3": 8,
    "G4": 12,
    "G5": 12,
    "G6": 16,
    "G7": 16,
    "G8": 16,
    "G9": 20,
    "G10": 20,
}

_SENTENCE_SPLIT = re.compile(r"[.!?۔]+")


def _avg_words_per_sentence(text: str) -> float:
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    if not sentences:
        return 0.0
    total_words = sum(len(s.split()) for s in sentences)
    return total_words / len(sentences)


@dataclass
class ValidationResult:
    structural: list[Finding] = field(default_factory=list)
    gate_results: list[GateResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        no_blocking_structural = not any(f.severity is Severity.BLOCKER for f in self.structural)
        gates_ok = all(g.passed for g in self.gate_results)
        return no_blocking_structural and gates_ok


def _blk(msg: str, field_name: str = "") -> Finding:
    return Finding(Severity.BLOCKER, msg, field_name)


def _structural_findings(lesson: Lesson) -> list[Finding]:
    f: list[Finding] = []
    if not lesson.title.is_complete_core():
        f.append(_blk("title requires Urdu + English", "title"))
    if not lesson.learning_outcomes:
        f.append(_blk("at least one learning outcome (SLO) required", "learning_outcomes"))
    if not 5 <= lesson.estimated_duration_min <= 40:
        f.append(_blk("estimated_duration_min must be 5-40", "estimated_duration_min"))
    if not lesson.keywords:
        f.append(_blk("keywords required", "keywords"))
    if not lesson.student_explanation.is_complete_core():
        f.append(_blk("student_explanation requires Urdu + English", "student_explanation"))
    if not lesson.teacher_script.is_complete_core():
        f.append(_blk("teacher_script requires Urdu + English", "teacher_script"))
    if lesson.difficulty is not Difficulty.INTRO and not lesson.worked_examples:
        f.append(_blk("worked_examples required for developing+", "worked_examples"))
    if not lesson.visual_concepts:
        f.append(_blk("at least one visual concept required", "visual_concepts"))
    if not lesson.interactive_activities:
        f.append(_blk("at least one interactive activity required", "interactive_activities"))
    if len(lesson.practice_questions) < 3:
        f.append(_blk("at least 3 practice questions required", "practice_questions"))
    if not lesson.hints:
        f.append(_blk("hints required", "hints"))
    if not lesson.common_misconceptions:
        f.append(_blk("at least one misconception required", "common_misconceptions"))
    if not lesson.adaptive_remediation:
        f.append(_blk("at least one remediation route required", "adaptive_remediation"))
    if not lesson.homework:
        f.append(_blk("homework required", "homework"))
    for name in (
        "revision_notes",
        "summary",
        "parent_notes",
        "mentor_notes",
        "accessibility_notes",
    ):
        if not getattr(lesson, name).is_complete_core():
            f.append(_blk(f"{name} requires Urdu + English", name))
    if not lesson.offline_package.strip():
        f.append(_blk("offline_package required", "offline_package"))
    # Provenance gate.
    for msg in check_provenance(lesson.provenance):
        f.append(_blk(msg, "provenance"))
    # AI teaching object completeness.
    missing = lesson.ai_teaching_object.missing_required()
    if missing:
        f.append(_blk("ai_teaching_object missing: " + ", ".join(missing), "ai_teaching_object"))
    return f


def _gate(gate: Gate, findings: list[Finding]) -> GateResult:
    return GateResult(gate=gate, passed=not findings, mode="auto", findings=findings)


def _alignment_gate(lesson: Lesson) -> GateResult:
    f: list[Finding] = []
    if not is_valid_grade_subject(lesson.metadata.grade_key, lesson.metadata.subject_key):
        f.append(
            _blk(
                f"invalid grade-subject: {lesson.metadata.grade_key}/{lesson.metadata.subject_key}"
            )
        )
    if any(not code.strip() for code in lesson.learning_outcomes):
        f.append(_blk("every learning outcome needs a non-empty standard_code"))
    overlap = set(lesson.prerequisites) & set(lesson.learning_outcomes)
    if overlap:
        f.append(_blk(f"prerequisite cannot equal an outcome (cycle): {sorted(overlap)}"))
    return _gate(Gate.CURRICULUM_ALIGNMENT, f)


def _accessibility_gate(lesson: Lesson) -> GateResult:
    f: list[Finding] = []
    for i, mv in enumerate(lesson.visual_concepts):
        if not any(v.strip() for v in mv.alt_text.text.values()):
            f.append(_blk(f"visual concept {i} missing alt text", "visual_concepts"))
    if not lesson.student_explanation.has_urdu_audio():
        f.append(
            _blk(
                "student_explanation missing recorded Urdu audio (mandatory)", "student_explanation"
            )
        )
    return _gate(Gate.ACCESSIBILITY, f)


def _readability_gate(lesson: Lesson) -> GateResult:
    f: list[Finding] = []
    max_words = READABILITY_MAX_WORDS.get(lesson.metadata.grade_key, 20)
    ur = lesson.student_explanation.text.get(Locale.UR, "")
    avg = _avg_words_per_sentence(ur)
    if avg > max_words:
        f.append(_blk(f"avg sentence length {avg:.1f} exceeds grade max {max_words}"))
    return _gate(Gate.READABILITY, f)


def _performance_gate(lesson: Lesson) -> GateResult:
    f: list[Finding] = []
    if not lesson.offline_package.strip():
        f.append(_blk("offline package required for performance/offline budget"))
    return _gate(Gate.PERFORMANCE, f)


def validate(lesson: Lesson) -> ValidationResult:
    """Run structural + provenance + automated gate pre-checks."""
    return ValidationResult(
        structural=_structural_findings(lesson),
        gate_results=[
            _alignment_gate(lesson),
            _accessibility_gate(lesson),
            _readability_gate(lesson),
            _performance_gate(lesson),
        ],
    )
