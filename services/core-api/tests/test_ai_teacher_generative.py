"""AI Teacher generative tier wiring (Phase D): flag, consent, kill switch, provenance, inertness.

The non-negotiables proven here:

- With the flag OFF the response is byte-identical to the templated tier, and nothing else (consent,
  kill switch, gateway, cost meter) is even consulted.
- With it ON, generation still needs a disengaged kill switch, no pending escalation, and live
  ``ai_teaching`` consent — each checked per request, each failing closed.
- Generated text lives only in a separate ``generation`` block marked ``generated: true`` with the
  LessonView fields it was grounded on; a refused or failed rephrase falls back to the authored
  response, unchanged. Safety events carry no generated or learner text.
- No network provider is reachable: the inert adapter refuses every call, and the stub gateway is
  refused in production.
"""

from __future__ import annotations

import inspect
import io
import json
import socket
import time
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.identity.domain.consent import ConsentEvidence, ConsentScope
from taleem_core.contexts.learning.application.ai_teacher_service import (
    GENERATED_NOTICE_KEY,
    SAFETY_LOG_ALLOW,
    AITeacherService,
    GenerativeTier,
    SafetyEvent,
    logging_safety_sink,
    run_rephrase,
)
from taleem_core.contexts.learning.domain import ai_teacher as ait
from taleem_core.contexts.learning.domain.ai_teacher_gate import GENERATIVE_FLAG
from taleem_core.contexts.learning.domain.curriculum_view import LessonView
from taleem_core.contexts.learning.domain.decision import CurriculumGraph, DecisionConfig
from taleem_core.contexts.learning.domain.knowledge import StudentKnowledge
from taleem_core.contexts.learning.domain.runtime import (
    TemplatedTeachingRuntime,
    TurnKind,
    Utterance,
)
from taleem_core.contexts.learning.domain.values import Mastery
from taleem_core.main import create_app
from taleem_core.platform.config import (
    Environment,
    InsecureConfigurationError,
    Settings,
    _assert_production_safe,
)
from taleem_core.platform.feature_flags import StaticFlagProvider
from taleem_core.platform.logging import StructuredLogger
from taleem_core.ports import llm_inert
from taleem_core.ports.llm import (
    InMemoryCostLedger,
    LearnerQuota,
    LLMGateway,
    LLMRequest,
    ProviderUnavailableError,
    StubLLMGateway,
    Tier,
    UsageRecord,
    UsageSummary,
)
from taleem_core.ports.llm_inert import InertProviderGateway
from taleem_core.tools.ai_teacher_eval import published_fractions_lesson
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE

_STUDENT = "gen-stu"
_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)


@pytest.fixture(scope="module")
def lesson() -> LessonView:
    return published_fractions_lesson()


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
    def __init__(self, knowledge: StudentKnowledge | None = None) -> None:
        self._k = knowledge

    def snapshot(self, student_ref: str) -> StudentKnowledge | None:
        return self._k


class _Spy:
    """A gating callback that records whether it was consulted."""

    def __init__(self, value: bool = True, *, raises: bool = False) -> None:
        self.value, self.raises, self.calls = value, raises, 0

    def __call__(self, *_: Any) -> bool:
        self.calls += 1
        if self.raises:
            raise RuntimeError("check unavailable")
        return self.value


def _service(
    lesson: LessonView,
    tier: GenerativeTier | None = None,
    knowledge: StudentKnowledge | None = None,
) -> AITeacherService:
    return AITeacherService(
        None,  # type: ignore[arg-type]  # explain() never touches the session service
        _Knowledge(knowledge),  # type: ignore[arg-type]
        _Curriculum(lesson),
        TemplatedTeachingRuntime(),
        CurriculumGraph(objectives=()),
        DecisionConfig(),
        lambda: 1000.0,
        generative=tier,
    )


