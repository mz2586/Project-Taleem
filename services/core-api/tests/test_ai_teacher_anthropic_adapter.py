"""FD-03 Claude adapter (``ports/llm_anthropic.py``): inert by default, switched on by config.

Proven here, with NO API key and NO real network (the official SDK runs against an in-process
``httpx2.MockTransport``; sockets are blocked for the whole module):

- the adapter refuses to construct unless every FD-03 approval setting is present, and production
  refuses to boot on a partial set; the app otherwise stays on the deterministic engine;
- data minimisation is enforced in the adapter: only the grounded rephrase template (published
  LessonView passages) and an authored selected option can be transmitted — child free text,
  identifiers, family codes, contact details and ``never_send`` values are refused before sending;
- a mocked success flows through the safety gate into a labelled ``generation`` block, with its
  cost (from ``usage`` tokens) in the usage ledger; refusal / truncation / timeout / error responses
  fall back to the authored response; quota is enforced before any call;
- requests carry prompt-caching breakpoints, a residency pin, a random per-request id, and none of
  the parameters Claude Sonnet 5.5 rejects (no prefill, no forced tool choice, no sampling params);
- the evaluation CLI refuses ``--provider anthropic`` without the approval configuration.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Callable
from typing import Any

import anthropic
import httpx2
import pytest

from taleem_core.contexts.learning.application.ai_teacher_service import (
    AITeacherService,
    GenerativeTier,
    SafetyEvent,
)
from taleem_core.contexts.learning.application.written_marker import (
    AI_RUBRIC_MARKING_FLAG,
    LLMWrittenWorkMarker,
    RubricForMarking,
)
from taleem_core.contexts.learning.domain import ai_teacher as ait
from taleem_core.contexts.learning.domain import ai_teacher_gate as gate
from taleem_core.contexts.learning.domain.curriculum_view import LessonView
from taleem_core.contexts.learning.domain.decision import CurriculumGraph, DecisionConfig
from taleem_core.contexts.learning.domain.runtime import TemplatedTeachingRuntime
from taleem_core.main import create_app
from taleem_core.platform.config import (
    Environment,
    InsecureConfigurationError,
    Settings,
    _assert_production_safe,
)
from taleem_core.platform.feature_flags import StaticFlagProvider
from taleem_core.ports import llm_anthropic as la
from taleem_core.ports.llm import InMemoryCostLedger, LearnerQuota, LLMRequest, Tier
from taleem_core.tools import ai_teacher_eval as ev
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE

APPROVED: dict[str, str] = {
    "provider": "anthropic",
    "api_key": "sk-ant-test-not-a-real-key",
    "inference_geo": "us",
    "zdr_confirmed": "true",
    "fd03_approval_ref": "FD-03/2026-11-01",
}
_SETTINGS_FIELDS = {
    "provider": "ai_provider",
    "api_key": "ai_anthropic_api_key",
    "inference_geo": "ai_inference_geo",
    "zdr_confirmed": "ai_zdr_confirmed",
    "fd03_approval_ref": "ai_fd03_approval_ref",
}
_STUDENT = "0192f7a1-8c3e-7d4b-9a12-3f4e5d6c7b8a"  # a uuid7-shaped pseudonymous ref
SAFE_EN = ev.GOLDEN_CASES[0].output  # an accepted English direct rephrase
Handler = Callable[[httpx2.Request], httpx2.Response]


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*_: Any, **__: Any) -> None:
        raise AssertionError("a test tried to open a real network connection")

    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


@pytest.fixture(scope="module")
def lesson() -> LessonView:
    return ev.published_fractions_lesson()


def _message(
    text: str = SAFE_EN,
    *,
    stop_reason: str = "end_turn",
    stop_details: dict[str, Any] | None = None,
    usage: dict[str, int] | None = None,
) -> dict[str, Any]:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": la.EXPLANATION_MODEL,
        "content": [{"type": "text", "text": text}] if text else [],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "stop_details": stop_details,
        "usage": usage
        or {
            "input_tokens": 40,
            "output_tokens": 30,
            "cache_creation_input_tokens": 200,
            "cache_read_input_tokens": 0,
        },
    }


class _Transport:
    """Records every request body the SDK sends; replies with ``handler``."""

    def __init__(self, handler: Handler) -> None:
        self.handler = handler
        self.bodies: list[dict[str, Any]] = []
        self.headers: list[httpx2.Headers] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.bodies.append(json.loads(request.content))
        self.headers.append(request.headers)
        return self.handler(request)


def _reply(payload: dict[str, Any], status: int = 200) -> Handler:
    return lambda _req: httpx2.Response(status, json=payload)


def _gateway(transport: _Transport) -> la.AnthropicGateway:
    return la.AnthropicGateway(
        **APPROVED,
        max_retries=0,
        http_client=anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(transport)),
    )


def _prompt(
    lesson: LessonView,
    style: ait.ExplanationStyle = ait.ExplanationStyle.DIRECT,
    locale: str = "en",
    band: str = "middle",
) -> gate.GroundedPrompt:
    utterances = ait.explain(lesson, style, TemplatedTeachingRuntime(), locale)
    return gate.build_prompt(lesson, utterances, locale=locale, grade_band=band)


def _request(lesson: LessonView, **overrides: Any) -> LLMRequest:
    p = _prompt(lesson)
    fields: dict[str, Any] = {"prompt": p.render(), "tier": Tier.LIGHT, "grounding": p.texts}
    fields.update(overrides)
    return LLMRequest(**fields)


# ---------------------------------------------------------------- construction refusal matrix


def test_inert_by_default_no_configuration_builds_nothing() -> None:
    settings = Settings(database_url="")
    assert la.settings_problems(settings)  # nothing is set in any environment
    with pytest.raises(la.AnthropicNotApprovedError, match="not_approved"):
        la.anthropic_gateway(settings)


@pytest.mark.parametrize(
    ("field", "value", "problem"),
    [
        ("provider", "", "TALEEM_AI_PROVIDER"),
        ("provider", "openai", "TALEEM_AI_PROVIDER"),
        ("api_key", "", "TALEEM_AI_ANTHROPIC_API_KEY"),
        ("api_key", "sk ant", "TALEEM_AI_ANTHROPIC_API_KEY"),
        ("inference_geo", "", "TALEEM_AI_INFERENCE_GEO"),
        ("inference_geo", "global", "TALEEM_AI_INFERENCE_GEO"),
        ("inference_geo", "eu", "TALEEM_AI_INFERENCE_GEO"),
        ("zdr_confirmed", "", "TALEEM_AI_ZDR_CONFIRMED"),
        ("zdr_confirmed", "yes", "TALEEM_AI_ZDR_CONFIRMED"),
        ("zdr_confirmed", "false", "TALEEM_AI_ZDR_CONFIRMED"),
        ("fd03_approval_ref", "", "TALEEM_AI_FD03_APPROVAL_REF"),
        ("fd03_approval_ref", "x", "TALEEM_AI_FD03_APPROVAL_REF"),
        ("fd03_approval_ref", "has spaces in it", "TALEEM_AI_FD03_APPROVAL_REF"),
    ],
)
def test_each_missing_or_wrong_setting_refuses_construction(
    field: str, value: str, problem: str
) -> None:
    config = {**APPROVED, field: value}
    with pytest.raises(la.AnthropicNotApprovedError) as info:
        la.AnthropicGateway(**config)
    assert len(info.value.problems) == 1 and problem in info.value.problems[0]
    settings = Settings(database_url="", **{_SETTINGS_FIELDS[k]: v for k, v in config.items()})
    with pytest.raises(la.AnthropicNotApprovedError):
        la.anthropic_gateway(settings)


def test_complete_configuration_constructs_without_any_network_call() -> None:
    gateway = la.AnthropicGateway(**APPROVED)
    assert gateway.name == "anthropic" and gateway.inference_geo == "us"
    assert gateway.fd03_approval_ref == "FD-03/2026-11-01"
    assert gateway.sent == []


def test_the_sdks_own_credentials_never_switch_it_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-the-machine")
    for key, value in APPROVED.items():
        if key != "api_key":
            monkeypatch.setenv(f"TALEEM_AI_{_SETTINGS_FIELDS[key][3:].upper()}", value)
    monkeypatch.delenv("TALEEM_AI_ANTHROPIC_API_KEY", raising=False)
    settings = Settings(database_url="")
    assert settings.ai_provider == "anthropic" and settings.ai_inference_geo == "us"
    with pytest.raises(la.AnthropicNotApprovedError, match="TALEEM_AI_ANTHROPIC_API_KEY"):
        la.anthropic_gateway(settings)


def test_api_key_is_not_in_the_settings_repr() -> None:
    assert "sk-ant-test" not in repr(Settings(ai_anthropic_api_key=APPROVED["api_key"]))


def _ai_problems(settings: Settings) -> list[str]:
    try:
        _assert_production_safe(settings)
    except InsecureConfigurationError as exc:
        return [p for p in str(exc).split("; ") if "TALEEM_AI_PROVIDER=anthropic" in p]
    return []


def test_production_fails_closed_on_a_partial_configuration() -> None:
    prod = {"environment": Environment.PRODUCTION, "ai_learner_daily_cost_micros": 50_000}
    full = {_SETTINGS_FIELDS[k]: v for k, v in APPROVED.items()}
    assert _ai_problems(Settings(**prod, **full)) == []
    for key in ("ai_anthropic_api_key", "ai_inference_geo", "ai_zdr_confirmed"):
        partial = {**full, key: ""}
        assert len(_ai_problems(Settings(**prod, **partial))) == 1, key
    # FD-07: a real provider in production also needs the per-learner cost envelope.
    no_cap = Settings(environment=Environment.PRODUCTION, **full)
    assert any("COST_MICROS" in p for p in _ai_problems(no_cap))


def test_app_stays_on_the_deterministic_engine_without_full_approval() -> None:
    partial = create_app(Settings(database_url="", ai_provider="anthropic"))
    assert partial.state.ai_gateway is None
    full = {_SETTINGS_FIELDS[k]: v for k, v in APPROVED.items()}
    approved = create_app(Settings(database_url="", **full))
    assert isinstance(approved.state.ai_gateway, la.AnthropicGateway)


# ---------------------------------------------------------------- data-minimisation guard


@pytest.mark.parametrize("style", list(ait.ExplanationStyle))
@pytest.mark.parametrize("locale", ["en", "ur", "xx"])
@pytest.mark.parametrize("band", ["early", "middle", "senior", "unknown"])
def test_every_grounded_prompt_the_app_builds_passes_the_guard(
    lesson: LessonView, style: ait.ExplanationStyle, locale: str, band: str
) -> None:
    p = _prompt(lesson, style, locale, band)
    la.assert_minimised(LLMRequest(p.render(), Tier.LIGHT, p.texts, never_send=(_STUDENT,)))


def _violations(lesson: LessonView) -> dict[str, LLMRequest]:
    base = _request(lesson)
    p = _prompt(lesson)
    first = p.texts[0]

    def with_passage(text: str) -> LLMRequest:
        texts = (*p.texts, text)
        body = "\n".join(f"[{i}] {t}" for i, t in enumerate(texts, 1))
        header = base.prompt.split("\nPassages:\n")[0]
        return LLMRequest(f"{header}\nPassages:\n{body}", Tier.LIGHT, texts)

    return {
        "child_free_text_appended": _request(lesson, prompt=base.prompt + "\nI feel sad at home"),
        "name_line": _request(
            lesson, prompt=base.prompt.replace("Passages:", "Learner: Ali\nPassages:")
        ),
        "tampered_instructions": _request(
            lesson, prompt=base.prompt.replace("Rephrase", "Summarise", 1)
        ),
        "grounding_not_in_prompt": _request(lesson, grounding=(*p.texts, "extra")),
        "no_grounding": _request(lesson, grounding=()),
        "family_code": with_passage("Your code is K7QM-3XPZ."),
        "uuid_ref": with_passage(f"{first} {_STUDENT}"),
        "email": with_passage("Write to ali@example.com today."),
        "phone": with_passage("Call 0300 1234567 now."),
        "account_ref": with_passage("See student:abc for details."),
        "never_send": _request(lesson, never_send=(first[:12],)),
        "option_not_authored": _request(
            lesson, selected_option="I hate school", selected_option_choices=("1/4", "1/2")
        ),
        "option_multiline": _request(
            lesson, selected_option="1/4\nhi", selected_option_choices=("1/4\nhi",)
        ),
        "output_budget": _request(lesson, max_output_tokens=50_000),
    }


def test_the_guard_refuses_anything_beyond_lesson_passages(lesson: LessonView) -> None:
    for name, request in _violations(lesson).items():
        with pytest.raises(la.MinimisationViolationError):
            la.assert_minimised(request)
        transport = _Transport(_reply(_message()))
        with pytest.raises(la.MinimisationViolationError):
            _gateway(transport).complete(request)
        assert transport.bodies == [], f"{name} reached the transport"


def test_the_written_marker_child_answer_is_never_transmitted() -> None:
    transport = _Transport(_reply(_message('{"score": 1, "met": true}')))

    class _Clear:
        def is_clear(self, text: str) -> bool:
            return True

    marker = LLMWrittenWorkMarker(
        gateway=_gateway(transport),
        flags=StaticFlagProvider({AI_RUBRIC_MARKING_FLAG}),
        distress_classifier=_Clear(),
        fd03_approved=True,
    )
    rubric = RubricForMarking("Explains halves", 2)
    assert marker.propose(prompt="Explain", rubric=rubric, text="my own words") is None
    assert transport.bodies == []


def test_an_authored_selected_option_is_sent_after_the_cache_breakpoint(
    lesson: LessonView,
) -> None:
    transport = _Transport(_reply(_message()))
    request = _request(lesson, selected_option="1/4", selected_option_choices=("1/4", "1/2"))
    _gateway(transport).complete(request)
    blocks = transport.bodies[0]["messages"][0]["content"]
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[0]["text"] == request.prompt
    assert blocks[1] == {"type": "text", "text": "The learner selected this option: 1/4"}
    assert "1/2" not in json.dumps(transport.bodies[0])  # the other choices stay in-process


# ---------------------------------------------------------------- request shape + caching


def test_request_shape_caching_residency_and_opaque_id(lesson: LessonView) -> None:
    transport = _Transport(_reply(_message()))
    gateway = _gateway(transport)
    request = _request(lesson, never_send=(_STUDENT,))
    gateway.complete(request)
    gateway.complete(request)
    body = transport.bodies[0]
    assert body["model"] == "claude-sonnet-5-5"
    assert body["inference_geo"] == "us"
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["messages"][0]["content"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["messages"][-1]["role"] == "user"  # no assistant prefill
    assert body["thinking"] == {"type": "between_tools"}
    assert body["output_config"] == {"effort": "medium"}
    for rejected in ("temperature", "top_p", "top_k", "tool_choice", "tools", "fallbacks"):
        assert rejected not in body
    ids = [b["metadata"]["user_id"] for b in transport.bodies]
    assert all(i.startswith("req-") for i in ids) and ids[0] != ids[1]  # fresh per request
    assert _STUDENT not in json.dumps(transport.bodies)
    assert str(transport.headers[0].get("host")) == "api.anthropic.com"
    assert [s.request_id for s in gateway.sent] == ids


def test_base_url_cannot_be_redirected_by_the_environment(
    monkeypatch: pytest.MonkeyPatch, lesson: LessonView
) -> None:
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://attacker.example")
    transport = _Transport(_reply(_message()))
    _gateway(transport).complete(_request(lesson))
    assert str(transport.headers[0].get("host")) == "api.anthropic.com"


def test_cost_is_computed_from_usage_tokens_with_the_residency_premium() -> None:
    # 40 in x $2 + 30 out x $10 + 200 cache-write x $2.50 + 0 read = 880 micro-USD, x1.1 for "us".
    assert (
        la.cost_micros(
            "claude-sonnet-5-5",
            input_tokens=40,
            output_tokens=30,
            cache_write_tokens=200,
            cache_read_tokens=0,
            inference_geo="us",
        )
        == 968
    )
    assert (
        la.cost_micros(
            "claude-sonnet-5-5",
            input_tokens=0,
            output_tokens=0,
            cache_write_tokens=0,
            cache_read_tokens=1_000,
            inference_geo="us",
        )
        == 220
    )
    assert (
        la.cost_micros(
            "claude-haiku-5-5",
            input_tokens=1,
            output_tokens=0,
            cache_write_tokens=0,
            cache_read_tokens=0,
            inference_geo="us",
        )
        == 1
    )  # rounded up, never under-counted


# ---------------------------------------------------------------- through the AI Teacher


class _Curriculum:
    def __init__(self, lesson: LessonView) -> None:
        self._lesson = lesson

    def lesson_for(self, objective_code: str) -> LessonView | None:
        return self._lesson if objective_code == self._lesson.objective_code else None

    def published_lessons(self) -> list[LessonView]:
        return [self._lesson]

    def published_graph(self) -> CurriculumGraph:
        return CurriculumGraph(objectives=())


class _Knowledge:
    def snapshot(self, student_ref: str) -> None:
        return None


def _teacher(
    lesson: LessonView,
    transport: _Transport,
    *,
    quota: LearnerQuota | None = None,
    ledger: InMemoryCostLedger | None = None,
    events: list[SafetyEvent] | None = None,
) -> tuple[AITeacherService, InMemoryCostLedger]:
    ledger = ledger if ledger is not None else InMemoryCostLedger()
    sink = events.append if events is not None else None
    tier = GenerativeTier(
        gateway=_gateway(transport),
        flags=StaticFlagProvider({gate.GENERATIVE_FLAG}),
        ai_teaching_consent=lambda _ref: True,
        kill_switch_engaged=lambda: False,
        cost_meter=ledger,
        safety_events=sink,
        quota=quota,
    )
    service = AITeacherService(
        None,  # type: ignore[arg-type]  # explain() never touches the session service
        _Knowledge(),  # type: ignore[arg-type]
        _Curriculum(lesson),
        TemplatedTeachingRuntime(),
        CurriculumGraph(objectives=()),
        DecisionConfig(),
        lambda: 1000.0,
        generative=tier,
    )
    return service, ledger


def _explain(service: AITeacherService) -> dict[str, Any]:
    result = service.explain(_STUDENT, OBJECTIVE_CODE, style="direct", locale="en")
    assert result is not None
    return result


def test_mocked_success_is_gated_labelled_and_ledgered(lesson: LessonView) -> None:
    transport = _Transport(_reply(_message()))
    events: list[SafetyEvent] = []
    service, ledger = _teacher(lesson, transport, events=events)
    generation = _explain(service)["generation"]
    assert generation["status"] == "accepted"
    explanation = generation["explanation"]
    assert explanation["text"] == SAFE_EN
    assert explanation["generated"] is True and explanation["verified"] is False
    assert explanation["provider"] == "anthropic:claude-sonnet-5-5"
    [record] = ledger.records
    assert record.learner_ref == _STUDENT and record.provider == "anthropic:claude-sonnet-5-5"
    assert (record.prompt_tokens, record.completion_tokens, record.cost_micros) == (240, 30, 968)
    assert events[-1].decision == "accepted" and events[-1].cost_micros == 968
    assert _STUDENT not in json.dumps(transport.bodies)


def test_mocked_unsafe_output_is_refused_by_the_gate_but_still_billed(
    lesson: LessonView,
) -> None:
    transport = _Transport(_reply(_message(f"{SAFE_EN} Visit https://example.com")))
    service, ledger = _teacher(lesson, transport)
    generation = _explain(service)["generation"]
    assert generation == {"status": "refused", "fallback": "authored", "explanation": None}
    assert ledger.calls == 1 and ledger.total_cost_micros == 968


_REFUSAL = _message(
    "",
    stop_reason="refusal",
    stop_details={"type": "refusal", "category": "general_harms"},
    usage={
        "input_tokens": 40,
        "output_tokens": 0,
        "cache_creation_input_tokens": 200,
        "cache_read_input_tokens": 0,
    },
)


def _raise(exc: Exception) -> Handler:
    def handler(_req: httpx2.Request) -> httpx2.Response:
        raise exc

    return handler


@pytest.mark.parametrize(
    ("handler", "reason", "billed"),
    [
        (_reply(_REFUSAL), "ProviderRefusedError", 638),  # 40 in + 200 cache write, no output
        (_reply(_message("cut off", stop_reason="max_tokens")), "ProviderIncompleteError", 968),
        (_raise(httpx2.ReadTimeout("slow")), "ProviderTimeoutError", 0),
        (_raise(httpx2.ConnectError("down")), "ProviderConnectionError", 0),
        (
            _reply({"type": "error", "error": {"type": "rate_limit_error", "message": "x"}}, 429),
            "ProviderRateLimitedError",
            0,
        ),
        (
            _reply({"type": "error", "error": {"type": "api_error", "message": "x"}}, 500),
            "ProviderResponseError",
            0,
        ),
        (
            _reply({"type": "error", "error": {"type": "overloaded_error", "message": "x"}}, 529),
            "ProviderResponseError",
            0,
        ),
    ],
)
def test_refusals_stop_reasons_timeouts_and_errors_fall_back_to_authored_content(
    lesson: LessonView, handler: Handler, reason: str, billed: int
) -> None:
    transport = _Transport(handler)
    events: list[SafetyEvent] = []
    service, ledger = _teacher(lesson, transport, events=events)
    result = _explain(service)
    assert result["generation"] == {
        "status": "unavailable",
        "fallback": "authored",
        "explanation": None,
    }
    assert result["utterances"]  # the authored explanation is served, unchanged
    assert events[-1].decision == "unavailable" and events[-1].reason == reason
    assert ledger.total_cost_micros == billed  # billed-but-unusable calls still count
    assert ledger.calls == (1 if billed else 0)


def test_quota_is_enforced_before_any_call(lesson: LessonView) -> None:
    transport = _Transport(_reply(_message()))
    quota = LearnerQuota(max_calls=10, max_tokens=10_000, max_cost_micros=968)
    service, ledger = _teacher(lesson, transport, quota=quota)
    assert _explain(service)["generation"]["status"] == "accepted"
    assert "generation" not in _explain(service)  # cost cap reached: templated engine only
    assert len(transport.bodies) == 1 and ledger.calls == 1


# ---------------------------------------------------------------- evaluation CLI


def test_eval_cli_refuses_the_real_provider_without_approval(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in (
        "TALEEM_AI_PROVIDER",
        "TALEEM_AI_ANTHROPIC_API_KEY",
        "TALEEM_AI_INFERENCE_GEO",
        "TALEEM_AI_ZDR_CONFIRMED",
        "TALEEM_AI_FD03_APPROVAL_REF",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-the-machine")  # must not count
    assert ev.main(["--provider", "anthropic"]) == 2
    err = capsys.readouterr().err
    assert "refusing --provider anthropic" in err and "TALEEM_AI_FD03_APPROVAL_REF" in err


def _golden_replier(lesson: LessonView) -> Handler:
    """Reply with a safe golden output for whichever golden context the prompt was rendered for."""
    outputs: dict[str, str] = {}
    for case in ev.GOLDEN_CASES:
        if case.expect == "accept":
            outputs[_prompt(lesson, case.style, case.locale, case.grade_band).render()] = (
                case.output
            )

    def handler(request: httpx2.Request) -> httpx2.Response:
        prompt = json.loads(request.content)["messages"][0]["content"][0]["text"]
        return httpx2.Response(200, json=_message(outputs[prompt]))

    return handler


def test_eval_cli_runs_the_golden_set_against_the_mocked_real_model(
    monkeypatch: pytest.MonkeyPatch, lesson: LessonView, tmp_path: Any
) -> None:
    transport = _Transport(_golden_replier(lesson))
    monkeypatch.setattr(ev, "anthropic_gateway", lambda _settings: _gateway(transport))
    out = tmp_path / "report.json"
    assert ev.main(["--provider", "anthropic", "--json", str(out)]) == 0
    real = json.loads(out.read_text(encoding="utf-8"))["real_model"]
    safe = [c for c in ev.GOLDEN_CASES if c.expect == "accept"]
    assert real["passed"] is True and real["accept_rate"] == 1.0
    assert real["human_review_required"] is True
    assert len(real["cases"]) == len(safe) == len(transport.bodies)
    assert real["cost_micros"] == 968 * len(safe)


def test_real_model_thresholds_fail_on_refusals(lesson: LessonView) -> None:
    refusal = _message("", stop_reason="refusal", stop_details={"type": "refusal"})
    report = ev.evaluate_real_model(_gateway(_Transport(_reply(refusal))), lesson=lesson)
    assert not report.passed and report.unavailable == len(report.results)
    assert "REAL-MODEL FAIL" in report.render()
