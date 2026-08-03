"""Compose the runtime auth context from settings (keys → verifier).

Production wires an **asymmetric, JWKS-verifying** ``TokenVerifier`` (EdDSA only); dev/local wires
the HS256 path (and EdDSA too, if a signing seed is configured, so EdDSA can be exercised locally).
The issuer/audience binding is enforced in production and left lenient in dev so the existing HS256
test tokens (which omit iss/aud) keep verifying. Pure composition — no framework imports.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..platform.config import Settings
from .jwt_verifier import TokenVerifier
from .keys import KeySet, SigningKey, VerifyKey, parse_verify_keys


@dataclass(frozen=True)
class AuthContext:
    verifier: TokenVerifier
    keyset: KeySet
    signing_key: SigningKey | None  # present iff this node can issue (sign) tokens


def build_auth_context(settings: Settings) -> AuthContext:
    verify_keys: list[VerifyKey] = []
    signing_key: SigningKey | None = None

    if settings.has_asymmetric_signing:
        signing_key = SigningKey(
            settings.jwt_signing_kid, bytes.fromhex(settings.jwt_signing_seed_hex.strip())
        )
        verify_keys.append(signing_key.verify_key())
    verify_keys.extend(parse_verify_keys(settings.jwt_verification_keys_csv))
    keyset = KeySet(tuple(verify_keys))

    if settings.is_production:
        # Asymmetric only. Bind tokens to this issuer + audience.
        verifier = TokenVerifier(
            keyset=keyset,
            hs256_secret=None,
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            allow_hs256=False,
        )
    else:
        # Dev/local: HS256 (back-compat) + EdDSA when a signing key is present. Lenient iss/aud so
        # existing HS256 test tokens (no iss/aud) keep verifying.
        verifier = TokenVerifier(
            keyset=keyset if verify_keys else None,
            hs256_secret=settings.jwt_dev_secret,
            issuer=None,
            audience=None,
            allow_hs256=True,
        )
    return AuthContext(verifier=verifier, keyset=keyset, signing_key=signing_key)