def _tier(
    *,
    flag_on: bool = True,
    gateway: LLMGateway | None = None,
    consent: _Spy | None = None,
    halted: _Spy | None = None,
    events: list[SafetyEvent] | None = None,
    ledger: InMemoryCostLedger | None = None,
) -> GenerativeTier:
    flags = StaticFlagProvider({GENERATIVE_FLAG} if flag_on else set())
    return GenerativeTier(
        gateway=gateway or StubLLMGateway(),
        flags=flags,
        ai_teaching_consent=consent or _Spy(True),
        kill_switch_engaged=halted or _Spy(False),
        cost_meter=ledger if ledger is not None else InMemoryCostLedger(),
        safety_events=events.append if events is not None else None,
    )


def _dump(result: dict[str, Any] | None) -> str:
    return json.dumps(result, ensure_ascii=False)


def _struggling() -> StudentKnowledge:
    k = StudentKnowledge(student_ref=_STUDENT)
    obj = k.ensure_objective(OBJECTIVE_CODE)
    obj.attempts, obj.consecutive_failures, obj.mastery = 4, 3, Mastery(0.2, 0.3)
    return k


_STYLES: tuple[str | None, ...] = (None, *(s.value for s in ait.ExplanationStyle))


# ---------------------------------------------------------------- flag OFF: byte-identical


@pytest.mark.parametrize("knowledge", [None, "struggling"])
def test_flag_off_is_byte_identical_and_consults_nothing(
    lesson: LessonView, knowledge: str | None
) -> None:
    k = _struggling() if knowledge else None
    gateway, consent, halted = StubLLMGateway(), _Spy(True), _Spy(False)
    events: list[SafetyEvent] = []
    ledger = InMemoryCostLedger()
    templated = _service(lesson, None, k)
    flagged_off = _service(
        lesson,
        _tier(
            flag_on=False,
            gateway=gateway,
            consent=consent,
            halted=halted,
            events=events,
            ledger=ledger,
        ),
        k,
    )
    compared = 0
    for style in _STYLES:
        for locale in ("ur", "en"):
            for band in ("early", "middle", "senior"):
                kw: dict[str, Any] = {"style": style, "grade_band": band, "locale": locale}
                a = templated.explain(_STUDENT, OBJECTIVE_CODE, **kw)
                b = flagged_off.explain(_STUDENT, OBJECTIVE_CODE, **kw)
                assert _dump(a) == _dump(b), kw
                assert b is not None and "generation" not in b
                compared += 1
    assert compared == len(_STYLES) * 6
    assert gateway.calls == 0 and consent.calls == 0 and halted.calls == 0
    assert not events and ledger.calls == 0


def test_flag_off_over_http_is_byte_identical_to_the_default_app() -> None:
    default = _http_app(Settings(database_url="", kdf_iterations=1_000))
    stub_but_off = _http_app(Settings(database_url="", kdf_iterations=1_000, ai_provider="stub"))
    bodies = []
    for app in (default, stub_but_off):
        client, sid = _session(app, _STUDENT)
        r = client.post(
            f"/v1/learning/sessions/{sid}:explain",
            json={"objective_code": OBJECTIVE_CODE, "locale": "en"},
            headers=_auth(_STUDENT),
        )
        assert r.status_code == 200
        bodies.append(r.content)
    assert bodies[0] == bodies[1]
    assert b'"generation"' not in bodies[0]
    assert stub_but_off.state.ai_gateway.calls == 0


# ---------------------------------------------------------------- flag ON: gates, provenance


