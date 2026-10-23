"""Lesson validator (pure-stdlib): structural + provenance + automated quality-gate pre-checks.

Runs on `:validate` before human review, so reviewers see complete, clean
lessons. See docs/10-curriculum-studio/QUALITY_ASSURANCE_STANDARD.md §2 and LESSON_STANDARD.md §2.

Every market-specific rule — valid grade/subject, which locales a core field must be complete in,
which need recorded audio, and readability limits — comes from the lesson's curriculum pack and
instructional locale(s) (packs.py). A lesson whose pack or instructional locale cannot be resolved
gets BLOCKER findings in every pack-dependent check: an unknown rule set never passes silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .audio import SYNTHETIC_FIXTURE_AUDIO, AudioAssetResolver
from .content import Difficulty, LocalizedText
from .hierarchy import EducationSystem, placement_errors
from .lesson import Lesson
from .packs import CurriculumPack, InstructionRules, PackRegistry, default_pack, default_registry
from .provenance import check_provenance
from .quality import Finding, Gate, GateResult, Severity


def __getattr__(name: str) -> object:
    # Lazy compatibility: readability limits are now curriculum-pack data (PK-NCP, Urdu).
    if name == "READABILITY_MAX_WORDS":
        return dict(default_pack().readability[default_pack().language_of_instruction].max_words)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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


@dataclass(frozen=True)
class _PackContext:
    """The lesson's resolved pack + effective instruction rules (``rules`` None = unresolved)."""

    pack: CurriculumPack | None
    rules: InstructionRules | None
    error: str = ""

    def unresolved(self) -> str:
        return f"{self.error}: pack rules cannot be applied (blocked)"

    def required_names(self) -> str:
        if self.pack is None or self.rules is None:
            return ""
        return " + ".join(self.pack.locale_name(t) for t in self.rules.required_locales)


def _resolve(lesson: Lesson, registry: PackRegistry) -> _PackContext:
    pack_id = lesson.metadata.curriculum_pack
    pack = registry.get(pack_id)
    if pack is None:
        return _PackContext(None, None, f"unknown curriculum pack {pack_id!r}")
    declared = lesson.metadata.instructional_locales
    unknown = [str(t) for t in declared if t not in pack.instructional_locales]
    if unknown:
        msg = f"instructional locale(s) {unknown} not offered by curriculum pack {pack_id}"
        return _PackContext(pack, None, msg)
    return _PackContext(pack, pack.rules_for(lesson.metadata.instructional_locales))


def _structural_findings(lesson: Lesson, ctx: _PackContext) -> list[Finding]:
    f: list[Finding] = []
    if ctx.rules is None:
        f.append(_blk(ctx.unresolved(), "metadata"))

    def complete(name: str, text: LocalizedText) -> None:
        if ctx.rules is not None and not text.is_complete_in(ctx.rules.required_locales):
            f.append(_blk(f"{name} requires {ctx.required_names()}", name))

    complete("title", lesson.title)
    if not lesson.learning_outcomes:
        f.append(_blk("at least one learning outcome (SLO) required", "learning_outcomes"))
    if not 5 <= lesson.estimated_duration_min <= 40:
        f.append(_blk("estimated_duration_min must be 5-40", "estimated_duration_min"))
    if not lesson.keywords:
        f.append(_blk("keywords required", "keywords"))
    complete("student_explanation", lesson.student_explanation)
    complete("teacher_script", lesson.teacher_script)
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
        complete(name, getattr(lesson, name))
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
    # A gate fails on any BLOCKER; lower-severity findings are reported without failing it.
    passed = not any(f.severity is Severity.BLOCKER for f in findings)
    return GateResult(gate=gate, passed=passed, mode="auto", findings=findings)


def _alignment_gate(
    lesson: Lesson, ctx: _PackContext, hierarchy: EducationSystem | None
) -> GateResult:
    f: list[Finding] = []
    if ctx.pack is None or ctx.rules is None:
        f.append(_blk(ctx.unresolved()))
    if ctx.pack is not None and not ctx.pack.is_valid_grade_subject(
        lesson.metadata.grade_key, lesson.metadata.subject_key
    ):
        f.append(
            _blk(
                f"invalid grade-subject: {lesson.metadata.grade_key}/{lesson.metadata.subject_key}"
            )
        )
    if ctx.pack is not None:
        foreign = [str(t) for t in lesson.metadata.languages if not ctx.pack.supports_locale(t)]
        if foreign:
            f.append(
                _blk(
                    f"language(s) {foreign} not declared by curriculum pack {ctx.pack.pack_id}",
                    "metadata",
                )
            )
    if ctx.pack is not None:
        meta = lesson.metadata
        if not meta.chapter_key and not meta.topic_key:
            # Unplaced is allowed for now, but reported (non-blocking).
            f.append(
                Finding(
                    Severity.MINOR,
                    "lesson is not placed in the curriculum hierarchy (no chapter/topic)",
                    "metadata",
                )
            )
        for msg in placement_errors(
            hierarchy,
            pack_id=ctx.pack.pack_id,
            grade_key=meta.grade_key,
            subject_key=meta.subject_key,
            chapter_key=meta.chapter_key,
            topic_key=meta.topic_key,
        ):
            f.append(_blk(msg, "metadata"))
    if any(not code.strip() for code in lesson.learning_outcomes):
        f.append(_blk("every learning outcome needs a non-empty standard_code"))
    overlap = set(lesson.prerequisites) & set(lesson.learning_outcomes)
    if overlap:
        f.append(_blk(f"prerequisite cannot equal an outcome (cycle): {sorted(overlap)}"))
    return _gate(Gate.CURRICULUM_ALIGNMENT, f)


