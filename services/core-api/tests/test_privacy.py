"""Privacy context: guardian export, two-step erasure, retention dry-run (R1, Phase G criterion).

The centrepiece is the **erasure completeness test**: a learner is seeded through the real APIs
(identity enrol + consent, a learning session with answers, an offline sync batch, the guardian
view, AI usage), erased through ``/v1/privacy``, and then *every table of every schema* — found by
introspecting the ORM metadata, not by a hand-kept list — is scanned for the learner's ref. A table
added later without privacy coverage fails ``test_every_table_is_covered_or_exempt``.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, select, text
from sqlalchemy.orm import Session, sessionmaker

from taleem_core.contexts.curriculum_studio.adapters.persistence import Base as CurriculumBase
from taleem_core.contexts.identity.adapters.persistence.base import IdentityBase
from taleem_core.contexts.identity.adapters.persistence.models import AuditRow, ConsentRow
from taleem_core.contexts.learning.adapters.persistence.base import LearningBase
from taleem_core.contexts.ops.adapters.persistence.base import OpsBase
from taleem_core.contexts.privacy.adapters.coverage import EXEMPT_CATALOG_TABLES, EXEMPT_TABLES
from taleem_core.contexts.privacy.adapters.identity_data import TOMBSTONE_ACTION
from taleem_core.contexts.privacy.application.service import PrivacyService
from taleem_core.contexts.privacy.domain import erasure
from taleem_core.contexts.privacy.domain.policy import (
    PolicyError,
    PrivacyConfig,
    RetainedSet,
    RetentionPolicy,
)
from taleem_core.contexts.reporting.adapters.persistence.base import ReportingBase
from taleem_core.contexts.reporting.adapters.persistence.models import (
    ReportCardAuditRow,
    ReportCardOutboxRow,
    ReportCardRow,
)
from taleem_core.contexts.reporting.domain.report_card import (
    LearnerRecords,
    Period,
    ReportCard,
    derive_body,
    new_card_id,
)
from taleem_core.contexts.safeguarding.adapters.persistence.base import SafeguardingBase
from taleem_core.contexts.safeguarding.adapters.persistence.models import (
    ConcernAuditRow,
    ConcernRow,
)
from taleem_core.contexts.school.adapters.persistence.base import SchoolBase
from taleem_core.contexts.school.adapters.persistence.models import (
    ClassroomRow,
    EnrolmentRow,
    OrganizationRow,
    SchoolAuditRow,
    TeacherRow,
)
from taleem_core.main import create_app
from taleem_core.platform.config import Settings
from taleem_core.platform.errors import Problem
from taleem_core.ports.llm import Tier, UsageRecord
from taleem_core.vertical_slice.fractions_lesson import OBJECTIVE_CODE

from .test_guardian_api import _publish

_PASSPHRASE = "a-guardian-passphrase"  # noqa: S105 (test fixture)
_PIN = "4813"
_FAST_KDF = 1_000

# (metadata, app.state session-factory attribute) for every schema in the platform.
_SCHEMAS: tuple[tuple[MetaData, str], ...] = (
    (IdentityBase.metadata, "identity_session_factory"),
    (LearningBase.metadata, "learning_session_factory"),
    (CurriculumBase.metadata, "studio_session_factory"),
    (OpsBase.metadata, "ops_session_factory"),
    (SchoolBase.metadata, "school_session_factory"),
    (SafeguardingBase.metadata, "safeguarding_session_factory"),
    (ReportingBase.metadata, "reporting_session_factory"),
)
_CHILD_WORDS = "someone at home frightens me"


def _dispose(app: FastAPI) -> None:
    """Close every pooled connection the app opened (PostgreSQL has a finite client budget)."""
    for _metadata, attr in _SCHEMAS:
        engine = getattr(app.state, attr).kw.get("bind")
        if engine is not None:
            engine.dispose()


def _qualified(table: Any) -> str:
    return f"{table.schema}.{table.name}"


# ------------------------------------------------------------------------- seeding (real APIs)


def _enrol_in_class(app: FastAPI, *refs: str) -> None:
    """Put both families' learners in one synthetic class (school rows have no seeding API that
    bypasses teacher sign-in, so they are written directly; the erasure path is what is tested)."""
    tag = uuid.uuid4().hex[:8]
    with app.state.school_session_factory() as s, s.begin():
        s.add(
            OrganizationRow(
                organization_id=f"org-{tag}",
                name="Synthetic school",
                country="ZZ",
                curriculum_pack_id="PK-NCP",
                default_locale="en",
            )
        )
        s.flush()
        s.add(
            TeacherRow(
                teacher_ref=f"tch-{tag}",
                organization_id=f"org-{tag}",
                email=f"t-{tag}@example.com",
                display_name="Teacher",
                passphrase_hash="not-a-real-hash",  # noqa: S106 (synthetic fixture row)
            )
        )
        s.flush()
        s.add(
            ClassroomRow(
                class_id=f"cls-{tag}",
                organization_id=f"org-{tag}",
                teacher_ref=f"tch-{tag}",
                name="4A",
                join_code=f"J{tag}"[:16],
            )
        )
        s.flush()
        for ref in refs:
            s.add(
                EnrolmentRow(
                    class_id=f"cls-{tag}",
                    student_ref=ref,
                    organization_id=f"org-{tag}",
                    approved_by="guardian",
                )
            )
            # The durable join audit (0011) names the learner too, so erasure must cover it.
            s.add(
                SchoolAuditRow(
                    event_id=f"sae-{tag}-{ref}"[:64],
                    action="enrolment.joined",
                    actor_ref="guardian",
                    actor_role="guardian",
                    subject_ref=ref,
                    organization_id=f"org-{tag}",
                    class_id=f"cls-{tag}",
                    at=1.0,
                )
            )


def _issue_report_card(app: FastAPI, ref: str) -> None:
    """A system-issued report card (with its audit + outbox rows) for ``ref``."""
    body = derive_body(
        records=LearnerRecords(ref),
        lessons={},
        period=Period(1, 2),
        context=None,
        learner_display_name="Ayesha",
        issued_by="system",
        issued_by_name="Taleem",
        issued_at=3.0,
        card_id=new_card_id(),
        supersedes=None,
        comment=None,
    )
    card = ReportCard.issue(body)
    with app.state.reporting_session_factory() as s, s.begin():
        s.add(
            ReportCardRow(
                card_id=card.card_id,
                student_ref=ref,
                organization_id="",
                class_id="",
                period_start=1,
                period_end=2,
                body=card.body_json,
                content_hash=card.content_hash,
                issued_by="system",
                issued_at=3.0,
            )
        )
        s.add(
            ReportCardAuditRow(
                event_id=f"rpa_{card.card_id}"[:64],
                action="report_card.issued",
                actor_ref="system",
                actor_role="system",
                subject_ref=ref,
                organization_id="",
                class_id="",
                card_id=card.card_id,
                at=3.0,
            )
        )
        s.add(
            ReportCardOutboxRow(
                id=f"rpo_{card.card_id}"[:64],
                event_type="ReportCardIssued",
                aggregate_id=card.card_id,
                student_ref=ref,
                payload={"card_id": card.card_id, "student_ref": ref},
                occurred_at=3.0,
            )
        )


def _family(client: TestClient, name: str) -> dict[str, Any]:
    reg = client.post(
        "/v1/identity/guardians",
        json={
            "email": f"{uuid.uuid4().hex[:10]}@example.com",
            "passphrase": _PASSPHRASE,
            "displayName": "Guardian",
        },
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    fam = {
        "auth": {"Authorization": f"Bearer {body['session']['access_token']}"},
        "guardian": body["guardian"],
    }
    enrol = client.post(
        "/v1/identity/learners",
        json={"displayName": name, "pin": _PIN, "gradeLevel": 4},
        headers=fam["auth"],
    )
    assert enrol.status_code == 201, enrol.text
    fam["ref"] = str(enrol.json()["student_ref"])
    granted = client.post(
        "/v1/identity/consents",
        json={"studentRef": fam["ref"], "scopes": ["learning_data", "ai_teaching"]},
        headers=fam["auth"],
    )
    assert granted.status_code == 200, granted.text
    signin = client.post(
        "/v1/identity/learners:signin",
        json={"familyCode": fam["guardian"]["family_code"], "displayName": name, "pin": _PIN},
    )
    assert signin.status_code == 200, signin.text
    fam["learner_auth"] = {"Authorization": f"Bearer {signin.json()['session']['access_token']}"}
    return fam


def _activity(client: TestClient, app: FastAPI, fam: dict[str, Any]) -> None:
    ref, h = fam["ref"], fam["learner_auth"]
    started = client.post("/v1/learning/sessions", json={"student_ref": ref}, headers=h)
    assert started.status_code in (200, 201), started.text
    sid = started.json()["session_id"]
    client.post(f"/v1/learning/sessions/{sid}:next", headers=h)
    client.post(
        f"/v1/learning/sessions/{sid}:teach", json={"objective_code": OBJECTIVE_CODE}, headers=h
    )
    for _ in range(2):
        answered = client.post(
            f"/v1/learning/sessions/{sid}:answer",
            json={"objective_code": OBJECTIVE_CODE, "item_ref": "p1-one-of-four", "option": 0},
            headers=h,
        )
        assert answered.status_code == 200, answered.text
    # An offline batch: one attempt (durable evidence) and one progress delta (sync entity state).
    batch = client.post(
        "/v1/sync/batch",
        json={
            "cursor": 0,
            "deltas": [
                {
                    "clientEventId": uuid.uuid4().hex,
                    "type": "attempt.submitted",
                    "entityKey": f"student:{ref}|item:p3",
                    "clientSeq": 1,
                    "payload": {
                        "student_ref": ref,
                        "objective_code": OBJECTIVE_CODE,
                        "item_ref": "p3-denominator",
                        "option": 0,
                        "evidence_id": uuid.uuid4().hex,
                        "session_id": "offline",
                        "context": "practice",
                    },
                },
                {
                    "clientEventId": uuid.uuid4().hex,
                    "type": "progress.updated",
                    "entityKey": f"student:{ref}|lesson:L-math-g4-intro-fractions",
                    "clientSeq": 2,
                    "payload": {"block": 2},
                },
            ],
        },
        headers=h,
    )
    assert batch.status_code == 200, batch.text
    view = client.get(f"/v1/guardian/children/{ref}", headers=fam["auth"])
    assert view.status_code == 200, view.text
    # The AI usage ledger: a metered call for this learner (no provider is wired in tests).
    app.state.ai_cost_ledger.record(
        UsageRecord("stub", Tier.LIGHT, 10, 5, 0, "ai_teacher.rephrase", ref, 1.0)
    )
    # Safeguarding: one concern the child raised, one the guardian raised about the child.
    child = client.post(
        "/v1/safeguarding/concerns",
        json={"category": "felt_unsafe", "text": _CHILD_WORDS},
        headers=h,
    )
    assert child.status_code == 201, child.text
    guardian = client.post(
        "/v1/safeguarding/concerns",
        json={"category": "bullying", "studentRef": ref, "text": "older pupils"},
        headers=fam["auth"],
    )
    assert guardian.status_code == 201, guardian.text


# ------------------------------------------------------------------------- scanning


def _scan(app: FastAPI, ref: str) -> dict[str, int]:
    """Rows mentioning ``ref`` in every table of every schema (substring: stricter than erasure)."""
    hits: dict[str, int] = {}
    for metadata, attr in _SCHEMAS:
        sf: sessionmaker[Session] = getattr(app.state, attr)
        with sf() as s:
            for table in metadata.sorted_tables:
                rows = s.execute(select(table)).mappings().all()
                n = sum(1 for r in rows if ref in json.dumps(dict(r), default=str))
                if n:
                    hits[_qualified(table)] = n
    return hits


def _memory_hits(app: FastAPI, ref: str) -> dict[str, int]:
    svc: PrivacyService = app.state.privacy_service
    return {
        f"{p.name}:{t}": n
        for p in svc.ports
        if p.name in ("learning", "sync", "ai_usage")
        for t, n in p.remaining(ref).items()
        if n
    }


# ------------------------------------------------------------------------- the journey


def _exercise(app: FastAPI, *, blocked: bool = False, safeguarding_kept: bool = True) -> None:
    _publish(app)
    client = TestClient(app)
    fam = _family(client, "Ayesha")
    other = _family(client, "Bilal")  # a control family that must be untouched
    _activity(client, app, fam)
    _activity(client, app, other)
    _enrol_in_class(app, fam["ref"], other["ref"])
    ref = fam["ref"]
    _issue_report_card(app, ref)  # only the erased learner: a left-over card blocks downgrade
    before = _scan(app, ref)
    assert {
        "identity.learner_account",
        "identity.consent_record",
        "identity.refresh_token",
        "identity.audit_event",
        "learning.student_knowledge",
        "learning.objective_mastery",
        "learning.assessment_evidence",
        "school.enrolment",
        "school.enrolment_audit",
        "safeguarding.concern",
        "safeguarding.concern_audit",
        "reporting.report_card",
        "reporting.report_card_audit",
        "reporting.report_card_outbox",
    } <= set(before), before
    assert _memory_hits(app, ref)  # live session, sync entity, AI usage

    # IDOR: another guardian, a learner token, and an unknown ref all fail without disclosure.
    export_url = f"/v1/privacy/learners/{ref}/export"
    assert client.get(export_url, headers=other["auth"]).status_code == 404
    assert (
        client.get(f"/v1/privacy/learners/{ref}/export", headers=fam["learner_auth"]).status_code
        == 403
    )
    nobody = client.get("/v1/privacy/learners/stu_nobody/export", headers=fam["auth"])
    assert nobody.status_code == 404
    assert client.get(f"/v1/privacy/learners/{ref}/export").status_code == 401

    # Export: machine-readable, complete, credentials withheld.
    exported = client.get(f"/v1/privacy/learners/{ref}/export", headers=fam["auth"])
    assert exported.status_code == 200, exported.text
    bundle = exported.json()
    assert bundle["format"] == "taleem.learner-export/1" and bundle["student_ref"] == ref
    sections = bundle["sections"]
    assert sections["identity"]["learner_account"]["student_ref"] == ref
    assert "pin_hash" not in sections["identity"]["learner_account"]
    assert sections["identity"]["consent_records"]
    assert all("token_hash" not in t for t in sections["identity"]["refresh_tokens"])
    assert sections["learning"]["assessment_evidence"]
    assert sections["learning"]["live_sessions"]
    assert sections["sync"]["entities"]
    # The usage ledger is process-local on SQLite and the durable learning.ai_usage_ledger on PG.
    usage = sections["ai_usage"]["usage_records"] + sections["learning"]["ai_usage"]
    assert [u["learner_ref"] for u in usage] == [ref]
    assert sections["guardian"]["stored_rows"] == 0
    assert other["ref"] not in json.dumps(bundle)  # nothing about another family leaks
    # Safeguarding: the guardian's own concern is exported; the child's is withheld, silently.
    raised = sections["safeguarding"]["concerns_raised_by_guardian"]
    assert [c["text"] for c in raised] == ["older pupils"]
    assert _CHILD_WORDS not in json.dumps(bundle) and sections["safeguarding"]["withheld"]

    if blocked:
        # Fail closed: no token is issued and not one row anywhere is touched.
        refused = client.post(f"/v1/privacy/learners/{ref}/erasure-requests", headers=fam["auth"])
        assert refused.status_code == 503, refused.text
        assert refused.json()["code"] == "ERASURE_BLOCKED"
        assert _scan(app, ref) == before
        return

    # Step 1 erases nothing.
    requested = client.post(f"/v1/privacy/learners/{ref}/erasure-requests", headers=fam["auth"])
    assert requested.status_code == 202, requested.text
    token = requested.json()["confirmation_token"]
    assert _scan(app, ref) == before
    # Another guardian cannot confirm it; a tampered token is refused.
    url = f"/v1/privacy/learners/{ref}/erasure:confirm"
    assert (
        client.post(url, json={"confirmationToken": token}, headers=other["auth"]).status_code
        == 404
    )
    bad = client.post(url, json={"confirmationToken": token[:-3] + "AAA"}, headers=fam["auth"])
    assert bad.status_code == 422, bad.text

    # Step 2: irreversible erasure + verification sweep.
    done = client.post(url, json={"confirmationToken": token}, headers=fam["auth"])
    assert done.status_code == 200, done.text
    receipt = done.json()
    assert receipt["verified"] is True and receipt["irreversible"] is True
    tomb = receipt["tombstone_ref"]
    assert tomb.startswith("tomb_") and ref not in tomb

    # THE completeness criterion: zero rows mentioning the ref, in every table of every schema.
    assert _scan(app, ref) == {}
    assert _memory_hits(app, ref) == {}

    # Only the documented tombstone survives, keyed by the tombstone ref.
    with app.state.identity_session_factory() as s:
        consents = s.scalars(select(ConsentRow).where(ConsentRow.student_ref == tomb)).all()
        assert consents and all(set(c.evidence) <= {"method", "attestation"} for c in consents)
        events = s.scalars(select(AuditRow).where(AuditRow.subject_ref == tomb)).all()
        assert [e.action for e in events] == [TOMBSTONE_ACTION]
        assert events[0].detail["retained"]["student_ref_retained"] is False
    # Safeguarding concerns follow the explicit retained-set entry (PENDING M-Gov), never silently.
    kept = receipt["retained"]["safeguarding_concerns"]
    assert kept["kept"] is safeguarding_kept and "PENDING M-Gov" in kept["approval"]
    with app.state.safeguarding_session_factory() as s:
        concerns = s.scalars(select(ConcernRow).where(ConcernRow.subject_ref == tomb)).all()
        raised = s.scalars(select(ConcernAuditRow).where(ConcernAuditRow.actor_ref == tomb)).all()
    if safeguarding_kept:  # re-keyed to the tombstone: the record survives, the ref does not
        assert sorted(c.raised_by_role for c in concerns) == ["guardian", "student"]
        assert [c.raised_by_ref for c in concerns if c.raised_by_role == "student"] == [tomb]
        assert [a.action for a in raised] == ["concern.raised"]
    else:
        assert concerns == [] and raised == []

    # Afterwards: the learner is gone everywhere it could be named; a replay is a 404.
    replay = client.post(url, json={"confirmationToken": token}, headers=fam["auth"])
    assert replay.status_code == 404
    assert client.get(f"/v1/privacy/learners/{ref}/export", headers=fam["auth"]).status_code == 404
    assert client.get(f"/v1/guardian/children/{ref}", headers=fam["auth"]).status_code in (403, 404)
    relogin = client.post(
        "/v1/identity/learners:signin",
        json={"familyCode": fam["guardian"]["family_code"], "displayName": "Ayesha", "pin": _PIN},
    )
    assert relogin.status_code in (401, 403, 404)

    # The control family is intact, and the guardian's own account remains.
    assert _scan(app, other["ref"]).keys() >= {
        "identity.learner_account",
        "learning.assessment_evidence",
    }
    assert client.get("/v1/identity/me", headers=fam["auth"]).status_code == 200


def test_erasure_is_complete_across_every_schema_over_sqlite() -> None:
    _exercise(create_app(Settings(database_url="", kdf_iterations=_FAST_KDF)))


def test_erasure_can_be_configured_to_delete_safeguarding_concerns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TALEEM_PRIVACY_SAFEGUARDING_CONCERNS", "erase")
    app = create_app(Settings(database_url="", kdf_iterations=_FAST_KDF))
    _exercise(app, safeguarding_kept=False)


def test_safeguarding_retention_mode_is_validated() -> None:
    assert RetainedSet().retain_safeguarding is True  # the default, stated in describe()
    described = RetainedSet().describe()["safeguarding_concerns"]
    assert isinstance(described, dict) and described["mode"] == "retain_pseudonymised"
    with pytest.raises(PolicyError):
        RetainedSet(safeguarding_concerns="keep_forever")


PG_URL = os.environ.get("CS_DATABASE_URL")


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_erasure_is_complete_across_every_schema_over_postgres() -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")
    app = create_app(Settings(database_url=PG_URL or "", kdf_iterations=_FAST_KDF))
    try:
        # Migration 0009 lets the append-only evidence trigger admit an erasure DELETE, so on a
        # migrated database nothing may block erasure: the full path must run, never the xfail.
        assert app.state.privacy_service.blockers() == []
        _exercise(app)
        # The live catalog, not just the ORM: a table created by a migration but absent from the
        # metadata would otherwise escape both coverage and the scan.
        with app.state.identity_session_factory() as s:
            names = s.execute(
                text(
                    "SELECT table_schema || '.' || table_name FROM information_schema.tables "
                    "WHERE table_schema NOT IN ('pg_catalog', 'information_schema') "
                    "AND table_type = 'BASE TABLE'"
                )
            ).scalars()
            catalog = set(names)
    finally:
        _dispose(app)
    svc: PrivacyService = app.state.privacy_service
    known = svc.covered_tables() | set(EXEMPT_TABLES) | set(EXEMPT_CATALOG_TABLES)
    assert catalog - known == set(), catalog - known


# ------------------------------------------------------------------------- coverage


def test_every_table_is_covered_or_exempt() -> None:
    app = create_app(Settings(database_url="", kdf_iterations=_FAST_KDF))
    svc: PrivacyService = app.state.privacy_service
    covered = svc.covered_tables()
    every = {_qualified(t) for metadata, _attr in _SCHEMAS for t in metadata.sorted_tables}
    uncovered = every - covered - set(EXEMPT_TABLES)
    assert not uncovered, f"tables with no privacy coverage or exemption: {sorted(uncovered)}"
    assert not (covered & set(EXEMPT_TABLES)), "a table cannot be both covered and exempt"
    stale = {t for t in EXEMPT_TABLES if t not in every}
    assert not stale, f"exemptions for tables that no longer exist: {sorted(stale)}"


# ------------------------------------------------------------------------- policy & tokens


def test_retention_defaults_are_unset_and_purge_disabled() -> None:
    app = create_app(Settings(database_url="", kdf_iterations=_FAST_KDF))
    client = TestClient(app)
    from taleem_core.auth.jwt_verifier import sign_hs256

    def auth(role: str) -> dict[str, str]:
        tok = sign_hs256(
            {"sub": "op-1", "role": role, "exp": int(time.time()) + 3600}, "dev-only-not-secret"
        )
        return {"Authorization": f"Bearer {tok}"}

    report = client.get("/v1/privacy/retention:dry-run", headers=auth("system"))
    assert report.status_code == 200, report.text
    body = report.json()
    assert body["dry_run"] is True and "PENDING M-Gov" in body["approval"]
    assert {c["status"] for c in body["classes"]} == {"not set; purge disabled"}
    assert all(c["would_purge"] is None for c in body["classes"])
    assert client.get("/v1/privacy/retention:dry-run", headers=auth("guardian")).status_code == 403
    policy = client.get("/v1/privacy/policy", headers=auth("system")).json()
    assert policy["retained_after_erasure"]["student_ref_retained"] is False
    assert set(policy["retention"]["periods_seconds"].values()) == {None}


def test_configured_period_reports_but_never_deletes() -> None:
    app = create_app(Settings(database_url="", kdf_iterations=_FAST_KDF))
    svc: PrivacyService = app.state.privacy_service
    app.state.ai_cost_ledger.record(UsageRecord("stub", Tier.LIGHT, 1, 1, 0, "", "stu_x", 1.0))
    configured = PrivacyService(
        svc._identity,  # noqa: SLF001 - same stores, different policy
        svc._stores,  # noqa: SLF001
        PrivacyConfig(retention=RetentionPolicy.from_json('{"ai_usage": 60}')),
        clock=lambda: 10_000.0,
    )
    rows = {c["data_class"]: c for c in configured.retention_dry_run()["classes"]}
    assert rows["ai_usage"]["would_purge"] == 1
    assert rows["ai_usage"]["status"] == "dry-run only; nothing is deleted"
    assert rows["learning_records"]["would_purge"] is None
    assert len(app.state.ai_cost_ledger.records) == 1


def test_policy_rejects_invented_or_invalid_settings() -> None:
    with pytest.raises(PolicyError):
        RetentionPolicy.from_json('{"forever": 1}')
    with pytest.raises(PolicyError):
        RetentionPolicy.from_json('{"ai_usage": -5}')
    with pytest.raises(PolicyError):
        RetentionPolicy.from_json("[1]")
    with pytest.raises(PolicyError):
        RetainedSet(consent_fields=("evidence.raw_ip",))
    with pytest.raises(PolicyError):
        PrivacyConfig.from_env({"TALEEM_PRIVACY_CONFIRMATION_KEY": "short"}, production=True)


def test_production_without_a_key_keeps_erasure_disabled() -> None:
    config = PrivacyConfig.from_env({}, production=True)
    assert not config.erasure_enabled
    app = create_app(Settings(database_url="", kdf_iterations=_FAST_KDF))
    svc: PrivacyService = app.state.privacy_service
    disabled = PrivacyService(svc._identity, svc._stores, config, clock=lambda: 0.0)  # noqa: SLF001
    with pytest.raises(Problem) as exc:
        disabled._require_erasable()  # noqa: SLF001 - the gate every erasure call passes
    assert exc.value.status == 503
    assert disabled.policy()["erasure_enabled"] is False


def test_confirmation_token_is_bound_and_expires() -> None:
    key = b"k" * 32
    req = erasure.new_request("stu_1", "gdn_1", now=100.0, ttl_s=60.0)
    token = erasure.sign(req, key)
    assert erasure.verify(token, key, student_ref="stu_1", guardian_ref="gdn_1", now=120.0) == req
    for kwargs in (
        {"student_ref": "stu_2", "guardian_ref": "gdn_1", "now": 120.0},
        {"student_ref": "stu_1", "guardian_ref": "gdn_2", "now": 120.0},
        {"student_ref": "stu_1", "guardian_ref": "gdn_1", "now": 161.0},
    ):
        with pytest.raises(erasure.ConfirmationError):
            erasure.verify(token, key, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(erasure.ConfirmationError):
        erasure.verify(token, b"x" * 32, student_ref="stu_1", guardian_ref="gdn_1", now=120.0)
    with pytest.raises(erasure.ConfirmationError):
        erasure.verify("garbage", key, student_ref="stu_1", guardian_ref="gdn_1", now=120.0)


def test_tombstone_ref_is_salted_and_one_way() -> None:
    a = RetainedSet(tombstone_salt="one").tombstone_ref("stu_1")
    b = RetainedSet(tombstone_salt="two").tombstone_ref("stu_1")
    assert a != b and "stu_1" not in a
    assert RetainedSet().describe()["student_ref_retained"] is False


def test_consent_evidence_can_be_configured_away() -> None:
    config = PrivacyConfig.from_env(
        {
            "TALEEM_PRIVACY_KEEP_CONSENT_EVIDENCE": "false",
            "TALEEM_PRIVACY_KEEP_ERASURE_EVENT": "false",
        },
        production=False,
    )
    assert config.retained.describe()["consent_evidence"] == {"kept": False}
    assert config.retained.describe()["erasure_event"] == {"kept": False}
    assert config.erasure_enabled  # a per-process key outside production


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_evidence_stays_append_only_outside_an_erasure() -> None:
    """0009 narrows the evidence trigger to one exception: a DELETE with the erasure flag set.
    An UPDATE is refused even with the flag, and a DELETE without it is refused. Exercised on a
    scratch table wired to the same trigger function, so real rows are deterministic."""
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.upgrade(cfg, "head")
    engine = create_engine(PG_URL or "")
    setup = (
        "CREATE TEMP TABLE evidence_probe (id int PRIMARY KEY, v text)",
        "CREATE TRIGGER probe_immutable BEFORE UPDATE OR DELETE ON evidence_probe "
        "FOR EACH ROW EXECUTE FUNCTION learning.forbid_mutation()",
        "INSERT INTO evidence_probe VALUES (1, 'a')",
    )

    def attempt(statement: str, *, flag: bool) -> None:
        with engine.connect() as conn, conn.begin():
            for ddl in setup:
                conn.execute(text(ddl))
            if flag:
                conn.execute(text("SET LOCAL taleem.privacy_erasure = 'on'"))
            conn.execute(text(statement))

    try:
        with pytest.raises(Exception, match="append-only"):
            attempt("UPDATE evidence_probe SET v = 'b'", flag=True)
        with pytest.raises(Exception, match="append-only"):
            attempt("DELETE FROM evidence_probe", flag=False)
        attempt("DELETE FROM evidence_probe", flag=True)  # the one admitted case
    finally:
        engine.dispose()