def test_accepted_rephrase_is_labelled_generated_with_provenance(lesson: LessonView) -> None:
    events: list[SafetyEvent] = []
    ledger = InMemoryCostLedger()
    gateway = StubLLMGateway()  # echoes the grounding verbatim: a trivially safe "rephrase"
    svc = _service(lesson, _tier(gateway=gateway, events=events, ledger=ledger))
    baseline = _service(lesson).explain(
        _STUDENT, OBJECTIVE_CODE, style="worked_example_led", locale="en"
    )
    result = svc.explain(_STUDENT, OBJECTIVE_CODE, style="worked_example_led", locale="en")
    assert result is not None and baseline is not None

    gen = result.pop("generation")
    assert result == baseline  # the verified, authored part is untouched
    assert gen["status"] == "accepted" and gen["fallback"] is None
    exp = gen["explanation"]
    assert exp["generated"] is True and exp["source"] == "generated"
    # Uncertainty is explicit: generated text is never presented as verified curriculum fact.
    assert exp["verified"] is False and exp["verified_source"] == "utterances"
    assert exp["notice_key"] == GENERATED_NOTICE_KEY
    assert exp["lesson_id"] == lesson.lesson_id and exp["objective_code"] == OBJECTIVE_CODE
    assert exp["grounded_on"] and all(f.startswith("lesson.") for f in exp["grounded_on"])
    assert "lesson.explanation.en" in exp["grounded_on"]
    assert exp["provider"] == "stub-gateway" and exp["tier"] == Tier.LIGHT.value

    # The model saw only LessonView passages — no learner identifier.
    (request,) = gateway.requests
    assert _STUDENT not in request.prompt
    assert set(request.grounding) <= {u["text"] for u in baseline["utterances"]}

    # Cost accounting: one call recorded, attributed to the (pseudonymous) learner; a stub is free.
    assert ledger.calls == 1 and ledger.total_cost_micros == 0 and ledger.total_tokens > 0
    (usage,) = ledger.records
    assert usage.learner_ref == _STUDENT and usage.recorded_at == 1000.0
    assert ledger.usage_for(_STUDENT).calls == 1 and ledger.usage_for("other").calls == 0

    (event,) = events
    assert event.decision == "accepted" and event.reason == ""
    assert exp["text"] not in json.dumps(event.log_fields(), ensure_ascii=False)


def test_unsafe_output_is_refused_and_the_authored_response_served(lesson: LessonView) -> None:
    leaked = "Which fraction? The answer is 1/4. Email me at a@b.org"
    events: list[SafetyEvent] = []
    svc = _service(lesson, _tier(gateway=StubLLMGateway(lambda _r: leaked), events=events))
    baseline = _service(lesson).explain(_STUDENT, OBJECTIVE_CODE, style="question_led", locale="en")
    result = svc.explain(_STUDENT, OBJECTIVE_CODE, style="question_led", locale="en")
    assert result is not None
    gen = result.pop("generation")
    assert gen == {"status": "refused", "fallback": "authored", "explanation": None}
    assert result == baseline  # refused, not softened: the authored response, verbatim
    assert leaked not in _dump(result)

    (event,) = events
    assert event.decision == "refused"
    assert "answer_leak" in event.reason and "contact_info" in event.reason
    logged = json.dumps(event.log_fields(), ensure_ascii=False)
    assert "a@b.org" not in logged and "answer is" not in logged
    assert event.output_sha256 and event.output_chars == len(leaked)


@pytest.mark.parametrize(
    ("consent", "halted", "knowledge", "reason"),
    [
        (_Spy(False), _Spy(False), None, "no_ai_teaching_consent"),
        (_Spy(raises=True), _Spy(False), None, "no_ai_teaching_consent"),  # fails closed
        (_Spy(True), _Spy(True), None, "kill_switch_engaged"),
        (_Spy(True), _Spy(raises=True), None, "kill_switch_engaged"),  # fails closed
        (_Spy(True), _Spy(False), "struggling", "escalating_to_human"),
    ],
)
def test_generation_needs_consent_running_switch_and_no_escalation(
    lesson: LessonView, consent: _Spy, halted: _Spy, knowledge: str | None, reason: str
) -> None:
    consent.calls = halted.calls = 0
    k = _struggling() if knowledge else None
    gateway = StubLLMGateway()
    events: list[SafetyEvent] = []
    svc = _service(lesson, _tier(gateway=gateway, consent=consent, halted=halted, events=events), k)
    result = svc.explain(_STUDENT, OBJECTIVE_CODE, locale="en")
    assert _dump(result) == _dump(
        _service(lesson, None, k).explain(_STUDENT, OBJECTIVE_CODE, locale="en")
    )
    assert gateway.calls == 0
    assert [e.decision for e in events] == ["skipped"] and events[0].reason == reason


