"""The FD-14 signer port: token and package signing go through ``Signer``, never a raw seed.

Pins four things:

1. ``EnvSeedSigner`` is byte-identical to the pre-port code (golden token and package signature
   captured from the previous implementation, plus the RFC 8032 test vector).
2. Issuance and verification round-trip through the protocol — for the env signer and for a
   ``KmsSigner`` backed by a fake remote that the signer can only ask for signatures.
3. Rotation overlap: two signers' kids published together in the JWKS, both verifying.
4. Refusal paths: the ``kms`` backend cannot be built from configuration while no provider exists,
   and production still refuses the development seed.

Only existing dev/test seeds and the public RFC 8032 vector appear here.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import TokenVerifier, sign_eddsa
from taleem_core.auth.keys import KeySet, SigningKey, VerifyKey
from taleem_core.auth.setup import build_auth_context
from taleem_core.auth.signer import (
    EnvSeedSigner,
    KmsSigner,
    Signer,
    SignerConfigurationError,
    SignerError,
    build_token_signer,
    public_key_from_jwk,
)
from taleem_core.contexts.identity.application.tokens import TokenIssuer
from taleem_core.contexts.learning.adapters.package_signer import (
    Ed25519PackageSigner,
    SignerPackageSigner,
)
from taleem_core.contexts.learning.domain.offline_package import signing_payload
from taleem_core.main import create_app
from taleem_core.platform import ed25519
from taleem_core.platform.config import (
    DEFAULT_OFFLINE_SIGNING_SEED,
    Environment,
    InsecureConfigurationError,
    Settings,
    _assert_production_safe,
)
from taleem_core.platform.errors import Problem

DEV_SEED = bytes(range(32))  # == DEFAULT_OFFLINE_SIGNING_SEED, the well-known dev seed
OTHER_SEED = bytes(range(32, 64))  # the second test seed used by test_auth_asymmetric

# Captured from the pre-port implementation (commit 347eb8e) for kid "kid-golden" over DEV_SEED.
GOLDEN_CLAIMS: dict[str, object] = {"sub": "stu_golden", "role": "student", "exp": 2000000000}
GOLDEN_JWS = (
    "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCIsImtpZCI6ImtpZC1nb2xkZW4ifQ"
    ".eyJzdWIiOiJzdHVfZ29sZGVuIiwicm9sZSI6InN0dWRlbnQiLCJleHAiOjIwMDAwMDAwMDB9"
    ".QV0mPi4ybk7ODGpvhYr1cR_h13SeJ05QMqPRagIP7DNo0bhyk1GUhzXwo_O3qxhgIupRDbPKjqcHERaK9eiABA"
)
GOLDEN_PACKAGE_SIGNATURE = (
    "a4b5e894a24b7a6a89b0476349c9263378cae7c185d383b961cd89a0a609effa"
    "8994533426ba28c1f92d7a3f4b864574c2054c4bd5eca645ea4fe43f5c5f1b02"
)
# RFC 8032 §7.1, TEST 1 (a published test vector, not key material of ours).
RFC8032_SEED = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
RFC8032_PUBLIC = "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a"
RFC8032_SIG_EMPTY = (
    "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
    "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
)


class FakeKms:
    """Stands in for a KMS: holds the key, exposes only its public half and a sign operation."""

    def __init__(self, seed: bytes, key_ref: str = "projects/test/keys/token") -> None:
        self._seed = seed
        self.key_ref = key_ref
        self.public_key = ed25519.public_key(seed)
        self.calls: list[tuple[str, bytes]] = []

    def sign(self, key_ref: str, message: bytes) -> bytes:
        self.calls.append((key_ref, message))
        if key_ref != self.key_ref:
            raise KeyError("no such key")
        return ed25519.sign(message, self._seed)


def _kms_signer(kms: FakeKms, kid: str = "kms-1") -> KmsSigner:
    return KmsSigner(kid=kid, key_ref=kms.key_ref, public_key=kms.public_key, remote_sign=kms.sign)


def _verifier(*signers: Signer) -> TokenVerifier:
    keys = tuple(VerifyKey(s.kid, public_key_from_jwk(s.public_jwk())) for s in signers)
    return TokenVerifier(keyset=KeySet(keys), issuer="iss", audience="aud", allow_hs256=False)


# --------------------------------------------------------------------- byte-identical behaviour


def test_env_seed_signer_reproduces_the_pre_port_token_exactly() -> None:
    assert sign_eddsa(GOLDEN_CLAIMS, EnvSeedSigner("kid-golden", DEV_SEED)) == GOLDEN_JWS
    # The legacy call shape (a bare SigningKey) is wrapped, not re-implemented.
    assert sign_eddsa(GOLDEN_CLAIMS, SigningKey("kid-golden", DEV_SEED)) == GOLDEN_JWS


def test_env_seed_signer_reproduces_the_pre_port_package_signature_exactly() -> None:
    payload = signing_payload("pkg-golden", "v1", "ab" * 32)
    assert Ed25519PackageSigner(DEFAULT_OFFLINE_SIGNING_SEED, "k").sign(payload) == (
        GOLDEN_PACKAGE_SIGNATURE
    )
    via_port = SignerPackageSigner(EnvSeedSigner("k", DEV_SEED))
    assert via_port.sign(payload) == GOLDEN_PACKAGE_SIGNATURE
    assert via_port.key_id == "k"
    assert via_port.public_key_hex == ed25519.public_key(DEV_SEED).hex()


def test_env_seed_signer_matches_the_rfc8032_vector() -> None:
    signer = EnvSeedSigner("rfc", RFC8032_SEED)
    assert signer.sign(b"").hex() == RFC8032_SIG_EMPTY
    assert public_key_from_jwk(signer.public_jwk()).hex() == RFC8032_PUBLIC
    assert signer.algorithm == "EdDSA"
    assert signer.public_jwk()["kid"] == "rfc"


# ------------------------------------------------------------------ round-trip through the port


def test_issuance_and_verification_round_trip_through_the_env_signer() -> None:
    signer = EnvSeedSigner("env-1", OTHER_SEED)
    issued = TokenIssuer(issuer="iss", audience="aud", signer=signer).issue(
        subject="stu_1", role="student", now=1_000_000, ttl_seconds=600
    )
    claims = _verifier(signer).verify(issued.token, now=1_000_100)
    assert (claims.sub, claims.role) == ("stu_1", "student")


def test_issuance_round_trips_through_a_kms_signer_that_never_exposes_the_key() -> None:
    kms = FakeKms(OTHER_SEED)
    signer = _kms_signer(kms)
    issued = TokenIssuer(issuer="iss", audience="aud", signer=signer).issue(
        subject="gdn_1", role="guardian", now=1_000_000, ttl_seconds=600
    )
    assert _verifier(signer).verify(issued.token, now=1_000_100).sub == "gdn_1"
    # The signer asked the "KMS" once, for the JWS signing input, by reference.
    assert len(kms.calls) == 1
    key_ref, message = kms.calls[0]
    assert key_ref == kms.key_ref
    assert issued.token.startswith(message.decode())
    assert not hasattr(signer, "seed") and not hasattr(signer, "_seed")


def test_a_kms_signer_signs_offline_packages_through_the_same_port() -> None:
    kms = FakeKms(OTHER_SEED, key_ref="keys/packages")
    packages = SignerPackageSigner(_kms_signer(kms, kid="pkg-kms-1"))
    payload = signing_payload("pkg", "v1", "cd" * 32)
    signature = bytes.fromhex(packages.sign(payload))
    assert ed25519.verify(signature, payload, bytes.fromhex(packages.public_key_hex))
    assert packages.key_id == "pkg-kms-1"


# --------------------------------------------------------------------- KmsSigner failure modes


def test_a_remote_failure_is_a_signer_error() -> None:
    kms = FakeKms(OTHER_SEED)
    signer = KmsSigner(
        kid="k", key_ref="wrong/ref", public_key=kms.public_key, remote_sign=kms.sign
    )
    with pytest.raises(SignerError, match="remote signing failed"):
        signer.sign(b"m")


def test_a_signature_from_the_wrong_key_is_refused() -> None:
    """A misrouted key reference would otherwise mint tokens every verifier silently rejects."""
    wrong = FakeKms(DEV_SEED)
    signer = KmsSigner(
        kid="k",
        key_ref=wrong.key_ref,
        public_key=ed25519.public_key(OTHER_SEED),
        remote_sign=wrong.sign,
    )
    with pytest.raises(SignerError, match="does not verify"):
        signer.sign(b"m")


@pytest.mark.parametrize("returned", [b"", b"\x00" * 63, b"\x00" * 64])
def test_a_malformed_remote_signature_is_refused(returned: bytes) -> None:
    signer = KmsSigner(
        kid="k",
        key_ref="r",
        public_key=ed25519.public_key(OTHER_SEED),
        remote_sign=lambda _ref, _msg: returned,
    )
    with pytest.raises(SignerError):
        signer.sign(b"m")


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"algorithm": "ES256"}, "EdDSA only"),
        ({"kid": ""}, "key id"),
        ({"key_ref": ""}, "key reference"),
        ({"public_key": b"\x01" * 31}, "32 bytes"),
    ],
)
def test_a_kms_signer_refuses_bad_construction(kwargs: dict[str, object], match: str) -> None:
    base: dict[str, object] = {
        "kid": "k",
        "key_ref": "r",
        "public_key": ed25519.public_key(OTHER_SEED),
        "remote_sign": lambda _ref, _msg: b"",
    }
    with pytest.raises(SignerConfigurationError, match=match):
        KmsSigner(**{**base, **kwargs})  # type: ignore[arg-type]


def test_sign_eddsa_refuses_a_non_eddsa_signer() -> None:
    class Es256Signer(EnvSeedSigner):
        @property
        def algorithm(self) -> str:
            return "ES256"

    with pytest.raises(ValueError, match="unsupported token signing algorithm"):
        sign_eddsa(GOLDEN_CLAIMS, Es256Signer("k", OTHER_SEED))


@pytest.mark.parametrize(
    "jwk",
    [
        {"kty": "EC", "crv": "P-256", "x": "AA"},
        {"kty": "OKP", "crv": "Ed25519", "x": "AAAA"},
    ],
)
def test_public_key_from_jwk_validates(jwk: dict[str, str]) -> None:
    with pytest.raises(SignerConfigurationError):
        public_key_from_jwk(jwk)


@pytest.mark.parametrize(("kid", "seed_hex"), [("", "22" * 32), ("k", "zz"), ("k", "22" * 31)])
def test_the_env_signer_refuses_bad_material(kid: str, seed_hex: str) -> None:
    with pytest.raises(SignerConfigurationError):
        EnvSeedSigner.from_hex(kid, seed_hex)


# --------------------------------------------------------------------------- rotation overlap


def test_rotation_overlap_publishes_both_kids_and_both_verify() -> None:
    old = EnvSeedSigner("kid-old", DEV_SEED)
    new = EnvSeedSigner("kid-new", OTHER_SEED)
    old_public = public_key_from_jwk(old.public_jwk()).hex()
    settings = Settings(
        environment=Environment.PRODUCTION,
        jwt_signing_seed_hex=OTHER_SEED.hex(),
        jwt_signing_kid="kid-new",
        jwt_verification_keys_csv=f"kid-old:{old_public}",
        database_url="",
        offline_signing_seed_hex="11" * 32,
    )
    ctx = build_auth_context(settings)
    assert ctx.signer is not None and ctx.signer.kid == "kid-new"
    assert {k["kid"] for k in ctx.keyset.jwks()["keys"]} == {"kid-new", "kid-old"}
    assert ctx.keyset.by_kid("kid-new") is not None
    assert ctx.keyset.by_kid("kid-new").jwk() == new.public_jwk()  # type: ignore[union-attr]

    claims = {**GOLDEN_CLAIMS, "iss": settings.jwt_issuer, "aud": settings.jwt_audience}
    assert ctx.verifier.verify(sign_eddsa(claims, old), now=1_000).sub == "stu_golden"
    assert ctx.verifier.verify(sign_eddsa(claims, ctx.signer), now=1_000).sub == "stu_golden"

    # Served by the app, too.
    jwks = TestClient(create_app(settings)).get("/.well-known/jwks.json").json()
    assert {k["kid"] for k in jwks["keys"]} == {"kid-new", "kid-old"}

    # Retiring the old key ends its tokens.
    retired = build_auth_context(
        Settings(
            environment=Environment.PRODUCTION,
            jwt_signing_seed_hex=OTHER_SEED.hex(),
            jwt_signing_kid="kid-new",
            offline_signing_seed_hex="11" * 32,
        )
    )
    with pytest.raises(Problem, match="Unknown signing key"):
        retired.verifier.verify(sign_eddsa(claims, old), now=1_000)


def test_an_overlap_key_cannot_shadow_the_active_signers_kid() -> None:
    impostor = ed25519.public_key(DEV_SEED).hex()
    ctx = build_auth_context(
        Settings(
            jwt_signing_seed_hex=OTHER_SEED.hex(),
            jwt_signing_kid="kid-a",
            jwt_verification_keys_csv=f"kid-a:{impostor}",
        )
    )
    assert [k.kid for k in ctx.keyset.keys] == ["kid-a"]
    assert ctx.keyset.keys[0].public_key == ed25519.public_key(OTHER_SEED)


# ------------------------------------------------------------------------------ refusal paths


def test_the_default_backend_is_the_env_seed() -> None:
    assert Settings().signer_backend == "env"
    assert build_token_signer(backend="env", kid="k", seed_hex="") is None
    assert isinstance(build_token_signer(backend="", kid="k", seed_hex="22" * 32), EnvSeedSigner)


def test_the_kms_backend_needs_its_configuration() -> None:
    with pytest.raises(SignerConfigurationError, match="TALEEM_KMS_TOKEN_KEY_REF"):
        build_token_signer(backend="kms", kid="k")


def test_the_kms_backend_cannot_be_built_from_configuration_alone() -> None:
    """No provider adapter exists until FD-14 is decided: config can never conjure one."""
    with pytest.raises(SignerConfigurationError, match="no KMS provider is wired"):
        build_token_signer(
            backend="kms",
            kid="k",
            kms_key_ref="projects/x/keys/token",
            kms_public_key_hex=ed25519.public_key(OTHER_SEED).hex(),
        )


def test_the_kms_backend_builds_only_with_an_injected_remote() -> None:
    kms = FakeKms(OTHER_SEED)
    signer = build_token_signer(
        backend="KMS",
        kid="kms-1",
        kms_key_ref=kms.key_ref,
        kms_public_key_hex=kms.public_key.hex(),
        remote_sign=kms.sign,
    )
    assert isinstance(signer, KmsSigner)
    with pytest.raises(SignerConfigurationError, match="must be hex"):
        build_token_signer(
            backend="kms", kid="k", kms_key_ref="r", kms_public_key_hex="zz", remote_sign=kms.sign
        )


def test_an_unknown_backend_is_refused() -> None:
    with pytest.raises(SignerConfigurationError, match="unknown TALEEM_SIGNER_BACKEND"):
        build_token_signer(backend="vault", kid="k")


def test_the_app_refuses_to_start_on_the_kms_backend_today() -> None:
    settings = Settings(
        signer_backend="kms",
        kms_token_key_ref="projects/x/keys/token",  # noqa: S106 (a key reference, not a secret)
        kms_token_public_key_hex=ed25519.public_key(OTHER_SEED).hex(),
    )
    with pytest.raises(SignerConfigurationError, match="no KMS provider is wired"):
        create_app(settings)


def _prod(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "environment": Environment.PRODUCTION,
        "jwt_signing_seed_hex": "22" * 32,
        "database_url": "postgresql+psycopg://u@h/db",
        "offline_signing_seed_hex": "11" * 32,
    }
    return Settings(**{**base, **overrides})  # type: ignore[arg-type]


def test_production_accepts_a_real_env_seed() -> None:
    _assert_production_safe(_prod())


def test_production_still_refuses_the_development_seed() -> None:
    with pytest.raises(InsecureConfigurationError, match="well-known development seed"):
        _assert_production_safe(_prod(jwt_signing_seed_hex=DEFAULT_OFFLINE_SIGNING_SEED))
    with pytest.raises(InsecureConfigurationError, match="TALEEM_OFFLINE_SIGNING_SEED"):
        _assert_production_safe(_prod(offline_signing_seed_hex=DEFAULT_OFFLINE_SIGNING_SEED))


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        ({"signer_backend": "kms"}, "TALEEM_KMS_TOKEN_KEY_REF"),
        (
            {
                "signer_backend": "kms",
                "kms_token_key_ref": "r",
                "kms_token_public_key_hex": "33" * 32,
            },
            "must be unset when tokens are signed by a KMS key",
        ),
        ({"signer_backend": "vault"}, "not a known backend"),
    ],
)
def test_production_refuses_an_incomplete_or_unknown_signer_backend(
    overrides: dict[str, object], match: str
) -> None:
    with pytest.raises(InsecureConfigurationError, match=match):
        _assert_production_safe(_prod(**overrides))


def test_production_kms_configuration_passes_the_static_check_but_cannot_boot() -> None:
    """Config-level checks pass for a complete KMS config; startup still fails closed."""
    settings = _prod(
        signer_backend="kms",
        jwt_signing_seed_hex="",
        kms_token_key_ref="projects/x/keys/token",  # noqa: S106 (a key reference, not a secret)
        kms_token_public_key_hex=ed25519.public_key(OTHER_SEED).hex(),
    )
    _assert_production_safe(settings)
    with pytest.raises(SignerConfigurationError):
        build_auth_context(settings)