def _accessibility_gate(
    lesson: Lesson, ctx: _PackContext, audio_assets: AudioAssetResolver
) -> GateResult:
    f: list[Finding] = []
    for i, mv in enumerate(lesson.visual_concepts):
        if not any(v.strip() for v in mv.alt_text.text.values()):
            f.append(_blk(f"visual concept {i} missing alt text", "visual_concepts"))
    if ctx.pack is None or ctx.rules is None:
        f.append(_blk(ctx.unresolved(), "student_explanation"))
    else:
        for loc in ctx.rules.audio_required_locales:
            name = ctx.pack.locale_name(loc)
            if not lesson.student_explanation.has_audio(loc):
                f.append(
                    _blk(
                        f"student_explanation missing recorded {name} audio (mandatory)",
                        "student_explanation",
                    )
                )
                continue
            # A non-empty ref is not a recording: it must resolve to a registered audio asset.
            ref = lesson.student_explanation.audio_ref[loc].strip()
            if not audio_assets.exists(ref):
                f.append(
                    _blk(
                        f"student_explanation {name} audio {ref!r} is not a registered audio asset",
                        "student_explanation",
                    )
                )
    return _gate(Gate.ACCESSIBILITY, f)


def _readability_gate(lesson: Lesson, ctx: _PackContext) -> GateResult:
    f: list[Finding] = []
    if ctx.pack is None or ctx.rules is None:
        f.append(_blk(ctx.unresolved()))
        return _gate(Gate.READABILITY, f)
    several = len(ctx.rules.readability_locales) > 1
    for loc in ctx.rules.readability_locales:
        max_words = ctx.pack.readability[loc].for_grade(lesson.metadata.grade_key)
        text = lesson.student_explanation.text.get(loc, "")
        if not any(s.strip() for s in _SENTENCE_SPLIT.split(text)):
            # Nothing to measure is a failure, never a vacuous pass.
            name = ctx.pack.locale_name(loc)
            f.append(_blk(f"no {name} student_explanation to measure", "student_explanation"))
            continue
        avg = _avg_words_per_sentence(text)
        if avg > max_words:
            where = f" ({ctx.pack.locale_name(loc)})" if several else ""
            f.append(_blk(f"avg sentence length {avg:.1f} exceeds grade max {max_words}{where}"))
    return _gate(Gate.READABILITY, f)


def _performance_gate(lesson: Lesson) -> GateResult:
    f: list[Finding] = []
    if not lesson.offline_package.strip():
        f.append(_blk("offline package required for performance/offline budget"))
    return _gate(Gate.PERFORMANCE, f)


def validate(
    lesson: Lesson,
    registry: PackRegistry | None = None,
    audio_assets: AudioAssetResolver | None = None,
    hierarchy: EducationSystem | None = None,
) -> ValidationResult:
    """Run structural + provenance + automated gate pre-checks under the lesson's pack rules.

    ``hierarchy`` is the lesson's pack's stored hierarchy (None = none stored): a non-empty
    chapter/topic placement must exist in it (BLOCKER otherwise).

    ``audio_assets`` resolves recorded-audio refs. Without one, only the synthetic dev/test
    fixture refs resolve (``audio.SYNTHETIC_FIXTURE_AUDIO``); production wiring passes the media
    registry resolver.
    """
    ctx = _resolve(lesson, registry if registry is not None else default_registry())
    audio = audio_assets if audio_assets is not None else SYNTHETIC_FIXTURE_AUDIO
    return ValidationResult(
        structural=_structural_findings(lesson, ctx),
        gate_results=[
            _alignment_gate(lesson, ctx, hierarchy),
            _accessibility_gate(lesson, ctx, audio),
            _readability_gate(lesson, ctx),
            _performance_gate(lesson),
        ],
    )