def test_consent_is_read_live_on_every_request(lesson: LessonView) -> None:
    consent = _Spy(True)
    svc = _service(lesson, _tier(consent=consent))
    first = svc.explain(_STUDENT, OBJECTIVE_CODE, locale="en")
    consent.value = False  # the guardian withdraws ai_teaching
    second = svc.explain(_STUDENT, OBJECTIVE_CODE, locale="en")
    assert first is not None and "generation" in first
    assert second is not None and "generation" not in second
    assert consent.calls == 2


def test_flag_can_roll_out_per_learner(lesson: LessonView) -> None:
    flags = StaticFlagProvider()
    flags.enable_for(GENERATIVE_FLAG, "student:pilot-1")
    tier = GenerativeTier(StubLLMGateway(), flags, _Spy(True), _Spy(False))
    svc = _service(lesson, tier)
    assert "generation" in (svc.explain("pilot-1", OBJECTIVE_CODE, locale="en") or {})
    assert "generation" not in (svc.explain("someone-else", OBJECTIVE_CODE, locale="en") or {})


# ---------------------------------------------------------------- provider inertness


def test_inert_provider_refuses_to_construct_without_configuration() -> None:
    for blank in ("", "   "):
        with pytest.raises(ProviderUnavailableError, match="not_configured"):
            InertProviderGateway(blank)


def test_inert_provider_degrades_to_authored_content(lesson: LessonView) -> None:
    gateway = InertProviderGateway("some-vendor")
    events: list[SafetyEvent] = []
    ledger = InMemoryCostLedger()
    svc = _service(lesson, _tier(gateway=gateway, events=events, ledger=ledger))
    result = svc.explain(_STUDENT, OBJECTIVE_CODE, locale="en")
    assert result is not None
    assert result.pop("generation") == {
        "status": "unavailable",
        "fallback": "authored",
        "explanation": None,
    }
    assert result == _service(lesson).explain(_STUDENT, OBJECTIVE_CODE, locale="en")
    assert gateway.attempts == 1 and ledger.calls == 0  # nothing billed for a refused call
    assert events[0].decision == "unavailable"
    assert events[0].reason == "ProviderUnavailableError"


def test_inert_adapter_cannot_reach_a_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_sockets(*_: Any, **__: Any) -> None:
        raise AssertionError("the inert adapter opened a socket")

    monkeypatch.setattr(socket, "socket", no_sockets)
    monkeypatch.setattr(socket, "create_connection", no_sockets)
    for provider, marker in (("", "not_configured"), ("vendor-x", "no_transport")):
        with pytest.raises(ProviderUnavailableError, match=marker):
            InertProviderGateway(provider).complete(LLMRequest("p", Tier.LIGHT, ("g",)))
    source = inspect.getsource(llm_inert)
    for forbidden in ("import socket", "http", "urllib", "requests", "anthropic", "openai"):
        assert forbidden not in source.split('"""', 2)[2], forbidden


def test_stub_gateway_is_refused_in_production() -> None:
    settings = Settings(environment=Environment.PRODUCTION, ai_provider="stub")
    with pytest.raises(InsecureConfigurationError, match="TALEEM_AI_PROVIDER"):
        _assert_production_safe(settings)


def test_default_app_wires_no_provider_at_all() -> None:
    # FD-03: no provider is configured in any environment, so no generative tier is composed.
    app = create_app(Settings(database_url="", ai_provider=""))
    assert app.state.ai_gateway is None
    assert not app.state.flags.is_enabled(GENERATIVE_FLAG)
    named = create_app(Settings(database_url="", ai_provider="some-vendor"))
    assert isinstance(named.state.ai_gateway, InertProviderGateway)


# ---------------------------------------------------------------- per-learner cost + quota


def test_ledger_aggregates_per_learner_and_per_period() -> None:
    ledger = InMemoryCostLedger()
    for ref, at, tokens, cost in (
        ("a", 10.0, 5, 1),
        ("a", 90_000.0, 7, 2),
        ("b", 20.0, 11, 3),
    ):
        ledger.record(
            UsageRecord("p", Tier.LIGHT, tokens, 0, cost, learner_ref=ref, recorded_at=at)
        )
    assert ledger.usage_for("a") == UsageSummary(calls=2, tokens=12, cost_micros=3)
    assert ledger.usage_for("a", since=0, until=86_400) == UsageSummary(1, 5, 1)
    assert ledger.usage_for("a", since=86_400) == UsageSummary(1, 7, 2)
    assert ledger.by_learner(until=86_400) == {
        "a": UsageSummary(1, 5, 1),
        "b": UsageSummary(1, 11, 3),
    }


