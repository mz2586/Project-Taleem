"""Demo-cohort building blocks (DEMO_COHORT_CONTRACT): the reader-cohort context, lesson audience
(hashing + validation), the ``demo-placeholder/`` rule in every environment, the learner inheriting
its guardian's cohort through a non-HTTP method, the build-step switch and the reader resolver
failing closed."""

from __future__ import annotations

import copy
import importlib.util
import threading
import time
from pathlib import Path
from types import ModuleType

import pytest
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import studio_audio_resolver
from taleem_core.contexts.curriculum_studio.domain import validation
from taleem_core.contexts.curriculum_studio.domain.audio import (
    DEMO_PLACEHOLDER_AUDIO,
    known_audio,
    resolver_for_audience,
)
from taleem_core.contexts.curriculum_studio.domain.content import Locale, MediaRef
from taleem_core.contexts.curriculum_studio.domain.quality import Gate, Severity
from taleem_core.contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
from taleem_core.main import create_app
from taleem_core.platform.cohort import (
    DEMO,
    REAL,
    current_reader_cohort,
    install_reader,
    normalise_cohort,
    reading_as,
    reset_reader,
    visible_to,
)
from taleem_core.platform.config import Settings
from tests.studio_helpers import make_valid_lesson

_SECRET = "cohort-rules-test-secret-0123456789abcdef"  # noqa: S105 (test fixture)
REF = "demo-placeholder/audio/X/ur.mp3"


# --------------------------------------------------------------------------------- reader cohort


def test_visibility_is_two_way_and_fails_closed() -> None:
    assert visible_to("", REAL) and visible_to("", DEMO) and visible_to(None, REAL)
    assert not visible_to(DEMO, REAL)
    assert visible_to(DEMO, DEMO)
    assert not visible_to("staff-only", DEMO) and not visible_to("staff-only", REAL)
    assert not visible_to(7, DEMO)
    assert normalise_cohort("demo") == DEMO
    assert normalise_cohort("DEMO") == REAL and normalise_cohort(None) == REAL


def test_reader_defaults_to_real_and_resolves_lazily_once() -> None:
    assert current_reader_cohort() == REAL
    calls: list[int] = []

    def resolve() -> str:
        calls.append(1)
        return DEMO

    token = install_reader(resolve)
    try:
        assert calls == []  # nothing resolved until a read needs it
        assert current_reader_cohort() == DEMO
        assert current_reader_cohort() == DEMO
        assert calls == [1]
    finally:
        reset_reader(token)
    assert current_reader_cohort() == REAL


def test_a_failing_or_unknown_resolution_reads_as_real() -> None:
    def boom() -> str:
        raise RuntimeError("identity down")

    for resolver in (boom, lambda: "staff", lambda: "Demo"):
        token = install_reader(resolver)
        try:
            assert current_reader_cohort() == REAL
        finally:
            reset_reader(token)


def test_reading_as_is_scoped_and_reaches_worker_threads_of_the_context() -> None:
    import contextvars

    seen: list[str] = []
    with reading_as(DEMO):
        ctx = contextvars.copy_context()
        worker = threading.Thread(target=lambda: seen.append(ctx.run(current_reader_cohort)))
        worker.start()
        worker.join()
    assert seen == [DEMO]
    assert current_reader_cohort() == REAL


# --------------------------------------------------------------------------------- lesson audience


def test_audience_is_hashed_only_when_set() -> None:
    lesson = make_valid_lesson()
    before = lesson.content_hash()
    lesson.metadata.audience = ""
    assert lesson.content_hash() == before  # existing hashes do not change
    lesson.metadata.audience = DEMO
    assert lesson.content_hash() != before


def _placeholdered(audience: str):  # type: ignore[no-untyped-def]
    lesson = make_valid_lesson()
    lesson.metadata.audience = audience
    lesson.student_explanation.audio_ref = {
        Locale.UR: "demo-placeholder/audio/L1/ur.mp3",
        Locale.EN: "demo-placeholder/audio/L1/en.mp3",
    }
    lesson.offline_package = "demo-placeholder/offline/L1"
    lesson.visual_concepts = [
        MediaRef(
            media_id="demo-placeholder/visual/L1",
            kind="svg",
            alt_text=copy.deepcopy(lesson.visual_concepts[0].alt_text),
        )
    ]
    return lesson


@pytest.mark.parametrize("production", [True, False])
def test_demo_lesson_with_placeholders_passes_in_every_environment(production: bool) -> None:
    audio = studio_audio_resolver(known_audio(set()), production=production)
    result = validation.validate(_placeholdered(DEMO), audio_assets=audio)
    assert result.ok, [
        (g.gate.value, [f.message for f in g.findings]) for g in result.gate_results if not g.passed
    ] + [f.message for f in result.structural if f.severity is Severity.BLOCKER]


