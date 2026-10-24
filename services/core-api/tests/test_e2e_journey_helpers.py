"""The e2e journey harness: transcript, redaction, rate limits, and both curriculum branches.

The real evidence run drives a uvicorn server over HTTP (``make e2e``). Here the same ``Journey`` is
pointed at the composed app through Starlette's TestClient — an ``httpx.Client`` — so the harness
itself is regression-tested on every ``make test``, with no server and no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.tools import e2e_journey as e2e
from taleem_core.tools.e2e_journey import (
    FAIL,
    FIXTURE_LESSON_ID,
    GAP,
    PASS,
    Journey,
    Transcript,
    report_card_problem,
    retry_after_seconds,
    seed_fixture_lesson,
    synthetic_client_ip,
    synthetic_pin,
)

_FAST_KDF = 1_000
REPORT_STEPS = (
    "guardian asks Taleem for the child's report card (closed period)",
    "guardian lists the child's report cards",
    "guardian reads the report card (hash re-verified)",
    "guardian acknowledges the report card",
    "a second acknowledgement is refused (already seen)",
    "the other guardian cannot list the first child's cards",
    "the other guardian cannot read the first child's card",
    "the other guardian cannot generate a card for the first child",
    "child reads their own report cards",
    "child's report-card read after withdrawal is refused",
)


def _client(*, fixture: bool = False) -> TestClient:
    app = create_app(Settings(database_url="", kdf_iterations=_FAST_KDF))
    if fixture:
        assert seed_fixture_lesson(app.state.studio_session_factory) == "seeded"
        assert seed_fixture_lesson(app.state.studio_session_factory) == "already-present"
    return TestClient(app)


def _titles(transcript: Transcript, outcome: str) -> list[str]:
    return [s.title for s in transcript.steps if s.outcome == outcome]


def test_empty_curriculum_branch_asserts_the_honest_nothing_to_learn_decision() -> None:
    journey = Journey(_client(), expect="empty")
    transcript = journey.run()
    assert transcript.failures == [], transcript.render()
    assert journey.branch == "empty"
    passed = _titles(transcript, PASS)
    assert "planner gives the honest 'nothing to learn' decision" in passed
    assert "child's refresh after withdrawal is refused" in passed
    assert "child's re-sign-in after withdrawal is refused" in passed
    assert "guardian reads the audit trail" in passed
    # With nothing learned the card says so; every report step still passes.
    for title in REPORT_STEPS:
        assert title in passed, title
    assert transcript.verdict() == PASS


def test_fixture_branch_completes_the_synthetic_lesson() -> None:
    journey = Journey(_client(fixture=True), expect="content")
    transcript = journey.run()
    assert transcript.failures == [], transcript.render()
    assert journey.branch == "content"
    passed = _titles(transcript, PASS)
    assert "child completes the lesson (session ends)" in passed
    assert any(t.startswith("child answers item") for t in passed)
    assert any("SYNTHETIC TEST FIXTURE" in n for n in transcript.notes)
    # The student-to-guardian report journey, strict: every step passed.
    for title in REPORT_STEPS:
        assert title in passed, title
    assert journey.answered > 0 and journey.learned is not None
    assert journey.learned[1] == FIXTURE_LESSON_ID and journey.learned[2] == 1
    issued = next(s for s in transcript.steps if s.title == REPORT_STEPS[0])
    assert f"attempts={journey.answered} correct={journey.correct}" in issued.note
    assert f"{FIXTURE_LESSON_ID}@v1 (evidence)" in issued.note


def test_known_gaps_are_recorded_not_hidden_and_strict_mode_fails_them() -> None:
    transcript = Journey(_client(), expect="empty").run()
    # Whatever the current gaps are, each one is labelled and explained in the summary.
    for gap in transcript.gaps:
        assert gap.note
        assert f"step {gap.index:02d}" in transcript.render()
    if transcript.gaps:
        assert transcript.verdict(strict=True).startswith("FAIL")
    assert transcript.verdict(strict=False) == PASS


def test_expectation_mismatch_is_a_failure() -> None:
    transcript = Journey(_client(), expect="content").run()
    assert [s.title for s in transcript.failures] == ["curriculum expectation"]
    assert transcript.verdict() == FAIL


def test_no_secret_reaches_the_rendered_transcript() -> None:
    lines: list[str] = []
    journey = Journey(_client(), expect="empty", echo=lines.append)
    transcript = journey.run()
    rendered = transcript.render() + "\n".join(lines) + json.dumps(transcript.to_dict())
    assert transcript._secrets, "the journey registered its secrets"
    for value in transcript._secrets:
        assert value not in rendered
    assert "access_token" not in rendered
    assert "@example.invalid" in " ".join(transcript._secrets)  # the email is protected


def test_scrub_replaces_longest_secret_first() -> None:
    t = Transcript()
    t.protect("abcd", "abcdefgh", "xy")  # "xy" is too short to protect
    assert t.scrub("token=abcdefgh pin=abcd xy") == "token=[redacted] pin=[redacted] xy"


def test_retry_after_from_header_and_problem_detail() -> None:
    header = httpx.Response(429, headers={"Retry-After": "7"}, json={})
    assert retry_after_seconds(header) == 7.0
    detail = httpx.Response(429, json={"detail": "too many attempts; try again in 12 seconds"})
    assert retry_after_seconds(detail) == 12.0
    assert retry_after_seconds(httpx.Response(429, text="not json")) is None


def test_rate_limit_is_honoured_and_noted() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, json={"detail": "try again in 3 seconds"})
        return httpx.Response(200, json={"status": "ok"})

    slept: list[float] = []
    echoed: list[str] = []
    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://e2e")
    journey = Journey(client, sleep=slept.append, echo=echoed.append)
    journey.step("liveness probe", "GET", "/health", expect=200)
    assert slept == [4.0]
    assert journey.transcript.steps[0].outcome == PASS
    assert "rate limited" in journey.transcript.notes[0]
    assert echoed[0].startswith("   note:")


def test_rate_limit_beyond_the_budget_fails() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"detail": ""})),
        base_url="http://e2e",
    )
    journey = Journey(client, sleep=lambda s: None, max_rate_limit_wait=4.0)
    transcript = journey.run()
    assert transcript.failures[0].status == 429


def test_gap_step_does_not_stop_the_journey() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(201, json={})),
        base_url="http://e2e",
    )
    journey = Journey(client)
    journey.step("x", "POST", "/y", expect=403, gap="known gap")
    assert journey.transcript.steps[0].outcome == GAP
    assert "known gap" in journey.transcript.steps[0].note


def test_transport_error_and_bad_shape_are_failures() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    down = httpx.Client(transport=httpx.MockTransport(boom), base_url="http://e2e")
    assert Journey(down).run().failures[0].title == "transport error"

    def shape(request: httpx.Request) -> httpx.Response:
        status = 201 if request.url.path == "/v1/identity/guardians" else 200
        return httpx.Response(
            status, json={"policy_version": "v", "session": {"access_token": "t"}}
        )

    odd = httpx.Client(transport=httpx.MockTransport(shape), base_url="http://e2e")
    assert Journey(odd).run().failures[0].title == "unexpected response shape"


def test_synthetic_pin_avoids_weak_pins() -> None:
    draws = iter([1111, 1234, 4813])
    assert synthetic_pin(lambda _: next(draws)) == "4813"
    assert len(set(synthetic_pin())) == 4


def test_synthetic_client_ip_is_a_documentation_address_and_is_sent() -> None:
    assert synthetic_client_ip(lambda n: 0) == "192.0.2.1"
    assert synthetic_client_ip().rsplit(".", 1)[0] in {"192.0.2", "198.51.100", "203.0.113"}
    seen: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("x-real-ip"))
        return httpx.Response(200, json={})

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://e2e")
    Journey(client, client_ip="198.51.100.7").step("x", "GET", "/health", expect=200)
    assert seen == ["198.51.100.7"]


def test_unknown_expectation_is_rejected() -> None:
    with pytest.raises(ValueError):
        Journey(httpx.Client(), expect="maybe")


def test_cli_writes_json_and_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client()
    monkeypatch.setattr(e2e.httpx, "Client", lambda **kwargs: client)
    out = tmp_path / "journey.json"
    code = e2e.main(["--expect", "empty", "--json", str(out), "--client-ip", "auto"])
    payload = json.loads(out.read_text())
    assert code == 0
    assert payload["branch"] == "empty"
    assert payload["verdict"] == PASS
    strict = e2e.main(["--expect", "empty", "--strict"])
    assert strict == (2 if payload["verdict"] == PASS and _has_gaps(payload) else 0)
    assert e2e.main(["--expect", "content"]) == 1


def _has_gaps(payload: dict[str, object]) -> bool:
    steps = payload["steps"]
    assert isinstance(steps, list)
    return any(s["outcome"] == GAP for s in steps)


def test_seed_cli_refuses_production_and_missing_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TALEEM_ENV", "production")
    assert e2e.main(["--seed-fixture"]) == 1
    monkeypatch.setenv("TALEEM_ENV", "local")
    monkeypatch.delenv("TALEEM_DATABASE_URL", raising=False)
    assert e2e.main(["--seed-fixture"]) == 1


def test_seed_cli_seeds_a_sqlite_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from taleem_core.contexts.curriculum_studio.adapters.persistence import (
        Base,
        create_db_engine,
        create_session_factory,
        unit_of_work,
    )

    url = f"sqlite:///{tmp_path / 'fixture.db'}"
    engine = create_db_engine(url)
    Base.metadata.create_all(engine)
    monkeypatch.setenv("TALEEM_ENV", "local")
    monkeypatch.setenv("TALEEM_DATABASE_URL", url)
    assert e2e.main(["--seed-fixture"]) == 0
    with unit_of_work(create_session_factory(engine)) as uow:
        lesson = next(x for x in uow.lessons.all() if x.lesson_id == FIXTURE_LESSON_ID)
        assert lesson.workflow.state.value == "published"
    engine.dispose()


def _card(**objective: object) -> dict[str, object]:
    obj = {
        "objective_code": "OBJ",
        "lesson_id": "L-1",
        "lesson_version": 2,
        "lesson_versions": [2],
        "version_source": "evidence",
        **objective,
    }
    return {
        "hash_verified": True,
        "derivation": "taleem.reporting.derive/2",
        "has_evidence": True,
        "totals": {"attempts": 3, "correct": 2},
        "subjects": [{"objectives": [obj]}],
    }


def test_the_report_card_check_reconciles_totals_and_the_version_pin() -> None:
    check = report_card_problem(answered=3, correct=2, learned=("OBJ", "L-1", 2))
    assert check(_card()) is None
    assert "do not reconcile" in str(check({**_card(), "totals": {"attempts": 3, "correct": 3}}))
    assert "version pin" in str(check(_card(version_source="mixed")))
    assert "version pin" in str(check(_card(lesson_version=None, lesson_versions=[1, 2])))
    assert "derivation" in str(check({**_card(), "derivation": "taleem.reporting.derive/1"}))
    assert "not verified" in str(check({**_card(), "hash_verified": False}))
    unpackaged = report_card_problem(answered=3, correct=2, learned=("OBJ", "L-1", None))
    assert "did not carry" in str(unpackaged(_card()))
    empty = report_card_problem(answered=0, correct=0, learned=None)
    assert "has_evidence false" in str(empty(_card()))
    honest = {**_card(), "has_evidence": False, "totals": None, "notice": "no_evidence_in_period"}
    assert empty(honest) is None