def test_quota_periods_are_fixed_utc_windows() -> None:
    quota = LearnerQuota(max_calls=2, max_tokens=100)
    assert quota.period_start(86_400 * 3 + 5) == 86_400 * 3
    assert not quota.exhausted(UsageSummary(1, 99, 0))
    assert quota.exhausted(UsageSummary(2, 0, 0)) and quota.exhausted(UsageSummary(0, 100, 0))
    assert LearnerQuota(5, 5, max_cost_micros=10).exhausted(UsageSummary(0, 0, 10))


def test_quota_exhaustion_falls_back_to_the_templated_engine(lesson: LessonView) -> None:
    ledger = InMemoryCostLedger()
    events: list[SafetyEvent] = []
    gateway = StubLLMGateway()
    tier = GenerativeTier(
        gateway,
        StaticFlagProvider({GENERATIVE_FLAG}),
        _Spy(True),
        _Spy(False),
        cost_meter=ledger,
        safety_events=events.append,
        quota=LearnerQuota(max_calls=2, max_tokens=1_000_000),
    )
    svc = _service(lesson, tier)
    templated = _dump(_service(lesson).explain(_STUDENT, OBJECTIVE_CODE, locale="en"))
    first, second, third = (svc.explain(_STUDENT, OBJECTIVE_CODE, locale="en") for _ in range(3))
    assert first and second and "generation" in first and "generation" in second
    # Quota spent: the learner gets the authored engine — not an error, not a weaker safety path.
    assert _dump(third) == templated
    assert gateway.calls == 2 and events[-1].reason == "learner_quota_exhausted"
    # The quota is per learner: someone else is unaffected.
    assert "generation" in (svc.explain("another-learner", OBJECTIVE_CODE, locale="en") or {})


def test_refused_output_still_counts_against_the_quota(lesson: LessonView) -> None:
    ledger = InMemoryCostLedger()
    tier = GenerativeTier(
        StubLLMGateway(lambda _r: "Visit http://x.com"),
        StaticFlagProvider({GENERATIVE_FLAG}),
        _Spy(True),
        _Spy(False),
        cost_meter=ledger,
        quota=LearnerQuota(max_calls=1, max_tokens=1_000_000),
    )
    svc = _service(lesson, tier)
    refused = svc.explain(_STUDENT, OBJECTIVE_CODE, locale="en") or {}
    assert refused["generation"]["status"] == "refused"
    assert "generation" not in (svc.explain(_STUDENT, OBJECTIVE_CODE, locale="en") or {})
    assert ledger.usage_for(_STUDENT).calls == 1


def test_unreadable_quota_fails_closed(lesson: LessonView) -> None:
    class _Broken(InMemoryCostLedger):
        def usage_for(self, *_: Any, **__: Any) -> UsageSummary:
            raise RuntimeError("ledger down")

    gateway = StubLLMGateway()
    tier = GenerativeTier(
        gateway,
        StaticFlagProvider({GENERATIVE_FLAG}),
        _Spy(True),
        _Spy(False),
        cost_meter=_Broken(),
        quota=LearnerQuota(5, 5_000),
    )
    assert "generation" not in (_service(lesson, tier).explain(_STUDENT, OBJECTIVE_CODE) or {})
    assert gateway.calls == 0


# ---------------------------------------------------------------- unverifiable => fallback


def test_unverifiable_grounding_never_calls_the_model(lesson: LessonView) -> None:
    gateway = StubLLMGateway()
    for utterances in ((), (TemplatedTeachingRuntime().affirm("en"),)):  # nothing to ground on
        outcome = run_rephrase(
            lesson,
            utterances,
            gateway,
            locale="en",
            grade_band="middle",
            cost_meter=InMemoryCostLedger(),
        )
        assert outcome.status == "refused" and outcome.text == ""
        assert outcome.verdict is not None and outcome.verdict.rules == ("unverifiable",)
    forged = (Utterance(TurnKind.PRESENT, "not lesson text", "en"),)
    outcome = run_rephrase(
        lesson, forged, gateway, locale="en", grade_band="middle", cost_meter=InMemoryCostLedger()
    )
    assert outcome.status == "refused" and outcome.verdict is not None
    assert outcome.verdict.rules == ("unverifiable",)
    assert gateway.calls == 0


