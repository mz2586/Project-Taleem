"""Anthropic Claude adapter for the ``LLMGateway`` port — the FD-03 provider, INERT by default.

This is the real provider adapter recommended by docs/decisions/FD-03-ai-provider-residency.md
(Anthropic Claude, region-pinned, zero data retention). It exists so that, once the founder records
the FD-03 approvals, switching the AI Teacher onto Claude is **configuration only**. Until then it
cannot be built: no environment sets the configuration below.

**Construction gate (all required, checked in ``anthropic_config_problems``):**

- ``TALEEM_AI_PROVIDER=anthropic``
- ``TALEEM_AI_ANTHROPIC_API_KEY`` — a dedicated variable. The SDK's own credential discovery
  (``ANTHROPIC_API_KEY``, profiles, workload identity) is never used, so a key that happens to be
  on a machine cannot switch this on.
- ``TALEEM_AI_INFERENCE_GEO`` — an explicit residency pin from ``ALLOWED_INFERENCE_GEOS``.
  ``global`` is not a pin and is refused; adding a geography is a reviewed code change.
- ``TALEEM_AI_ZDR_CONFIRMED=true`` — the founder's attestation that a zero-data-retention agreement
  covers these models.
- ``TALEEM_AI_FD03_APPROVAL_REF`` — the id of the recorded FD-03 approval (all six items).

Missing any of them raises ``AnthropicNotApprovedError`` and the AI Teacher stays on the
deterministic engine; production refuses to boot on a partial configuration
(``platform/config.py``).

**Defence in depth, enforced here regardless of the caller (``assert_minimised``):** a request is
transmitted only if its prompt is exactly the grounded rephrase template — fixed instruction lines
plus the published LessonView passages listed in ``request.grounding`` — and, optionally, the
learner's selected option, which must be one of the item's authored options. Anything else (child
free text such as a written answer, identifiers, family codes, emails, phone numbers, or a value the
caller marked ``never_send``) is refused before any network call. The only identifier sent is a
fresh, random per-request id in ``metadata.user_id``.

**Fallbacks:** a refusal (``stop_reason == "refusal"``), a truncated or otherwise incomplete reply,
a timeout, a rate limit, or any API error raises a ``ProviderUnavailableError`` subclass, and the
AI Teacher serves the authored response labelled ``fallback: "authored"``. Billed-but-unusable calls
carry their accounting (``billed``) so the cost still reaches the usage ledger and the quota. The
API's server-side refusal ``fallbacks`` are deliberately NOT enabled: a fallback would run the
request on a different model, outside what FD-03 approved; for a child the fallback is our own
authored content.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, replace
from decimal import ROUND_CEILING, Decimal
from typing import TYPE_CHECKING, Literal

from .llm import LLMRequest, LLMResponse, ProviderUnavailableError, Tier

if TYPE_CHECKING:  # pragma: no cover - typing only; the SDK is imported lazily at construction
    import anthropic
    import httpx2

    from ..platform.config import Settings

ANTHROPIC_PROVIDER = "anthropic"
# Exact model ids (FD-03 recommendation). Fable-tier models are excluded from zero data retention
# unless Anthropic expressly authorizes them, so they are not used here.
EXPLANATION_MODEL = "claude-sonnet-5-5"
CLASSIFICATION_MODEL = "claude-haiku-5-5"  # FD-03 routing tier; no call site until the check ships
# Every tier the AI Teacher routes today is explanation work (rephrasing authored lesson text).
TIER_MODELS: dict[Tier, str] = {
    Tier.LIGHT: EXPLANATION_MODEL,
    Tier.STANDARD: EXPLANATION_MODEL,
    Tier.DEEP: EXPLANATION_MODEL,
    Tier.SAFETY: EXPLANATION_MODEL,
}
# Residency pins this adapter accepts (first-party API ``inference_geo``). "global" is not a pin.
ALLOWED_INFERENCE_GEOS = frozenset({"us"})
# Pinned explicitly: ``ANTHROPIC_BASE_URL`` in the environment must not redirect child-session text.
ANTHROPIC_API_BASE_URL = "https://api.anthropic.com"
DEFAULT_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RETRIES = 1  # a child is waiting: one retry, then the authored response
MAX_OUTPUT_TOKENS = 1024
# Thinking is turned off for a short rephrase (Claude Sonnet 5.5: ``between_tools`` is how; it is
# accepted at effort ``high`` or below and takes no other field). This keeps the whole output budget
# for the visible text and the latency low.
EFFORT: Literal["medium"] = "medium"
_APPROVAL_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,63}$")

# List prices, USD per million tokens (== micro-USD per token): input, output, 5-minute cache
# write, cache read. Verify against the pricing page when FD-03 is approved.
_PRICES: dict[str, tuple[Decimal, Decimal, Decimal, Decimal]] = {
    EXPLANATION_MODEL: (Decimal("2.00"), Decimal("10.00"), Decimal("2.50"), Decimal("0.20")),
    CLASSIFICATION_MODEL: (Decimal("0.10"), Decimal("0.50"), Decimal("0.125"), Decimal("0.01")),
}
# Data-residency premium per pinned geography (``inference_geo``); verify at approval.
_GEO_MULTIPLIER: dict[str, Decimal] = {"us": Decimal("1.1")}

SYSTEM_PROMPT = (
    "You rephrase approved school lesson passages for a child. Follow the instructions in the "
    "user message exactly. Reply with the rephrased text only: no preamble, no headings, no "
    "markup, no links, and no questions about the learner. If you cannot follow the "
    "instructions, reply with nothing."
)


# ---------------------------------------------------------------------------- errors


class AnthropicNotApprovedError(ProviderUnavailableError):
    """The FD-03 approval configuration is incomplete; the adapter refuses to construct."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("not_approved: " + "; ".join(problems))
        self.problems = tuple(problems)


