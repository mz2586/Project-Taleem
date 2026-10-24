"""AI rubric marking of open written answers — a port, a stub and an INERT LLM adapter.

HOMEWORK_AND_MARKING_CONTRACT §6: open written answers (stories, explanations, letters) are never
scored by a rule or a model today. This module defines the seam a future model-backed marker would
use, so it can be designed and tested against a stub, and nothing more:

- ``WrittenWorkMarker`` — the port: propose a rubric mark for one answer, or decline (``None``).
- ``StubWrittenWorkMarker`` — scripted and deterministic, for tests only.
- ``LLMWrittenWorkMarker`` — goes through the existing ``LLMGateway``. It declines every call
  unless ALL of these hold: the ``homework.ai_rubric_marking`` flag is on, FD-03 (inference
  residency + zero-retention) is recorded as approved, an in-region distress classifier is wired
  AND clears the child's text first, and the item has a scored rubric. FD-03 is undecided and no
  classifier exists, so in this build it always declines; with the inert provider adapter a call
  would also be refused (``ProviderUnavailableError``) and the marker declines.

**Not wired.** The composition root gives the school context no marker, so no submission path —
assigned or self-paced — ever calls this. A proposal, were one ever produced, is a suggestion for
a human; nothing here records evidence or changes a submission.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from ....platform.feature_flags import FlagProvider
from ....ports.llm import LLMGateway, LLMRequest, ProviderUnavailableError, Tier

AI_RUBRIC_MARKING_FLAG = "homework.ai_rubric_marking"
# Flipped only by a reviewed change once the FD-03 brief's approvals exist. Never configuration.
FD03_APPROVED = False


@dataclass(frozen=True)
class RubricForMarking:
    criteria: str
    max_score: int
    levels: tuple[tuple[int, str], ...] = ()  # (score, descriptor)


@dataclass(frozen=True)
class MarkProposal:
    """A suggested mark for a human to accept or reject. Never recorded as evidence by itself."""

    met: bool
    score: int
    rationale: str


class WrittenWorkMarker(Protocol):
    def propose(
        self, *, prompt: str, rubric: RubricForMarking | None, text: str
    ) -> MarkProposal | None:
        """A proposal, or None (declined / unavailable). The learner's ref is never an input."""


class DistressClassifier(Protocol):
    """An IN-REGION classifier that must clear a child's text before any model sees it."""

    def is_clear(self, text: str) -> bool: ...


class StubWrittenWorkMarker:
    """Deterministic test double: ``responder`` scripts the proposal; every call is recorded."""

    def __init__(
        self, responder: Callable[[str, RubricForMarking | None, str], MarkProposal | None]
    ) -> None:
        self._responder = responder
        self.calls: list[tuple[str, RubricForMarking | None, str]] = []

    def propose(
        self, *, prompt: str, rubric: RubricForMarking | None, text: str
    ) -> MarkProposal | None:
        self.calls.append((prompt, rubric, text))
        return self._responder(prompt, rubric, text)


class LLMWrittenWorkMarker:
    """Rubric marking through the ``LLMGateway`` — inert until FD-03 + a distress classifier."""

    def __init__(
        self,
        *,
        gateway: LLMGateway | None,
        flags: FlagProvider,
        distress_classifier: DistressClassifier | None = None,
        fd03_approved: bool = FD03_APPROVED,
    ) -> None:
        self._gateway = gateway
        self._flags = flags
        self._classifier = distress_classifier
        self._fd03 = fd03_approved

    def enabled(self) -> bool:
        return (
            self._gateway is not None
            and self._fd03
            and self._classifier is not None
            and self._flags.is_enabled(AI_RUBRIC_MARKING_FLAG)
        )

    def propose(
        self, *, prompt: str, rubric: RubricForMarking | None, text: str
    ) -> MarkProposal | None:
        gateway, classifier = self._gateway, self._classifier
        if not self.enabled() or gateway is None or classifier is None:
            return None
        if rubric is None or rubric.max_score <= 0:
            return None
        if not classifier.is_clear(text):
            return None  # distress-adjacent text never reaches a model
        request = LLMRequest(
            prompt=(
                "Mark the learner's answer against the rubric. Reply with JSON "
                '{"score": int, "met": bool, "rationale": str}.'
            ),
            tier=Tier.STANDARD,
            grounding=(
                f"QUESTION: {prompt}",
                f"RUBRIC: {rubric.criteria} (0..{rubric.max_score})",
                *(f"LEVEL {score}: {d}" for score, d in rubric.levels),
                f"ANSWER: {text}",
            ),
            max_output_tokens=200,
        )
        try:
            response = gateway.complete(request)
        except ProviderUnavailableError:
            return None
        return _parse(response.text, rubric.max_score)


def _parse(raw: str, max_score: int) -> MarkProposal | None:
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    score, met = data.get("score"), data.get("met")
    if isinstance(score, bool) or not isinstance(score, int) or not 0 <= score <= max_score:
        return None
    if not isinstance(met, bool):
        return None
    return MarkProposal(met=met, score=score, rationale=str(data.get("rationale", ""))[:500])
