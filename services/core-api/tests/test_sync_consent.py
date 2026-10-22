"""Offline sync honours live consent and account status (child-safety control).

A device can hold a child's answers for days; between recording and upload a guardian may withdraw
consent or an operator may suspend the learner. These tests prove the sync endpoint re-checks the
identity context on every batch — with a still-valid access token, and with a privileged operator
token — and that a refused batch writes nothing at all (so the client can hold it intact).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.identity.adapters.persistence.uow import SqlIdentityUnitOfWork
from taleem_core.contexts.identity.domain.accounts import AccountStatus
from taleem_core.contexts.learning.adapters.persistence.uow import LearningUnitOfWork
from taleem_core.contexts.sync.consent_gate import (
    CONSENT_REQUIRED,
    LEARNER_INACTIVE,
    IdentitySyncGate,
    SyncRefusedError,
    enforce,
)
from taleem_core.contexts.sync.domain import DeltaType, Status, SyncDelta, SyncStore
from taleem_core.contexts.sync.service import DurableSyncCoordinator, learners_touched
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.ids import uuid7
from tests.test_sync_evidence import _attempt_delta, _publish_fractions

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)
_PIN = "4813"
_FAST_KDF = 1_000


# ------------------------------------------------------------------------------- unit: the gate


@dataclass
class _Learner:
    can_sign_in: bool = True


@dataclass
class _Consent:
    permits_sign_in: bool = True


def _gate(
    learners: dict[str, _Learner], consents: dict[str, bool], *, require_enrolled: bool = True
) -> IdentitySyncGate:
    return IdentitySyncGate(
        lambda ref: _Consent(consents.get(ref, False)),
        learners.get,
        require_enrolled=require_enrolled,
    )


def test_gate_refuses_withdrawn_consent_and_inactive_learners() -> None:
    gate = _gate({"ok": _Learner(), "nc": _Learner(), "susp": _Learner(False)}, {"ok": True})
    assert gate.refusal("ok") is None
    assert gate.refusal("nc") == CONSENT_REQUIRED
    assert gate.refusal("susp") == LEARNER_INACTIVE  # status is checked before consent


def test_gate_fails_closed_for_unknown_learners_when_enrolment_is_required() -> None:
    assert _gate({}, {}).refusal("ghost") == CONSENT_REQUIRED
    # Dev/test only: synthetic HS256 learners have no account and are permitted.
    assert _gate({}, {}, require_enrolled=False).refusal("ghost") is None
    # ...but an account WITHOUT consent is refused in every environment.
    assert _gate({"nc": _Learner()}, {}, require_enrolled=False).refusal("nc") == CONSENT_REQUIRED


def test_enforce_is_deterministic_and_ignores_blank_refs() -> None:
    gate = _gate({"a": _Learner(), "b": _Learner()}, {"a": True})
    enforce(gate, ["", "a"])  # permitted
    with pytest.raises(SyncRefusedError) as info:
        enforce(gate, ["b", "a", "b"])
    assert (info.value.code, info.value.student_ref) == (CONSENT_REQUIRED, "b")
    enforce(None, ["anyone"])  # no gate wired → no-op (back-compat for pure engine tests)


class _CountingSink:
    def __init__(self) -> None:
        self.calls = 0

    def apply_attempt(self, delta: SyncDelta) -> Status:
        self.calls += 1
        return Status.APPLIED


def _attempt(ref: str, cid: str) -> SyncDelta:
    return SyncDelta(cid, DeltaType.ATTEMPT_SUBMITTED, f"student:{ref}|x", {"student_ref": ref})


def test_a_refused_batch_applies_nothing_not_even_the_permitted_learners_items() -> None:
    store = SyncStore()
    sink = _CountingSink()
    gate = _gate({"ok": _Learner(), "nc": _Learner()}, {"ok": True})
    coordinator = DurableSyncCoordinator(store, sink, gate)
    progress = SyncDelta("p1", DeltaType.PROGRESS, "student:ok|lesson:L", {"block": 1}, 0)
    with pytest.raises(SyncRefusedError):
        coordinator.apply_batch([_attempt("ok", "a1"), progress, _attempt("nc", "a2")])
    assert sink.calls == 0
    assert store.server_cursor == 0
    assert not store.is_seen("a1") and not store.is_seen("p1")  # a later re-send is not a dup


def test_acting_learner_is_gated_even_for_non_attempt_deltas() -> None:
    gate = _gate({"nc": _Learner()}, {})
    coordinator = DurableSyncCoordinator(SyncStore(), _CountingSink(), gate)
    pref = SyncDelta("p", DeltaType.PREFERENCE, "student:nc|pref:locale", {"value": "ur"})
    assert learners_touched([pref], "nc") == {"nc"}
    with pytest.raises(SyncRefusedError):
        coordinator.apply_batch([pref], acting_learner="nc")


# ------------------------------------------------------------------- end to end: composed app


@pytest.fixture
def app() -> FastAPI:
    application = create_app(
        Settings(database_url="", kdf_iterations=_FAST_KDF, jwt_dev_secret=_SECRET)
    )
    _publish_fractions(application)
    return application


def _family(client: TestClient) -> tuple[dict[str, str], str, str]:
    """Register a guardian, enrol + consent a learner, sign the learner in. Returns
    (guardian auth, student_ref, learner access token)."""
    reg = client.post(
        "/v1/identity/guardians",
        json={"email": "parent@example.com", "passphrase": _PASSPHRASE, "displayName": "Fatima"},
    )
    assert reg.status_code == 201, reg.text
    guardian = {"Authorization": f"Bearer {reg.json()['session']['access_token']}"}
    family_code = reg.json()["guardian"]["family_code"]
    learner = client.post(
        "/v1/identity/learners",
        json={"displayName": "Ayesha", "pin": _PIN, "gradeLevel": 4},
        headers=guardian,
    )
    assert learner.status_code == 201, learner.text
    ref = str(learner.json()["student_ref"])
    consent = client.post(
        "/v1/identity/consents",
        json={
            "studentRef": ref,
            "scopes": ["learning_data"],
            "attestation": "I am this child's parent and I agree.",
        },
        headers=guardian,
    )
    assert consent.status_code == 200, consent.text
    signin = client.post(
        "/v1/identity/learners:signin",
        json={"familyCode": family_code, "displayName": "Ayesha", "pin": _PIN},
    )
    assert signin.status_code == 200, signin.text
    return guardian, ref, str(signin.json()["session"]["access_token"])


def _delta(ref: str, seq: int) -> dict[str, object]:
    return _attempt_delta(
        student=ref,
        item_ref="p1-one-of-four",
        option=0,
        client_event_id=uuid7(),
        evidence_id=uuid7(),
        client_seq=seq,
    )


def _post(client: TestClient, token: str, deltas: list[dict[str, object]]) -> tuple[int, dict]:
    r = client.post(
        "/v1/sync/batch",
        json={"cursor": 0, "deltas": deltas},
        headers={"Authorization": f"Bearer {token}"},
    )
    return r.status_code, r.json()


def _evidence_count(app: FastAPI, ref: str) -> int:
    with LearningUnitOfWork(app.state.learning_session_factory) as uow:
        knowledge = uow.knowledge.get(ref)
        return len(knowledge.evidence) if knowledge else 0


def _system_token() -> str:
    exp = int(time.time()) + 3600
    return sign_hs256({"sub": "ops", "role": "system", "exp": exp}, _SECRET)


def test_consented_learner_syncs(app: FastAPI) -> None:
    client = TestClient(app)
    _, ref, token = _family(client)
    status, body = _post(client, token, [_delta(ref, 1)])
    assert status == 200, body
    assert [r["status"] for r in body["results"]] == ["applied"]
    assert _evidence_count(app, ref) == 1


def test_withdrawn_consent_stops_sync_on_the_next_batch_with_a_still_valid_token(
    app: FastAPI,
) -> None:
    client = TestClient(app)
    guardian, ref, token = _family(client)
    assert _post(client, token, [_delta(ref, 1)])[0] == 200

    withdrawn = client.post(
        "/v1/identity/consents:withdraw", json={"studentRef": ref}, headers=guardian
    )
    assert withdrawn.status_code == 200

    # The learner's access token has not expired — the gate must not trust it.
    status, body = _post(client, token, [_delta(ref, 2), _delta(ref, 3)])
    assert status == 403
    assert body["code"] == CONSENT_REQUIRED
    assert ref not in str(body)  # no child identifier in the problem body
    assert _evidence_count(app, ref) == 1  # nothing from the refused batch was written


def test_withdrawn_consent_also_blocks_non_attempt_deltas_for_that_learner(app: FastAPI) -> None:
    client = TestClient(app)
    guardian, ref, token = _family(client)
    client.post("/v1/identity/consents:withdraw", json={"studentRef": ref}, headers=guardian)
    pref = {
        "clientEventId": uuid7(),
        "type": "preference.set",
        "entityKey": f"student:{ref}|pref:locale",
        "clientSeq": 1,
        "payload": {"value": "ur"},
    }
    status, body = _post(client, token, [pref])
    assert status == 403 and body["code"] == CONSENT_REQUIRED


def test_a_privileged_operator_cannot_bypass_withdrawn_consent(app: FastAPI) -> None:
    client = TestClient(app)
    guardian, ref, _ = _family(client)
    client.post("/v1/identity/consents:withdraw", json={"studentRef": ref}, headers=guardian)
    status, body = _post(client, _system_token(), [_delta(ref, 1)])
    assert status == 403 and body["code"] == CONSENT_REQUIRED
    assert _evidence_count(app, ref) == 0


def test_a_suspended_learner_cannot_sync(app: FastAPI) -> None:
    client = TestClient(app)
    _, ref, token = _family(client)
    with SqlIdentityUnitOfWork(app.state.identity_session_factory) as uow:
        learner = uow.learners.get(ref)
        assert learner is not None
        learner.status = AccountStatus.SUSPENDED
        uow.learners.save(learner)
        uow.commit()
    status, body = _post(client, token, [_delta(ref, 1)])
    assert status == 403 and body["code"] == LEARNER_INACTIVE
    assert _evidence_count(app, ref) == 0


def test_an_enrolled_learner_who_never_had_consent_cannot_sync(app: FastAPI) -> None:
    client = TestClient(app)
    reg = client.post(
        "/v1/identity/guardians",
        json={"email": "p2@example.com", "passphrase": _PASSPHRASE, "displayName": "Bilal"},
    )
    guardian = {"Authorization": f"Bearer {reg.json()['session']['access_token']}"}
    learner = client.post(
        "/v1/identity/learners",
        json={"displayName": "Zara", "pin": _PIN, "gradeLevel": 4},
        headers=guardian,
    )
    ref = str(learner.json()["student_ref"])
    status, body = _post(client, _system_token(), [_delta(ref, 1)])
    assert status == 403 and body["code"] == CONSENT_REQUIRED


def test_re_granted_consent_lets_the_held_batch_sync_exactly_once(app: FastAPI) -> None:
    client = TestClient(app)
    guardian, ref, token = _family(client)
    client.post("/v1/identity/consents:withdraw", json={"studentRef": ref}, headers=guardian)
    held = [_delta(ref, 1), _delta(ref, 2)]
    assert _post(client, token, held)[0] == 403

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
    # The refused batch left no in-memory "seen" marks, so the same deltas now apply (not dup).
    status, body = _post(client, token, held)
    assert status == 200, body
    assert [r["status"] for r in body["results"]] == ["applied", "applied"]
    assert _post(client, token, held)[1]["results"][0]["status"] == "duplicate"
    assert _evidence_count(app, ref) == 2