class MinimisationViolationError(ProviderUnavailableError):
    """The request carries something FD-03 says is never sent; nothing was transmitted."""


class ProviderRefusedError(ProviderUnavailableError):
    """The model declined (``stop_reason == "refusal"``)."""


class ProviderIncompleteError(ProviderUnavailableError):
    """The reply stopped for a reason other than finishing (e.g. ``max_tokens``)."""


class ProviderTimeoutError(ProviderUnavailableError):
    """The call timed out (after the SDK's retries)."""


class ProviderRateLimitedError(ProviderUnavailableError):
    """HTTP 429 from the provider."""


class ProviderConnectionError(ProviderUnavailableError):
    """The provider could not be reached."""


class ProviderResponseError(ProviderUnavailableError):
    """Any other API error status (4xx/5xx)."""


# ---------------------------------------------------------------------------- configuration


def anthropic_config_problems(
    *,
    provider: str,
    api_key: str,
    inference_geo: str,
    zdr_confirmed: str,
    fd03_approval_ref: str,
) -> list[str]:
    """Everything missing before the adapter may be built (empty => complete). Pure."""
    problems: list[str] = []
    if provider.strip().lower() != ANTHROPIC_PROVIDER:
        problems.append(f"TALEEM_AI_PROVIDER must be {ANTHROPIC_PROVIDER!r}")
    key = api_key.strip()
    if not key or any(c.isspace() for c in key):
        problems.append("TALEEM_AI_ANTHROPIC_API_KEY is unset")
    geo = inference_geo.strip().lower()
    if geo not in ALLOWED_INFERENCE_GEOS:
        problems.append(
            "TALEEM_AI_INFERENCE_GEO must explicitly pin a region "
            f"(one of {sorted(ALLOWED_INFERENCE_GEOS)}; 'global' is not a pin)"
        )
    if zdr_confirmed.strip().lower() != "true":
        problems.append("TALEEM_AI_ZDR_CONFIRMED is not 'true' (zero-data-retention attestation)")
    if not _APPROVAL_REF.match(fd03_approval_ref.strip()):
        problems.append("TALEEM_AI_FD03_APPROVAL_REF is unset (the recorded FD-03 approval id)")
    return problems


def settings_problems(settings: Settings) -> list[str]:
    return anthropic_config_problems(
        provider=settings.ai_provider,
        api_key=settings.ai_anthropic_api_key,
        inference_geo=settings.ai_inference_geo,
        zdr_confirmed=settings.ai_zdr_confirmed,
        fd03_approval_ref=settings.ai_fd03_approval_ref,
    )


# ---------------------------------------------------------------------------- minimisation guard

# The only instruction lines a transmitted prompt may contain (``GroundedPrompt.render``). A test
# renders every locale x age band through this guard, so the two cannot drift apart silently.
_HEADER_LINES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^Rephrase the approved lesson passages below for an? [a-z() -]{1,40} learner, "
        r"in [A-Za-z]{2,20}\.$"
    ),
    re.compile(
        r"^Use ONLY the facts and numbers in the passages\. "
        r"Add no new facts and no new numbers\.$"
    ),
    re.compile(
        r"^Do not answer any question in the passages and do not say which option is correct\.$"
    ),
    re.compile(r"^No links, no contact details, and no questions about the learner\.$"),
    re.compile(r"^At most \d{1,3} words; at most \d{1,3} words per sentence\.$"),
)
_PASSAGES_MARKER = "\nPassages:\n"
_MAX_PROMPT_CHARS = 16_000
_MAX_PASSAGES = 64
_MAX_OPTION_CHARS = 200

