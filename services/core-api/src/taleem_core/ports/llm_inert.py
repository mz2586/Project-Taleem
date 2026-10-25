"""Inert provider adapter — the placeholder for a real model provider (blocked on FD-03).

This is deliberately **not** an integration. It holds no API key, imports no HTTP client, and has
no network transport. Consistent with docs/decisions/FD-03-ai-provider-residency.md:

- it **refuses to construct** without an explicitly named provider (``not_configured``), and that
  configuration (``TALEEM_AI_PROVIDER``) is not set in any environment — so by default the
  composition root wires no generative tier at all;
- even when named, **every call raises** ``ProviderUnavailableError`` (``no_transport``) and the AI
  Teacher serves its templated, authored response. Naming a provider does not connect one.

Connecting a real provider requires all six approvals listed in the FD-03 brief (provider + region
and transfer basis, zero-retention/no-training addendum, DPIA, external red-team of the gate, the
per-learner cost envelope (FD-07), and golden-set results on the chosen model). The adapter for
the recommended provider is ``ports/llm_anthropic.py`` (``TALEEM_AI_PROVIDER=anthropic``), which
refuses to construct until those approvals are recorded in configuration; any other provider name
still lands here.
"""

from __future__ import annotations

from .llm import LLMRequest, LLMResponse, ProviderUnavailableError

FD03_BLOCKER = "FD-03 (inference residency + zero-retention) is undecided"


class InertProviderGateway:
    """Refuses every call. Cannot reach a network: there is no transport to reach one with."""

    def __init__(self, provider: str) -> None:
        name = provider.strip()
        if not name:
            raise ProviderUnavailableError(
                f"not_configured: no AI provider is named; {FD03_BLOCKER}"
            )
        self._provider = name
        self.name = f"inert:{name}"
        self.attempts = 0  # how many calls were refused (observability; never a hidden retry)

    def complete(self, request: LLMRequest) -> LLMResponse:
        self.attempts += 1
        raise ProviderUnavailableError(
            f"no_transport: provider {self._provider!r} is named but no network adapter exists in "
            f"this build; {FD03_BLOCKER}"
        )
