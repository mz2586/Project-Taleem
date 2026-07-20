"""The AI Teaching Object (pure-stdlib).

Structured, authored AI instructions per lesson.
See docs/10-curriculum-studio/AI_TEACHING_STANDARD.md.
Safety fields (forbidden_behaviours, escalation_rules) are mandatory and non-empty.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AITeachingObject:
    learning_goals: list[str] = field(default_factory=list)  # SLO codes this interaction advances
    teaching_strategy: str = ""
    questioning_strategy: str = ""
    slow_down_signals: list[str] = field(default_factory=list)
    hint_policy: str = ""  # graduated; capped before escalation; never answer-first
    example_policy: str = ""
    misconception_detectors: list[str] = field(default_factory=list)  # covers lesson misconceptions
    critical_thinking_prompts: list[str] = field(default_factory=list)
    personalization_rules: str = ""
    escalation_rules: list[str] = field(default_factory=list)  # MANDATORY non-empty
    forbidden_behaviours: list[str] = field(default_factory=list)  # MANDATORY non-empty
    confidence_thresholds: dict[str, float] = field(default_factory=dict)

    def missing_required(self) -> list[str]:
        """Return names of missing/empty required fields (validation)."""
        missing: list[str] = []
        if not self.learning_goals:
            missing.append("learning_goals")
        if not self.teaching_strategy.strip():
            missing.append("teaching_strategy")
        if not self.questioning_strategy.strip():
            missing.append("questioning_strategy")
        if not self.hint_policy.strip():
            missing.append("hint_policy")
        if not self.escalation_rules:
            missing.append("escalation_rules")
        if not self.forbidden_behaviours:
            missing.append("forbidden_behaviours")
        return missing