# Identifier shapes that must never leave (defence in depth; the template check is the main guard).
_IDENTIFIER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Family codes use an unambiguous upper-case alphabet (identity domain), e.g. ``K7QM-3XPZ``.
    ("family_code", re.compile(r"\b[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}\b")),
    ("uuid", re.compile(r"\b[0-9a-fA-F]{8}(?:-?[0-9a-fA-F]{4}){3}-?[0-9a-fA-F]{12}\b")),
    ("email", re.compile(r"[^\s@]+@[^\s@]+\.[^\s@]+")),
    ("phone_or_long_number", re.compile(r"\+?\d[\d \-]{6,}\d")),
    ("account_ref", re.compile(r"\b(?:student|guardian|learner|family|user)[:_/]\S+", re.I)),
)


def _identifier_hits(text: str, never_send: tuple[str, ...]) -> list[str]:
    hits = [name for name, pattern in _IDENTIFIER_PATTERNS if pattern.search(text)]
    lowered = text.casefold()
    for value in never_send:
        v = value.strip().casefold()
        if len(v) >= 3 and v in lowered:
            hits.append("never_send")
    return hits


def assert_minimised(request: LLMRequest) -> None:
    """Refuse (``MinimisationViolationError``) anything but lesson passages + a selected option.

    Rules: the prompt is exactly the grounded rephrase template whose passage lines are
    ``request.grounding`` in order; no transmitted text matches an identifier shape or a
    ``never_send`` value; a selected option, if any, is one of the authored options.
    """
    if not request.grounding:
        raise MinimisationViolationError("minimisation: no lesson grounding")
    if len(request.grounding) > _MAX_PASSAGES or len(request.prompt) > _MAX_PROMPT_CHARS:
        raise MinimisationViolationError("minimisation: prompt too large")
    if not 0 < request.max_output_tokens <= MAX_OUTPUT_TOKENS:
        raise MinimisationViolationError("minimisation: output budget out of range")
    header, marker, body = request.prompt.partition(_PASSAGES_MARKER)
    if not marker:
        raise MinimisationViolationError("minimisation: not the grounded rephrase template")
    lines = header.split("\n")
    if len(lines) != len(_HEADER_LINES) or not all(
        p.match(line) for p, line in zip(_HEADER_LINES, lines, strict=True)
    ):
        raise MinimisationViolationError("minimisation: unrecognised instruction text")
    expected = "\n".join(f"[{i}] {text}" for i, text in enumerate(request.grounding, 1))
    if body != expected:
        raise MinimisationViolationError("minimisation: prompt carries text beyond the grounding")
    option = request.selected_option
    if option and (
        option not in request.selected_option_choices
        or "\n" in option
        or len(option) > _MAX_OPTION_CHARS
    ):
        raise MinimisationViolationError("minimisation: selected option is not authored")
    for text in (*request.grounding, option):
        hits = _identifier_hits(text, request.never_send)
        if hits:
            raise MinimisationViolationError(
                "minimisation: identifier-shaped content (" + ",".join(sorted(set(hits))) + ")"
            )


# ---------------------------------------------------------------------------- cost


def cost_micros(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cache_write_tokens: int,
    cache_read_tokens: int,
    inference_geo: str,
) -> int:
    """Cost in micro-USD from the response ``usage`` (rounded up; never under-counts)."""
    p_in, p_out, p_write, p_read = _PRICES[model]
    raw = (
        input_tokens * p_in
        + output_tokens * p_out
        + cache_write_tokens * p_write
        + cache_read_tokens * p_read
    ) * _GEO_MULTIPLIER.get(inference_geo, Decimal(1))
    return int(raw.to_integral_value(rounding=ROUND_CEILING))


# ---------------------------------------------------------------------------- adapter


@dataclass(frozen=True)
class SentRequest:
    """What the adapter transmitted for one call (kept for tests/evaluation; counts + ids only)."""

    model: str
    request_id: str
    inference_geo: str


