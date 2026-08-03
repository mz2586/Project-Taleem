# Verification Report — Production Blocker 1: Asymmetric Authentication

**Date:** 2026-08-03  ·  **Milestone:** Production auth (EdDSA / rotating JWKS)  ·  **Status:** ✅ COMPLETE
**Design authority:** FD-14; `docs/03-security-privacy/11-authentication-strategy.md` §7;
`docs/03-security-privacy/13-security-model.md` (Token signing: *asymmetric, rotating JWKS keys*).

---

## 1. What was delivered (no architecture change)

The authentication **seam is unchanged**: `Authorization: Bearer <JWT>` → verify → `Claims` →
deny-by-default PDP. Only the **signature scheme and key handling** moved from the development HS256
shared-secret stub to the documented production form:

| Aspect | Before (dev stub) | After (production) |
| --- | --- | --- |
| Algorithm | HS256 (symmetric, shared secret) | **EdDSA / Ed25519** (asymmetric) |
| Secret exposure | Every verifier holds the forging secret | Verifiers hold **public keys only** |
| Rotation | Flag-day secret swap | **`kid`-addressed key set**, overlapping validity |
| Discovery | none | **`GET /.well-known/jwks.json`** (OKP/Ed25519 JWK) |
| Binding | none | **`iss` + `aud`** enforced in production |
| Downgrade | n/a | **asymmetric-only** in prod (HS256 refused) |
| Boot safety | rejects default secret | **fail-closed** without a real 32-byte signing seed |

**Dependency-free:** built on the repo's existing pure-stdlib `platform/ed25519` (the same primitive
that signs offline lesson packages) — no new packages, consistent with the hexagonal, pure-stdlib
core.

**New / changed code:** `auth/keys.py` (SigningKey/VerifyKey/KeySet + JWKS), `auth/jwt_verifier.py`
(`sign_eddsa`, `verify_eddsa`, unified `TokenVerifier`), `auth/setup.py` (`build_auth_context`),
`auth/dependencies.py` (`bearer_claims_from`), `platform/config.py` (signing config + fail-closed),
`main.py` (verifier wiring + JWKS route). HS256 (`sign_hs256`/`verify_hs256`) retained for
local/dev/tests only.

---

## 2. Automated verification (local)

- **Backend suite:** `258 passed, 8 skipped`, coverage **96.19%** (gate 85%). *(was 243 — +15 new
  auth tests.)*
- **Lint/type:** `ruff` + `mypy` — **clean** (113 source files).
- **New tests** (`tests/test_auth_asymmetric.py`): EdDSA sign/verify roundtrip; tampered-payload
  rejection; wrong-key / unknown-`kid` rejection; expiry; key **rotation overlap** (a set verifies
  tokens from either key); `iss`/`aud` enforcement; **alg-confusion defense** (HS256 refused by an
  asymmetric-only verifier); JWKS shape (OKP/Ed25519); and the **composed app in production mode**
  (JWKS served, EdDSA authenticates, HS256 → 401).
- **Config fail-closed** (`tests/test_hardening_4_2.py`): production without a signing seed → refuses
  to boot; with a distinct 32-byte seed → boots.

## 3. Live verification (Railway staging, `TALEEM_ENV=production`)

Deployed `fecd0c17` — booted healthy (proves fail-closed did not trip; the signing seed is valid).
Tokens minted with the live signing key via the app's own `sign_eddsa`.

| Check | Expected | Result |
| --- | --- | --- |
| `GET /health` | 200 | ✅ 200 |
| `GET /.well-known/jwks.json` | Ed25519 public JWK, `kid=taleem-ed25519-2026-08` | ✅ `{"kty":"OKP","crv":"Ed25519","alg":"EdDSA",…}` |
| EdDSA **system** token → `/v1/skeleton/protected` | 200 | ✅ 200 |
| EdDSA **guardian** token → `/v1/guardian/dashboard` | 200 | ✅ 200 |
| EdDSA **student** token → `/v1/learning/students/{me}/today` | 200 | ✅ 200 |
| **Old HS256** token → protected route | 401 (rejected in prod) | ✅ 401 |
| No token → guardian route | 401 | ✅ 401 |
| Student token on guardian route | 403 | ✅ 403 |
| IDOR: student reads another student | 403 | ✅ 403 |
| Wrong `aud` token | 401 | ✅ 401 |

Signing key material is Railway-held (`TALEEM_JWT_SIGNING_SEED`, distinct from the offline seed);
never printed or committed.

---

## 4. Operational notes

- **Key rotation runbook:** generate a new seed → add its public key to `TALEEM_JWT_VERIFICATION_KEYS`
  (both keys now verify) → set `TALEEM_JWT_SIGNING_SEED`/`_KID` to the new key (signing switches) →
  after old tokens expire, remove the retired key. Overlap = zero downtime.
- **JWKS** is public by design (public keys only); it is intentionally reachable even though
  interactive API docs are disabled in production.

## 5. Scope boundary (feeds Blocker 2)

This milestone delivers the **token architecture** (issue/verify/rotate/publish). It does **not** yet
add the human **identity & consent flows** — login factors (picture-PIN, class-code, guardian-OTP,
phone-OTP, mentor MFA), the guardian-anchor/consent records, and enrolment — which are **Blocker 2**
and will issue tokens through this signing key. AAL/consent/safety ABAC enrichment in the PDP is also
Blocker 2. No child accounts or child PII exist on staging (governance gate unchanged).

**Verdict:** Blocker 1 is complete, tested, and live. Development authentication has been replaced by
a production-ready asymmetric-JWKS architecture with zero remaining defects in this scope.
