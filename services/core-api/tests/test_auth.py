"""Tests for the AuthN (JWT seam) and AuthZ (PDP deny-by-default) frameworks."""

from __future__ import annotations

import unittest

from taleem_core.auth import pdp
from taleem_core.auth.jwt_verifier import sign_hs256, verify_hs256
from taleem_core.platform.errors import Problem

SECRET = "dev-only-not-secret"  # noqa: S105 (test constant)


class TestJwtVerifier(unittest.TestCase):
    def test_sign_and_verify_roundtrip(self) -> None:
        token = sign_hs256({"sub": "sys-1", "role": "system", "exp": 9999999999}, SECRET)
        claims = verify_hs256(token, SECRET)
        self.assertEqual(claims.sub, "sys-1")
        self.assertEqual(claims.role, "system")

    def test_expired_token_rejected(self) -> None:
        token = sign_hs256({"sub": "s", "role": "system", "exp": 1000}, SECRET)
        with self.assertRaises(Problem) as ctx:
            verify_hs256(token, SECRET, now=2000)
        self.assertEqual(ctx.exception.status, 401)

    def test_bad_signature_rejected(self) -> None:
        token = sign_hs256({"sub": "s", "role": "system", "exp": 9999999999}, SECRET)
        with self.assertRaises(Problem):
            verify_hs256(token, "wrong-secret")

    def test_malformed_token_rejected(self) -> None:
        with self.assertRaises(Problem):
            verify_hs256("not.a.jwt.token", SECRET)

    def test_missing_required_claims_rejected(self) -> None:
        token = sign_hs256({"sub": "s", "exp": 9999999999}, SECRET)  # no role
        with self.assertRaises(Problem):
            verify_hs256(token, SECRET)


class TestPdp(unittest.TestCase):
    def test_deny_by_default(self) -> None:
        d = pdp.authorize("system", "read", "some.unknown.resource")
        self.assertFalse(d.allow)
        self.assertEqual(d.reason, "deny-by-default")

    def test_explicit_allow(self) -> None:
        d = pdp.authorize("system", "read", "skeleton.protected")
        self.assertTrue(d.allow)

    def test_non_system_role_denied(self) -> None:
        self.assertFalse(pdp.authorize("student", "read", "skeleton.protected").allow)


if __name__ == "__main__":
    unittest.main()
