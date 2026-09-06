"""Access-token issuance for the identity context.

This is the *only* place in the platform that mints a token. It reuses the key material built by
``auth.setup`` — EdDSA with the rotating kid-addressed key set where a signing seed is configured
(production always is, because ``platform.config`` refuses to boot without one), falling back to the
HS256 development path locally so the suite and a laptop can exercise the journey without key setup.

Token lifetimes are short on purpose. Consent can be withdrawn at any moment and the sign-in gate is
the thing that reads it, so a long-lived token is a window in which a withdrawn consent is still
being honoured. Ten minutes for a child bounds that window to something a guardian would accept;
sessions stay seamless because the client silently re-authenticates against the same device binding.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ....auth.jwt_verifier import sign_eddsa, sign_hs256
from ....auth.keys import SigningKey

# A learner token is short-lived: it is the blast radius of a withdrawn consent.
LEARNER_TOKEN_TTL_SECONDS = 10 * 60
# A guardian token is longer — an adult managing consent should not be logged out mid-form — but
# still well short of a session that could be lifted from a shared family device and reused later.
GUARDIAN_TOKEN_TTL_SECONDS = 60 * 60


@dataclass(frozen=True)
class IssuedToken:
    token: str
    expires_at: int
    role: str
    subject: str

    def to_dict(self) -> dict[str, object]:
        return {
            "access_token": self.token,
            "token_type": "Bearer",
            "expires_at": self.expires_at,
            "expires_in": max(0, self.expires_at - int(time.time())),
            "role": self.role,
            "subject": self.subject,
        }


@dataclass(frozen=True)
class TokenIssuer:
    """Mints signed access tokens bound to this deployment's issuer and audience."""

    issuer: str
    audience: str
    signing_key: SigningKey | None = None
    hs256_secret: str | None = None

    def __post_init__(self) -> None:
        if self.signing_key is None and not self.hs256_secret:
            raise ValueError(
                "TokenIssuer needs an Ed25519 signing key (production) or an HS256 secret (dev)"
            )

    def issue(
        self,
        *,
        subject: str,
        role: str,
        now: float,
        ttl_seconds: int,
        aal: int = 1,
        device_id: str | None = None,
    ) -> IssuedToken:
        issued_at = int(now)
        expires_at = issued_at + ttl_seconds
        claims: dict[str, object] = {
            # No name, no email, no date of birth: a token carries refs and a role, never child
            # PII (docs/03 §11 §7). Everything user-visible is fetched with the token, not in it.
            "sub": subject,
            "role": role,
            "aal": aal,
            "iss": self.issuer,
            "aud": self.audience,
            "iat": issued_at,
            "nbf": issued_at,
            "exp": expires_at,
        }
        if device_id:
            claims["device_id"] = device_id
        if self.signing_key is not None:
            token = sign_eddsa(claims, self.signing_key)
        elif self.hs256_secret:
            # Dev/local only. Unreachable in production: config fails closed without an asymmetric
            # seed, and the verifier refuses HS256 there even if a token were somehow minted.
            token = sign_hs256(claims, self.hs256_secret)
        else:  # pragma: no cover — __post_init__ rejects an issuer with no signing material
            raise RuntimeError("token issuer has no signing material")
        return IssuedToken(token=token, expires_at=expires_at, role=role, subject=subject)