def test_safety_events_log_only_allow_listed_fields() -> None:
    stream = io.StringIO()
    sink = logging_safety_sink(StructuredLogger("t", "INFO", stream=stream, allow=SAFETY_LOG_ALLOW))
    sink(SafetyEvent("refused", "url", "L1", OBJECTIVE_CODE, "en", "middle", output_chars=12))
    record = json.loads(stream.getvalue())
    assert record["event"] == "ai_teacher_safety_event" and record["level"] == "WARN"
    assert record["decision"] == "refused" and record["reason"] == "url"
    assert "text" not in record and "student_ref" not in record


# ---------------------------------------------------------------- end-to-end over HTTP


def _auth(sub: str, role: str = "student") -> dict[str, str]:
    exp = int(time.time()) + 3600
    return {
        "Authorization": f"Bearer {sign_hs256({'sub': sub, 'role': role, 'exp': exp}, _SECRET)}"
    }


def _http_app(settings: Settings) -> FastAPI:
    from tests.test_ai_teacher import _publish_fractions

    app = create_app(settings)
    _publish_fractions(app)
    return app


def _session(app: FastAPI, student_ref: str) -> tuple[TestClient, str]:
    client = TestClient(app)
    r = client.post(
        "/v1/learning/sessions", json={"student_ref": student_ref}, headers=_auth(student_ref)
    )
    assert r.status_code in (200, 201), r.text
    return client, r.json()["session_id"]


def test_end_to_end_flag_on_with_live_consent_and_kill_switch() -> None:
    app = _http_app(
        Settings(
            database_url="",
            kdf_iterations=1_000,
            enabled_flags_csv=GENERATIVE_FLAG,
            ai_provider="stub",
        )
    )
    identity = app.state.identity_service
    guardian = identity.register_guardian(
        email="gen-guardian@example.org",
        passphrase="a-guardian-passphrase",  # noqa: S106 (test fixture)
        display_name="Amina",
    )["guardian"]["guardian_ref"]
    student = identity.enrol_learner(guardian_ref=guardian, display_name="Sara", pin="4826")[
        "student_ref"
    ]
    evidence = ConsentEvidence(attestation="test")
    identity.grant_consent(
        guardian_ref=guardian,
        student_ref=student,
        scopes={ConsentScope.LEARNING_DATA, ConsentScope.AI_TEACHING},
        evidence=evidence,
    )
    client, sid = _session(app, student)

    def explain(locale: str = "en") -> Any:
        return client.post(
            f"/v1/learning/sessions/{sid}:explain",
            json={"objective_code": OBJECTIVE_CODE, "locale": locale},
            headers=_auth(student),
        )

    for locale in ("en", "ur"):
        body = explain(locale).json()
        assert body["generation"]["status"] == "accepted", (locale, body["generation"])
        assert body["generation"]["explanation"]["generated"] is True
        assert body["guardrail"]["generative"] is False  # still certifies the authored utterances

    # The guardian withdraws ai_teaching only: learning continues, generation stops at once.
    identity.withdraw_consent(
        guardian_ref=guardian,
        student_ref=student,
        scopes={ConsentScope.AI_TEACHING},
        evidence=evidence,
    )
    after = explain()
    assert after.status_code == 200 and "generation" not in after.json()

    # The kill switch halts the whole child-facing surface.
    ops = _auth("op-1", "system")
    assert (
        client.post("/v1/ops/kill-switch:engage", json={"reason": "drill"}, headers=ops).status_code
        == 200
    )
    assert explain().status_code == 503
    client.post("/v1/ops/kill-switch:disengage", headers=ops)
    assert app.state.ai_cost_ledger.total_cost_micros == 0
