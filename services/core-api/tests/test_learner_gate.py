"""Per-request learner permission gate on every learner surface (e2e GAP 2, child safety).

A learner access token lives ten minutes. Before this gate, a guardian's consent withdrawal (or an
operator's suspension) took effect only at the next refresh: the journey recorded
``POST /v1/learning/sessions -> 201`` after withdrawal. Every route a student token can call that
reads or writes learning data now re-checks the learner against live identity state on every
request. These tests hold each route family to that, with a still-valid token.
"""

from __future__ import annotations

import time

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from taleem_core.auth.dependencies import bearer_claims
from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.auth.learner_gate import (
    CONSENT_REQUIRED,
    LEARNER_INACTIVE,
    IdentityLearnerGate,
    learner_permission_dependency,
)
from taleem_core.contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
from taleem_core.contexts.identity.domain.accounts import AccountStatus
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.errors import Problem
from taleem_core.vertical_slice.fractions_lesson import LESSON_KEY, OBJECTIVE_CODE
from tests.test_sync_consent import _FAST_KDF, _SECRET, _delta, _family
from tests.test_sync_evidence import _publish_fractions

# One representative of EVERY student-callable learning route, grouped by router family.
# ``{ref}`` is the learner's own ref (IDOR is a separate guard; the gate must fire regardless).
_ROUTES: list[tuple[str, str, str, dict[str, object] | None]] = [
    # learning core (sessions + knowledge/progress)
    ("learning", "POST", "/v1/learning/sessions", {"student_ref": "{ref}"}),
    ("learning", "POST", "/v1/learning/sessions/sess-1:next", None),
    ("learning", "POST", "/v1/learning/sessions/sess-1:teach", {"objective_code": OBJECTIVE_CODE}),
    (
        "learning",
        "POST",
        "/v1/learning/sessions/sess-1:answer",
        {"objective_code": OBJECTIVE_CODE, "item_ref": "p1-one-of-four", "option": 0},
    ),
    (
        "learning",
        "POST",
        "/v1/learning/sessions/sess-1:hint",
        {"objective_code": OBJECTIVE_CODE, "item_ref": "p1-one-of-four", "hint_level": 1},
    ),
    ("learning", "POST", "/v1/learning/sessions/sess-1:end", None),
    ("learning", "GET", "/v1/learning/students/{ref}/knowledge", None),
    ("learning", "GET", "/v1/learning/students/{ref}/progress", None),
    # student read models
    ("student", "GET", "/v1/learning/students/{ref}/today", None),
    ("student", "GET", "/v1/learning/students/{ref}/homework", None),
    ("student", "GET", "/v1/learning/students/{ref}/assessments", None),
    ("student", "GET", "/v1/learning/students/{ref}/reviews", None),
    ("student", "GET", "/v1/learning/students/{ref}/timetable", None),
    ("student", "GET", "/v1/learning/students/{ref}/notifications", None),
    ("student", "POST", "/v1/learning/students/{ref}/notifications/n1:read", None),
    ("student", "GET", "/v1/learning/students/{ref}/achievements", None),
    ("student", "GET", "/v1/learning/students/{ref}/history", None),
    ("student", "GET", "/v1/learning/students/{ref}/recommendations", None),
    # AI teacher
    (
        "ai-teacher",
        "POST",
        "/v1/learning/sessions/sess-1:explain",
        {"objective_code": OBJECTIVE_CODE},
    ),
    ("ai-teacher", "GET", "/v1/learning/students/{ref}/ai-teacher/plan", None),
    ("ai-teacher", "GET", "/v1/learning/students/{ref}/ai-teacher/capabilities", None),
    # offline packages
    ("offline", "GET", "/v1/offline/packages", None),
    ("offline", "GET", f"/v1/offline/packages/{LESSON_KEY}", None),
    ("offline", "GET", "/v1/offline/signing-keys", None),
]


@pytest.fixture
def app() -> FastAPI:
    application = create_app(
        Settings(database_url="", kdf_iterations=_FAST_KDF, jwt_dev_secret=_SECRET)
    )
    _publish_fractions(application)
    return application


def _call(
    client: TestClient, token: str, ref: str, method: str, path: str, body: object
) -> tuple[int, dict[str, object]]:
    url = path.replace("{ref}", ref)
    payload = None
    if isinstance(body, dict):
        payload = {
            k: (v.replace("{ref}", ref) if isinstance(v, str) else v) for k, v in body.items()
        }
    r = client.request(method, url, json=payload, headers={"Authorization": f"Bearer {token}"})
    try:
        data = r.json()
    except ValueError:
        data = {}
    return r.status_code, data if isinstance(data, dict) else {}


def _withdraw(client: TestClient, guardian: dict[str, str], ref: str) -> None:
    r = client.post("/v1/identity/consents:withdraw", json={"studentRef": ref}, headers=guardian)
    assert r.status_code == 200, r.text


def _suspend(app: FastAPI, ref: str) -> None:
    with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
        learner = uow.learners.get(ref)
        assert learner is not None
        learner.status = AccountStatus.SUSPENDED
        uow.learners.save(learner)
        uow.commit()


