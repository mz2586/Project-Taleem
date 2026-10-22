"""AI provider abstraction — the LLM gateway port (pure-stdlib).

No product code ever calls a provider SDK directly (docs/24 §5, FR-AIT-005): all AI traffic goes
through this port. Model tiering (Haiku/Sonnet/Opus) is a routing policy on the port, not scattered
call sites.

This module ships ONLY offline, deterministic, **NON-production** implementations:

- ``StubLLMProvider`` — the original placeholder (returns a fixed stub marker).
- ``StubLLMGateway`` — a scripted, deterministic gateway for tests and the evaluation harness.

The only "real provider" shape in the tree is ``ports/llm_inert.py``, which refuses every call: no
network transport exists in this build. Connecting a real provider is blocked on FOUNDER_DECISIONS
**FD-03** (inference residency + zero-retention). Neither stub may be used with real children.

Every call is accounted: ``LLMResponse`` carries prompt/completion token counts and a cost in
micro-units, and a ``CostMeter`` records one ``UsageRecord`` per call, attributed to the
pseudonymous learner it was made for. ``LearnerQuota`` caps calls/tokens/cost per learner per
period. The stubs report zero cost — this is the accounting *interface*, not a billing integration.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, runtime_checkable


class Tier(StrEnum):
    LIGHT = "light"  # e.g. Haiku — routine
    STANDARD = "standard"  # e.g. Sonnet — normal tutoring
    DEEP = "deep"  # e.g. Opus — hard explanations
    SAFETY = "safety"  # strongest tier; distress-adjacent turns route here regardless of cost


@dataclass(frozen=True)
class LLMRequest:
    prompt: str
    tier: Tier
    grounding: tuple[str, ...] = ()  # RAG context: the only passages the model may rephrase
    max_output_tokens: int = 256


@dataclass(frozen=True)
class LLMResponse:
    text: str
    tier: Tier
    tokens: int  # total tokens (prompt + completion); kept for backwards compatibility
    provider: str
    grounded: bool
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_micros: int = 0  # cost in millionths of the billing currency; 0 for every stub


@runtime_checkable
class LLMGateway(Protocol):
    """The single seam every model call goes through. ``name`` identifies the adapter."""

    name: str

    def complete(self, request: LLMRequest) -> LLMResponse: ...


# Historical name for the same port (kept so existing imports keep working).
LLMProvider = LLMGateway


class ProviderUnavailableError(RuntimeError):
    """Raised by an adapter that cannot (or may not) serve a call; callers use templates."""


# ---------------------------------------------------------------------------- cost accounting


@dataclass(frozen=True)
class UsageRecord:
    """One model call's accounting line. Carries no prompt or output text — counts only.

    ``learner_ref`` is the pseudonymous ``student_ref`` the call was made for (never a name, family
    code, or contact detail), so inference cost can be tracked and capped per learner. It stays in
    the ledger; it is never sent to a provider.
    """

    provider: str
    tier: Tier
    prompt_tokens: int
    completion_tokens: int
    cost_micros: int
    purpose: str = ""  # e.g. "ai_teacher.rephrase"
    learner_ref: str = ""
    recorded_at: float = 0.0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class UsageSummary:
    """Aggregate usage for one learner (or all learners) over a time window."""

    calls: int = 0
    tokens: int = 0
    cost_micros: int = 0


@runtime_checkable
class CostMeter(Protocol):
    def record(self, usage: UsageRecord) -> None: ...


@runtime_checkable
class LearnerUsageLedger(CostMeter, Protocol):
    """A cost meter that can also answer "how much has this learner used in this period?"."""

    def usage_for(
        self, learner_ref: str, *, since: float = 0.0, until: float | None = None
    ) -> UsageSummary: ...

    def by_learner(
        self, *, since: float = 0.0, until: float | None = None
    ) -> dict[str, UsageSummary]: ...

    def purge_older_than(self, cutoff: float) -> int:
        """Delete records with ``recorded_at < cutoff``; returns how many (retention hook)."""
        ...


@dataclass
class InMemoryCostLedger:
    """Process-local ledger (dev/test only).

    Production uses the durable, shared ``SqlLearnerUsageLedger``
    (``learning.ai_usage_ledger``, migration 0007) so quotas hold across instances and restarts.
    """

    records: list[UsageRecord] = field(default_factory=list)

    def record(self, usage: UsageRecord) -> None:
        self.records.append(usage)

    @property
    def calls(self) -> int:
        return len(self.records)

    @property
    def total_tokens(self) -> int:
        return sum(r.total_tokens for r in self.records)

    @property
    def total_cost_micros(self) -> int:
        return sum(r.cost_micros for r in self.records)

    def usage_for(
        self, learner_ref: str, *, since: float = 0.0, until: float | None = None
    ) -> UsageSummary:
        """Aggregate one learner's usage in ``[since, until)`` (``until=None`` means open-ended)."""
        rows = [
            r
            for r in self.records
            if r.learner_ref == learner_ref
            and r.recorded_at >= since
            and (until is None or r.recorded_at < until)
        ]
        return UsageSummary(
            calls=len(rows),
            tokens=sum(r.total_tokens for r in rows),
            cost_micros=sum(r.cost_micros for r in rows),
        )

    def by_learner(
        self, *, since: float = 0.0, until: float | None = None
    ) -> dict[str, UsageSummary]:
        """Per-learner aggregates for a period (an operator cost view)."""
        refs = sorted({r.learner_ref for r in self.records})
        return {ref: self.usage_for(ref, since=since, until=until) for ref in refs}

    def purge_older_than(self, cutoff: float) -> int:
        kept = [r for r in self.records if r.recorded_at >= cutoff]
        removed = len(self.records) - len(kept)
        self.records = kept
        return removed


