"""Quality gates (pure-stdlib types + registry).

Defines the 9 gates and the GateResult record. The validator FUNCTIONS that inspect a Lesson live in
validation.py (to avoid a Lesson import cycle here).
See docs/10-curriculum-studio/QUALITY_ASSURANCE_STANDARD.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Gate(StrEnum):
    EDUCATIONAL_REVIEW = "educational_review"
    CURRICULUM_ALIGNMENT = "curriculum_alignment"
    TECHNICAL_ACCURACY = "technical_accuracy"
    LANGUAGE = "language"
    ACCESSIBILITY = "accessibility"
    AI_SAFETY = "ai_safety"
    AGE_APPROPRIATENESS = "age_appropriateness"
    READABILITY = "readability"
    PERFORMANCE = "performance"


ALL_GATES: tuple[Gate, ...] = tuple(Gate)

# Which gates have an automated pre-check component (run on :validate before human review).
AUTOMATED_GATES: frozenset[Gate] = frozenset(
    {Gate.CURRICULUM_ALIGNMENT, Gate.ACCESSIBILITY, Gate.READABILITY, Gate.PERFORMANCE}
)


class Severity(StrEnum):
    BLOCKER = "blocker"
    MAJOR = "major"
    MINOR = "minor"


@dataclass
class Finding:
    severity: Severity
    message: str
    field: str = ""


@dataclass
class GateResult:
    gate: Gate
    passed: bool
    mode: str  # "auto" | "human"
    reviewer_role: str = ""
    findings: list[Finding] = field(default_factory=list)
    at: float = 0.0

    @property
    def has_blocker(self) -> bool:
        return any(f.severity is Severity.BLOCKER for f in self.findings)


def all_gates_green(results: list[GateResult]) -> bool:
    """True only if every one of the 9 gates has a passing result."""
    by_gate = {r.gate: r for r in results}
    return all(g in by_gate and by_gate[g].passed for g in ALL_GATES)
