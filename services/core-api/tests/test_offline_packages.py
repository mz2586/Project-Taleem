"""Tests for offline lesson packages — Phase 6.2A.

Unit tests cover the pure builder: manifest determinism, content-hash **cache invalidation** (a
content change changes the hash/version), the child-safe projection (NO answer keys on device), and
the storage-quota pre-flight. Integration tests exercise the endpoints over the composed app
(SQLite default + PostgreSQL-gated), including auth.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import sign_hs256
from taleem_core.contexts.curriculum_studio.adapters.persistence import unit_of_work as cs_uow
from taleem_core.contexts.curriculum_studio.application.service import CurriculumStudioService
from taleem_core.contexts.curriculum_studio.domain.workflow import ReviewAction
from taleem_core.contexts.learning.adapters.package_signer import Ed25519PackageSigner
from taleem_core.contexts.learning.domain.curriculum_view import ItemView, LessonView
from taleem_core.contexts.learning.domain.offline_package import (
    build_manifest,
    build_package,
    content_hash,
    fits_in_quota,
    lesson_offline_content,
    signing_payload,
)
from taleem_core.main import create_app
from taleem_core.platform import ed25519
from taleem_core.platform.config import DEFAULT_OFFLINE_SIGNING_SEED, Settings
from taleem_core.vertical_slice.fractions_lesson import (
    LESSON_KEY,
    build_fractions_lesson,
)

_SECRET = "dev-only-not-secret"  # noqa: S105 (local-env dev secret)
_REVIEW_ROLES = [
    "subject_expert",
    "instructional_designer",
    "a11y_specialist",
    "language_editor",
    "safety_officer",
]


def _view(explanation_en: str = "A fraction is an equal part.") -> LessonView:
    return LessonView(
        lesson_id="L-x",
        objective_code="MATH-G4-FR-01",
        title={"ur": "کسر", "en": "Fractions"},
        explanation={"ur": "حصہ", "en": explanation_en},
        worked_example_steps=("step one", "step two"),
        practice_items=(
            ItemView(
                item_ref="p1",
                objective_code="MATH-G4-FR-01",
                prompt={"ur": "سوال", "en": "Which fraction?"},
                options=("1/4", "4/1"),
                correct_option=0,
                option_misconceptions={1: "m-bigger-denominator-is-bigger"},
                hints=("Think about slices.",),
            ),
        ),
    )


# ---------------------------------------------------------------- unit: builder


def test_manifest_is_deterministic_for_fixed_now() -> None:
    view = _view()
    a = build_manifest(view, now_ms=1000)
    b = build_manifest(view, now_ms=1000)
    assert a.to_dict() == b.to_dict()
    assert a.version == a.content_hash[:12]
    assert a.package_id == "pkg/L-x"


def test_content_hash_changes_when_content_changes_cache_invalidation() -> None:
    # A content edit MUST change content_hash + version so clients treat the cache as stale.
    h1 = content_hash(lesson_offline_content(_view("A fraction is an equal part.")))
    h2 = content_hash(lesson_offline_content(_view("A fraction is one equal part of a whole.")))
    assert h1 != h2
    assert (
        build_manifest(_view("x"), now_ms=1).version != build_manifest(_view("y"), now_ms=1).version
    )


def test_offline_content_omits_answer_keys() -> None:
    # Safety property: no correct_option / option_misconceptions / corrections reach the device.
    content = lesson_offline_content(_view())
    blob = str(content)
    assert "correct_option" not in content["practice_items"][0]  # type: ignore[index]
    assert "option_misconceptions" not in blob
    assert "correct_option" not in blob
    # But the teaching + attempt surface IS present (prompt, options, hints).
    item = content["practice_items"][0]  # type: ignore[index]
    assert item["prompt"]["en"] == "Which fraction?"  # type: ignore[index]
    assert item["options"] == ["1/4", "4/1"]  # type: ignore[index]
    assert item["hints"] == ["Think about slices."]  # type: ignore[index]


def test_package_asset_hash_matches_content() -> None:
    pkg = build_package(_view(), now_ms=42)
    assert pkg.manifest.content_hash == content_hash(pkg.content)
    assert len(pkg.manifest.assets) == 1
    asset = pkg.manifest.assets[0]
    assert asset.kind == "content" and asset.sha256 == pkg.manifest.content_hash
    assert asset.bytes == pkg.manifest.total_bytes > 0


def test_manifest_created_at_is_injected_not_wallclocked() -> None:
    assert build_manifest(_view(), now_ms=777).created_at_ms == 777


# ---------------------------------------------------------------- unit: Ed25519 signing (6.2C-1)


def test_manifest_unsigned_by_default_backward_compatible() -> None:
    m = build_manifest(_view(), now_ms=1)
    assert m.signature == "" and m.signing_key_id == ""
    d = m.to_dict()
    assert d["signature"] == "" and d["signing_key_id"] == ""


def test_signed_manifest_verifies_against_public_key() -> None:
    signer = Ed25519PackageSigner(DEFAULT_OFFLINE_SIGNING_SEED, "dev-ed25519-1")
    m = build_manifest(_view(), now_ms=1, signer=signer)
    assert m.signing_key_id == "dev-ed25519-1" and len(m.signature) == 128
    payload = signing_payload(m.package_id, m.version, m.content_hash)
    assert ed25519.verify(bytes.fromhex(m.signature), payload, bytes.fromhex(signer.public_key_hex))


def test_signature_binds_content_and_version() -> None:
    # A signature over one package must not verify for different content/version (downgrade guard).
    signer = Ed25519PackageSigner(DEFAULT_OFFLINE_SIGNING_SEED, "k")
    m = build_manifest(_view("first"), now_ms=1, signer=signer)
    other = signing_payload(
        m.package_id, m.version, content_hash(lesson_offline_content(_view("2")))
    )
    assert not ed25519.verify(
        bytes.fromhex(m.signature), other, bytes.fromhex(signer.public_key_hex)
    )


def test_signer_rejects_bad_seed_length() -> None:
    with pytest.raises(ValueError):
        Ed25519PackageSigner("00", "k")


# ---------------------------------------------------------------- unit: storage quota pre-flight


def test_fits_in_quota() -> None:
    assert fits_in_quota(100, available_bytes=200) is True
    assert fits_in_quota(200, available_bytes=200) is True  # exact fit
    assert fits_in_quota(201, available_bytes=200) is False  # over quota
    assert fits_in_quota(100, available_bytes=200, headroom_bytes=150) is False  # headroom reserved


def test_fits_in_quota_rejects_negative() -> None:
    with pytest.raises(ValueError):
        fits_in_quota(-1, available_bytes=10)


# ---------------------------------------------------------------- integration


def _auth(role: str, sub: str) -> dict[str, str]:
    exp = int(time.time()) + 3600
    return {
        "Authorization": f"Bearer {sign_hs256({'sub': sub, 'role': role, 'exp': exp}, _SECRET)}"
    }


def _publish_fractions(app: FastAPI) -> None:
    sf = app.state.studio_session_factory
    clock = lambda: 1000.0  # noqa: E731

    def op(fn: object) -> None:
        with cs_uow(sf) as uow:
            svc = CurriculumStudioService(uow.lessons, uow.publish, clock=clock)
            fn(svc)  # type: ignore[operator]
            uow.commit()

    op(lambda s: s.create(build_fractions_lesson()))
    op(lambda s: s.submit(LESSON_KEY, "subject_author"))
    for role in _REVIEW_ROLES:
        op(lambda s, role=role: s.review(LESSON_KEY, ReviewAction.APPROVE, role))
    op(lambda s: s.publish(LESSON_KEY, "curriculum_architect", "v1"))


def _exercise(app: FastAPI) -> None:
    client = TestClient(app)
    _publish_fractions(app)
    h = _auth("student", "off-stu")

    # Index lists the published package.
    index = client.get("/v1/offline/packages", headers=h)
    assert index.status_code == 200
    packages = index.json()["packages"]
    assert any(p["lesson_id"] == LESSON_KEY for p in packages)
    manifest = next(p for p in packages if p["lesson_id"] == LESSON_KEY)
    assert manifest["version"] == manifest["content_hash"][:12]
    assert manifest["total_bytes"] > 0

    # The full package round-trips and its content hash matches the manifest.
    pkg = client.get(f"/v1/offline/packages/{LESSON_KEY}", headers=h)
    assert pkg.status_code == 200
    body = pkg.json()
    m = body["manifest"]
    assert m["content_hash"] == content_hash(body["content"])
    assert body["content"]["lesson_id"] == LESSON_KEY
    # No answer keys shipped to the device.
    assert "correct_option" not in str(body["content"])

    # 6.2C-1: the manifest is Ed25519-signed, and the public key from /signing-keys verifies it.
    assert m["signing_key_id"] and len(m["signature"]) == 128
    keys = client.get("/v1/offline/signing-keys", headers=h).json()["keys"]
    key = next(k for k in keys if k["key_id"] == m["signing_key_id"])
    assert key["algorithm"] == "Ed25519"
    payload = signing_payload(m["package_id"], m["version"], m["content_hash"])
    assert ed25519.verify(
        bytes.fromhex(m["signature"]), payload, bytes.fromhex(key["public_key_hex"])
    )

    # Unknown lesson → 404.
    assert client.get("/v1/offline/packages/does-not-exist", headers=h).status_code == 404

    # Auth required.
    assert client.get("/v1/offline/packages").status_code == 401
    assert client.get(f"/v1/offline/packages/{LESSON_KEY}").status_code == 401
    assert client.get("/v1/offline/signing-keys").status_code == 401


def test_offline_packages_over_sqlite() -> None:
    _exercise(create_app(Settings(database_url="")))


# ---------------------------------------------------------------- PostgreSQL-gated

PG_URL = os.environ.get("CS_DATABASE_URL")


@pytest.mark.skipif(not PG_URL, reason="CS_DATABASE_URL not set (PostgreSQL required)")
def test_offline_packages_over_postgres() -> None:
    from alembic import command
    from alembic.config import Config

    base = Path(__file__).resolve().parents[1]
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    _exercise(create_app(Settings(database_url=PG_URL or "")))