def test_every_route_family_is_covered() -> None:
    assert {family for family, *_ in _ROUTES} == {"learning", "student", "ai-teacher", "offline"}


@pytest.mark.parametrize(("family", "method", "path", "body"), _ROUTES)
def test_route_refused_after_withdrawal_with_a_still_valid_token(
    app: FastAPI, family: str, method: str, path: str, body: object
) -> None:
    client = TestClient(app)
    guardian, ref, token = _family(client)
    before, _ = _call(client, token, ref, method, path, body)
    assert before != 403, f"{family} {path} refused a consented learner"

    _withdraw(client, guardian, ref)
    status, problem = _call(client, token, ref, method, path, body)
    assert status == 403, f"{family} {method} {path} -> {status}"
    assert problem.get("code") == CONSENT_REQUIRED
    assert ref not in str(problem)  # no learner reference in the refusal


@pytest.mark.parametrize(
    ("family", "method", "path", "body"),
    [r for r in _ROUTES if r[2] in {"/v1/learning/sessions", "/v1/learning/students/{ref}/today"}]
    + [r for r in _ROUTES if r[0] in {"ai-teacher", "offline"}][:2],
)
def test_route_refused_for_a_suspended_learner(
    app: FastAPI, family: str, method: str, path: str, body: object
) -> None:
    client = TestClient(app)
    _, ref, token = _family(client)
    _suspend(app, ref)
    status, problem = _call(client, token, ref, method, path, body)
    assert status == 403, f"{family} {path} -> {status}"
    assert problem.get("code") == LEARNER_INACTIVE
    assert ref not in str(problem)


def test_sync_is_refused_by_the_same_gate(app: FastAPI) -> None:
    client = TestClient(app)
    guardian, ref, token = _family(client)
    _withdraw(client, guardian, ref)
    r = client.post(
        "/v1/sync/batch",
        json={"cursor": 0, "deltas": [_delta(ref, 1)]},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403 and r.json()["code"] == CONSENT_REQUIRED


def test_regranting_consent_restores_access_on_the_next_request(app: FastAPI) -> None:
    client = TestClient(app)
    guardian, ref, token = _family(client)
    _withdraw(client, guardian, ref)
    assert _call(client, token, ref, "GET", "/v1/learning/students/{ref}/today", None)[0] == 403
    regrant = client.post(
        "/v1/identity/consents",
        json={
            "studentRef": ref,
            "scopes": ["learning_data"],
            "attestation": "I am this child's parent and I agree.",
        },
        headers=guardian,
    )
    assert regrant.status_code == 200
    assert _call(client, token, ref, "GET", "/v1/learning/students/{ref}/today", None)[0] == 200
    status, body = _call(client, token, ref, "POST", "/v1/learning/sessions", {"student_ref": ref})
    assert status == 201, body


def test_guardian_routes_are_unaffected_by_the_learner_gate(app: FastAPI) -> None:
    client = TestClient(app)
    guardian, ref, _ = _family(client)
    _withdraw(client, guardian, ref)
    # The guardian keeps managing the family (and can re-grant) after withdrawing.
    for path in ("/v1/identity/me", "/v1/identity/learners", f"/v1/identity/consents/{ref}"):
        assert client.get(path, headers=guardian).status_code == 200, path
    for path in ("/v1/guardian/me", "/v1/guardian/dashboard"):
        r = client.get(path, headers=guardian)
        assert r.status_code == 200, (path, r.status_code, r.text)


def test_system_and_guardian_tokens_pass_the_route_gate() -> None:
    # Unit-level: only a student token is re-checked; other roles fall through to their own authz.
    claims_dep = bearer_claims(_SECRET)
    refused = IdentityLearnerGate(lambda _r: _Nope(), lambda _r: _Active(), require_enrolled=True)
    gate = learner_permission_dependency(refused, claims_dep)
    mini = FastAPI()

    @mini.exception_handler(Problem)
    async def _problem(_request: Request, exc: Problem) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=exc.to_dict())

    @mini.get("/x", dependencies=[Depends(gate)])
    def x() -> dict[str, bool]:
        return {"ok": True}

    client = TestClient(mini)
    exp = int(time.time()) + 600
    for role, expected in (("student", 403), ("guardian", 200), ("system", 200)):
        tok = sign_hs256({"sub": "S1", "role": role, "exp": exp}, _SECRET)
        r = client.get("/x", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == expected, (role, r.status_code)
    assert client.get("/x").status_code == 401  # unauthenticated stays a 401, not a 403


def test_synthetic_dev_learners_without_an_account_keep_working(app: FastAPI) -> None:
    exp = int(time.time()) + 600
    tok = sign_hs256({"sub": "dev-synthetic", "role": "student", "exp": exp}, _SECRET)
    today = "/v1/learning/students/{ref}/today"
    status, _ = _call(TestClient(app), tok, "dev-synthetic", "GET", today, None)
    assert status == 200


def test_production_gate_refuses_learners_without_an_account() -> None:
    gate = IdentityLearnerGate(lambda _r: _Nope(), lambda _r: None, require_enrolled=True)
    assert gate.refusal("ghost") == CONSENT_REQUIRED


class _Nope:
    permits_sign_in = False


class _Active:
    can_sign_in = True