class AnthropicGateway:
    """``LLMGateway`` over the official ``anthropic`` SDK. Refuses to exist without FD-03 config."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        inference_geo: str,
        zdr_confirmed: str,
        fd03_approval_ref: str,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx2.Client | None = None,
    ) -> None:
        problems = anthropic_config_problems(
            provider=provider,
            api_key=api_key,
            inference_geo=inference_geo,
            zdr_confirmed=zdr_confirmed,
            fd03_approval_ref=fd03_approval_ref,
        )
        if problems:
            raise AnthropicNotApprovedError(problems)
        import anthropic  # lazy: the SDK is loaded only once every approval setting is present

        self._sdk = anthropic
        self.inference_geo = inference_geo.strip().lower()
        self.fd03_approval_ref = fd03_approval_ref.strip()
        self.name = ANTHROPIC_PROVIDER
        self._client = anthropic.Anthropic(
            api_key=api_key.strip(),  # explicit: env/profile/federation credentials are not read
            base_url=ANTHROPIC_API_BASE_URL,
            timeout=timeout_seconds if timeout_seconds > 0 else DEFAULT_TIMEOUT_SECONDS,
            max_retries=max(0, max_retries),
            open_telemetry=False,  # no request/response content in traces
            http_client=http_client,
        )
        self.sent: list[SentRequest] = []

    def complete(self, request: LLMRequest) -> LLMResponse:
        assert_minimised(request)  # raises before anything is transmitted
        model = TIER_MODELS[request.tier]
        request_id = f"req-{uuid.uuid4().hex}"  # opaque, random, never derived from the learner
        sdk = self._sdk
        user_content: list[anthropic.types.TextBlockParam] = [
            # The rendered lesson prompt is identical for every learner on the same lesson, style,
            # locale and age band, so it is the cached prefix. Short prefixes (below the model's
            # minimum cacheable length) simply do not cache.
            {"type": "text", "text": request.prompt, "cache_control": {"type": "ephemeral"}}
        ]
        if request.selected_option:
            user_content.append(
                {
                    "type": "text",
                    "text": f"The learner selected this option: {request.selected_option}",
                }
            )
        self.sent.append(SentRequest(model, request_id, self.inference_geo))
        try:
            message = self._client.messages.create(
                model=model,
                max_tokens=MAX_OUTPUT_TOKENS,
                system=[
                    {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
                ],
                messages=[{"role": "user", "content": user_content}],
                thinking={"type": "between_tools"},
                output_config={"effort": EFFORT},
                inference_geo=self.inference_geo,
                metadata={"user_id": request_id},
            )
        except sdk.APITimeoutError as exc:
            raise ProviderTimeoutError("timeout") from exc
        except sdk.APIConnectionError as exc:
            raise ProviderConnectionError("connection") from exc
        except sdk.RateLimitError as exc:
            raise ProviderRateLimitedError("rate_limited") from exc
        except sdk.APIStatusError as exc:
            raise ProviderResponseError(f"status_{exc.status_code}") from exc
        except sdk.AnthropicError as exc:
            raise ProviderResponseError(type(exc).__name__) from exc

        usage = message.usage
        cache_write = usage.cache_creation_input_tokens or 0
        cache_read = usage.cache_read_input_tokens or 0
        prompt_tokens = usage.input_tokens + cache_write + cache_read
        cost = cost_micros(
            model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_write_tokens=cache_write,
            cache_read_tokens=cache_read,
            inference_geo=self.inference_geo,
        )
        text = "".join(block.text for block in message.content if block.type == "text")
        response = LLMResponse(
            text=text,
            tier=request.tier,
            tokens=prompt_tokens + usage.output_tokens,
            provider=f"{ANTHROPIC_PROVIDER}:{model}",
            grounded=True,
            prompt_tokens=prompt_tokens,
            completion_tokens=usage.output_tokens,
            cost_micros=cost,
        )
        if message.stop_reason == "refusal":
            category = message.stop_details.category if message.stop_details else None
            unusable = replace(response, text="")
            raise ProviderRefusedError(f"refusal:{category or 'uncategorised'}", billed=unusable)
        if message.stop_reason != "end_turn":
            unusable = replace(response, text="")
            raise ProviderIncompleteError(f"stop_reason:{message.stop_reason}", billed=unusable)
        return response


def anthropic_gateway(
    settings: Settings, *, http_client: httpx2.Client | None = None
) -> AnthropicGateway:
    """Build the adapter from settings (raises ``AnthropicNotApprovedError`` if incomplete)."""
    return AnthropicGateway(
        provider=settings.ai_provider,
        api_key=settings.ai_anthropic_api_key,
        inference_geo=settings.ai_inference_geo,
        zdr_confirmed=settings.ai_zdr_confirmed,
        fd03_approval_ref=settings.ai_fd03_approval_ref,
        timeout_seconds=settings.ai_timeout_seconds,
        http_client=http_client,
    )
