"""Production authentication: asymmetric EdDSA/Ed25519 JWTs + rotating JWKS (FD-14, docs/03 §11)."""

from __future__ import annotations

import time
import unittest

from fastapi.testclient import TestClient

from taleem_core.auth.jwt_verifier import (
    TokenVerifier,
    sign_eddsa,
    sign_hs256,
    verify_eddsa,
)
from taleem_core.auth.keys import KeySet, SigningKey, parse_verify_keys
from taleem_core.auth.setup import build_auth_context
from taleem_core.main import create_app
from taleem_core.platform.config import Environment, Settings
from taleem_core.platform.errors import Problem

SEED_A = bytes(range(32))  # 00..1f
SEED_B = bytes(range(32, 64))  # 20..3f
KEY_A = SigningKey("kid-a", SEED_A)
KEY_B = SigningKey("kid-b", SEED_B)


def _claims(sub: str = "u1", role: str = "student", **extra: object) -> dict[str, object]:
    return {"sub": sub, "role": role, "exp": int(time.time()) + 3600, **extra}


class TestEddsaRoundtrip(unittest.TestCase):
    def test_sign_verify_roundtrip(self) -> None:
        tok = sign_eddsa(_claims(), KEY_A)
        c = verify_eddsa(tok, KeySet((KEY_A.verify_key(),)))
        self.assertEqual((c.sub, c.role), ("u1", "student"))

    def test_tampered_payload_rejected(self) -> None:
        tok = sign_eddsa(_claims(role="student"), KEY_A)
        h, p, s = tok.split(".")
        forged = sign_hs256(_claims(role="curriculum_architect"), "x").split(".")[1]
        with self.assertRaises(Problem) as ctx:
            verify_eddsa(f"{h}.{forged}.{s}", KeySet((KEY_A.verify_key(),)))
        self.assertEqual(ctx.exception.status, 401)

    def test_wrong_key_rejected(self) -> None:
        tok = sign_eddsa(_claims(), KEY_A)
        with self.assertRaises(Problem):
            verify_eddsa(tok, KeySet((KEY_B.verify_key(),)))  # kid-a signed, only kid-b present

    def test_unknown_kid_rejected(self) -> None:
        tok = sign_eddsa(_claims(), KEY_A)
        with self.assertRaises(Problem):
            verify_eddsa(tok, KeySet(()))

    def test_expired_rejected(self) -> None:
        tok = sign_eddsa({"sub": "u", "role": "student", "exp": 1000}, KEY_A)
        with self.assertRaises(Problem):
            verify_eddsa(tok, KeySet((KEY_A.verify_key(),)), now=2000)


class TestRotation(unittest.TestCase):
    def test_keyset_verifies_either_key_during_overlap(self) -> None:
        both = KeySet((KEY_A.verify_key(), KEY_B.verify_key()))
        self.assertEqual(verify_eddsa(sign_eddsa(_claims(), KEY_A), both).sub, "u1")
        self.assertEqual(verify_eddsa(sign_eddsa(_claims(), KEY_B), both).sub, "u1")

    def test_parse_verify_keys(self) -> None:
        pub = KEY_B.public_key.hex()
        keys = parse_verify_keys(f"kid-b:{pub}")
        self.assertEqual(keys[0].kid, "kid-b")
        self.assertEqual(keys[0].public_key, KEY_B.public_key)


class TestJwks(unittest.TestCase):
    def test_jwks_shape(self) -> None:
        doc = KeySet((KEY_A.verify_key(),)).jwks()
        jwk = doc["keys"][0]
        self.assertEqual(jwk["kty"], "OKP")
        self.assertEqual(jwk["crv"], "Ed25519")
        self.assertEqual(jwk["alg"], "EdDSA")
        self.assertEqual(jwk["kid"], "kid-a")
        self.assertIn("x", jwk)  # base64url public key present