@pytest.mark.parametrize("production", [True, False])
def test_real_lesson_with_placeholders_fails_its_gates(production: bool) -> None:
    audio = studio_audio_resolver(known_audio(set()), production=production)
    result = validation.validate(_placeholdered(""), audio_assets=audio)
    assert not result.ok
    failed = {g.gate for g in result.gate_results if not g.passed}
    assert {Gate.ACCESSIBILITY, Gate.PERFORMANCE} <= failed
    assert any("demo-placeholder/" in f.message for f in result.structural)


def test_a_registry_listing_a_placeholder_still_cannot_pass_a_real_lesson() -> None:
    registry = known_audio({"demo-placeholder/audio/L1/ur.mp3", "demo-placeholder/audio/L1/en.mp3"})
    result = validation.validate(_placeholdered(""), audio_assets=registry)
    accessibility = next(g for g in result.gate_results if g.gate is Gate.ACCESSIBILITY)
    assert not accessibility.passed


def test_unknown_audience_is_a_blocker() -> None:
    lesson = make_valid_lesson()
    lesson.metadata.audience = "everyone"
    result = validation.validate(lesson)
    assert any(
        "unknown audience" in f.message and f.severity is Severity.BLOCKER
        for f in result.structural
    )


def test_placeholder_resolver_rules() -> None:
    assert DEMO_PLACEHOLDER_AUDIO.exists(REF)
    assert not DEMO_PLACEHOLDER_AUDIO.exists("demo-placeholder/")
    assert not DEMO_PLACEHOLDER_AUDIO.exists("x/demo-placeholder/a.mp3")
    real_registry = known_audio({"audio/real.mp3"})
    assert resolver_for_audience(DEMO, real_registry).exists(REF)
    assert resolver_for_audience(DEMO, real_registry).exists("audio/real.mp3")
    assert not resolver_for_audience("", real_registry).exists(REF)
    assert resolver_for_audience("", real_registry).exists("audio/real.mp3")


# --------------------------------------------------------------------------------- accounts


def test_learner_inherits_cohort_and_only_the_service_method_sets_it() -> None:
    app = create_app(Settings(kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    identity = app.state.identity_service
    with TestClient(app) as c:
        reg = c.post(
            "/v1/identity/guardians",
            json={
                "email": "parent.x@example.org",
                "passphrase": "a long synthetic passphrase 4410",
                "displayName": "P",
            },
        )
        assert reg.status_code == 201, reg.text
        guardian_ref = reg.json()["guardian"]["guardian_ref"]
        h = {"Authorization": f"Bearer {reg.json()['session']['access_token']}"}
        first = c.post(
            "/v1/identity/learners", json={"displayName": "One", "pin": "4826"}, headers=h
        )
        assert first.status_code == 201
        assert identity.assign_family_cohort(guardian_ref=guardian_ref, cohort=DEMO) == 2
        assert identity.assign_family_cohort(guardian_ref=guardian_ref, cohort=DEMO) == 0
        second = c.post(
            "/v1/identity/learners", json={"displayName": "Two", "pin": "7391"}, headers=h
        )
        assert second.status_code == 201
        with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
            assert uow.guardians.get(guardian_ref).cohort == DEMO  # type: ignore[union-attr]
            assert {x.cohort for x in uow.learners.for_guardian(guardian_ref)} == {DEMO}
        # A rename / PIN reset (ordinary saves) never clears it.
        ref = second.json()["student_ref"]
        assert c.post(
            f"/v1/identity/learners/{ref}/pin:reset", json={"pin": "5937"}, headers=h
        ).status_code in (200, 204)
        assert identity.learner_cohort(ref) == DEMO
        with pytest.raises(ValueError, match="unknown cohort"):
            identity.assign_family_cohort(guardian_ref=guardian_ref, cohort="staff")


def test_the_reader_resolver_fails_closed_on_a_bad_token() -> None:
    app = create_app(Settings(kdf_iterations=1_000, jwt_dev_secret=_SECRET))
    with TestClient(app) as c:
        bad = {"Authorization": "Bearer not-a-token"}
        expired = {
            "Authorization": "Bearer "
            + sign_hs256({"sub": "x", "role": "student", "exp": int(time.time()) - 10}, _SECRET)
        }
        for headers in (bad, expired, {}):
            # Unauthenticated: the route refuses as before; the cohort resolver never raises.
            assert c.get("/v1/offline/packages", headers=headers).status_code == 401


# --------------------------------------------------------------------------------- build step


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "vercel_migrate.py"


def _build_step() -> ModuleType:
    spec = importlib.util.spec_from_file_location("vercel_migrate_cohort", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_step_runs_the_demo_cohort_seeder(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []
    import taleem_core.tools.demo_cohort as dc

    monkeypatch.setattr(dc, "seed_from_environment", lambda: called.append(True) or 0)
    monkeypatch.setenv("TALEEM_DEMO_SEED", "1")
    monkeypatch.setenv("TALEEM_ENV", "production")
    assert _build_step()._seed_demo_fixture() == 0
    assert called == [True]
