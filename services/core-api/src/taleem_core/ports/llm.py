"""AI provider abstraction — the LLM gateway port (pure-stdlib).

No product code ever calls a provider SDK directly (docs/24 §5, FR-AIT-005): all AI traffic goes
through this port. Model tiering (Haiku/Sonnet/Opus) is a routing policy on the port, not scattered
call sites.

M1 ships ONLY a `StubLLMProvider` — deterministic, offline, NON-production. It exists to prove the
abstraction + routing + safety-gate seams compile and are testable. It MUST NOT be used with real
children (production AI is a Phase-2 item gated on FOUNDER_DECISIONS FD-03).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable


class Tier(str, Enum):
    LIGHT = "light"  # e.g. Haiku — routine
    STANDARD = "standard"  # e.g. Sonnet — normal tutoring
    DEEP = "deep"  # e.g. Opus — hard explanations
    SAFETY = "safety"  # strongest tier; distress-adjacent turns route here regardless of cost


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    tier: Tier
    grounding: tuple[str, ...] = ()  # RAG context; empty in the stub


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tier: Tier
    tokens: int
    provider: str
    grounded: bool


@runtime_checkable
class LLMProvider(Protocol):
    def complete(self, request: LLMRequest) -> LLMResponse: ...


class StubLLMProvider:
    """Deterministic, offline stub. Never contacts a network. NOT for production/children."""

    name = "stub"

    def complete(self, request: LLMRequest) -> LLMResponse:
        # Governance guard: refuse to pretend to answer a child; return an explicit stub marker.
        text = f"[stub:{request.tier.value}] grounded-answer-placeholder"
        return LLMResponse(
            text=text,
            tier=request.tier,
            tokens=len(request.prompt.split()),
            provider=self.name,
            grounded=bool(request.grounding),
        )


def route_tier(*, distress_adjacent: bool, difficulty: str) -> Tier:
    """Tier routing policy (docs/24 §5 + audit AR-H-16): safety never yields to cost.

    Any distress-adjacent turn routes to the strongest tier regardless of cost.
    """
    if distress_adjacent:
        return Tier.SAFETY
    return {
        "easy": Tier.LIGHT,
        "normal": Tier.STANDARD,
        "hard": Tier.DEEP,
    }.get(difficulty, Tier.STANDARD)