class TestTokenVerifierDispatch(unittest.TestCase):
    def test_prod_verifier_rejects_hs256_alg_confusion(self) -> None:
        # Even with a known secret, an asymmetric-only verifier must reject HS256 tokens.
        v = TokenVerifier(keyset=KeySet((KEY_A.verify_key(),)), allow_hs256=False)
        hs = sign_hs256(_claims(), "any-secret")
        with self.assertRaises(Problem):
            v.verify(hs)

    def test_issuer_audience_enforced(self) -> None:
        v = TokenVerifier(
            keyset=KeySet((KEY_A.verify_key(),)),
            allow_hs256=False,
            issuer="taleem-identity",
            audience="taleem-core-api",
        )
        ok = sign_eddsa(_claims(iss="taleem-identity", aud="taleem-core-api"), KEY_A)
        self.assertEqual(v.verify(ok).role, "student")
        with self.assertRaises(Problem):
            v.verify(sign_eddsa(_claims(iss="evil", aud="taleem-core-api"), KEY_A))
        with self.assertRaises(Problem):
            v.verify(sign_eddsa(_claims(iss="taleem-identity", aud="wrong"), KEY_A))

    def test_dev_verifier_accepts_hs256(self) -> None:
        v = TokenVerifier(hs256_secret="s", allow_hs256=True)  # noqa: S106 (test fixture)
        self.assertEqual(v.verify(sign_hs256(_claims(), "s")).sub, "u1")


class TestBuildAuthContext(unittest.TestCase):
    def _prod_settings(self) -> Settings:
        return Settings(
            environment=Environment.PRODUCTION,
            jwt_signing_seed_hex=SEED_A.hex(),
            jwt_signing_kid="kid-a",
            database_url="postgresql+psycopg://u@h/db",
            offline_signing_seed_hex="11" * 32,
        )

    def test_production_is_asymmetric_only(self) -> None:
        ctx = build_auth_context(self._prod_settings())
        self.assertIsNotNone(ctx.signing_key)
        self.assertFalse(ctx.verifier.allow_hs256)
        # A token signed by the prod signing key, with iss/aud, verifies.
        tok = sign_eddsa(
            _claims(iss="taleem-identity", aud="taleem-core-api"), ctx.signing_key  # type: ignore[arg-type]
        )
        self.assertEqual(ctx.verifier.verify(tok).role, "student")
        # HS256 is rejected in production.
        with self.assertRaises(Problem):
            ctx.verifier.verify(sign_hs256(_claims(), "dev-only-not-secret"))

    def test_dev_accepts_hs256(self) -> None:
        ctx = build_auth_context(
            Settings(environment=Environment.LOCAL, jwt_dev_secret="s")  # noqa: S106 (test fixture)
        )
        self.assertIsNone(ctx.signing_key)
        self.assertEqual(ctx.verifier.verify(sign_hs256(_claims(), "s")).sub, "u1")


class TestComposedAppProduction(unittest.TestCase):
    def test_jwks_endpoint_and_eddsa_auth_in_prod(self) -> None:
        settings = Settings(
            environment=Environment.PRODUCTION,
            jwt_signing_seed_hex=SEED_A.hex(),
            jwt_signing_kid="kid-a",
            database_url="",  # empty => in-memory SQLite for the test harness (create_app is lazy)
            offline_signing_seed_hex="11" * 32,
        )
        client = TestClient(create_app(settings))
        # JWKS is public and lists the signing public key.
        jwks = client.get("/.well-known/jwks.json").json()
        self.assertEqual(jwks["keys"][0]["kid"], "kid-a")
        # A correctly-issued EdDSA token authenticates against a protected route.
        tok = sign_eddsa(
            {
                "sub": "sys-1",
                "role": "system",
                "iss": "taleem-identity",
                "aud": "taleem-core-api",
                "exp": int(time.time()) + 3600,
            },
            KEY_A,
        )
        r = client.get("/v1/skeleton/protected", headers={"Authorization": f"Bearer {tok}"})
        self.assertEqual(r.status_code, 200)
        # HS256 is rejected in production, even with the dev secret.
        hs = sign_hs256({"sub": "sys-1", "role": "system", "exp": int(time.time()) + 3600}, "x")
        self.assertEqual(
            client.get(
                "/v1/skeleton/protected", headers={"Authorization": f"Bearer {hs}"}
            ).status_code,
            401,
        )


if __name__ == "__main__":
    unittest.main()