@dataclass(frozen=True)
class LearnerQuota:
    """Per-learner inference budget for one period. ``0`` for a limit means "no calls allowed".

    Periods are fixed windows aligned to the epoch (``period_seconds=86400`` => UTC days), so every
    instance computes the same window. Exhaustion is not an error: the caller serves the templated,
    authored response instead.
    """

    max_calls: int
    max_tokens: int
    max_cost_micros: int | None = None  # None until FD-07 sets a real cost envelope
    period_seconds: int = 86_400

    def period_start(self, now: float) -> float:
        return now - (now % self.period_seconds)

    def exhausted(self, used: UsageSummary) -> bool:
        if used.calls >= self.max_calls or used.tokens >= self.max_tokens:
            return True
        return self.max_cost_micros is not None and used.cost_micros >= self.max_cost_micros


def usage_of(
    response: LLMResponse, purpose: str = "", *, learner_ref: str = "", recorded_at: float = 0.0
) -> UsageRecord:
    return UsageRecord(
        provider=response.provider,
        tier=response.tier,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        cost_micros=response.cost_micros,
        purpose=purpose,
        learner_ref=learner_ref,
        recorded_at=recorded_at,
    )


def _count_tokens(text: str) -> int:
    """Whitespace token count — a deterministic stand-in, not a real tokenizer."""
    return len(text.split())


# ---------------------------------------------------------------------------- stubs


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


def echo_grounding(request: LLMRequest) -> str:
    """Default stub behaviour: "rephrase" by returning the grounding passages verbatim."""
    return " ".join(request.grounding)


class StubLLMGateway:
    """Scripted, deterministic gateway for tests and the evaluation harness. Zero cost, no network.

    ``responder`` maps a request to the text the "model" returns, so a test can script adversarial
    output (an invented number, a leaked answer, a URL...) and prove the safety gate refuses it.
    Every request is kept in ``requests`` so tests can assert exactly what was (not) sent.
    """

    name = "stub-gateway"

    def __init__(self, responder: Callable[[LLMRequest], str] | None = None) -> None:
        self._responder = responder or echo_grounding
        self.requests: list[LLMRequest] = []

    @property
    def calls(self) -> int:
        return len(self.requests)

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        text = self._responder(request)
        prompt_tokens = _count_tokens(request.prompt)
        completion_tokens = _count_tokens(text)
        return LLMResponse(
            text=text,
            tier=request.tier,
            tokens=prompt_tokens + completion_tokens,
            provider=self.name,
            grounded=bool(request.grounding),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_micros=0,  # a stub costs nothing — and must never be mistaken for a real bill
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
