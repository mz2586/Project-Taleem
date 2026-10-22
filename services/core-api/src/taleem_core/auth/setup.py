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
from .keys import KeySet, VerifyKey, parse_verify_keys
from .signer import RemoteSign, Signer, build_token_signer, public_key_from_jwk


@dataclass(frozen=True)
class AuthContext:
    verifier: TokenVerifier
    keyset: KeySet
    signer: Signer | None  # present iff this node can issue (sign) tokens


def build_auth_context(settings: Settings, *, remote_sign: RemoteSign | None = None) -> AuthContext:
    """``remote_sign`` is the hook for a future KMS provider adapter (FD-14); nothing passes it yet,
    so ``TALEEM_SIGNER_BACKEND=kms`` fails closed here."""
    verify_keys: list[VerifyKey] = []
    signer = build_token_signer(
        backend=settings.signer_backend,
        kid=settings.jwt_signing_kid,
        seed_hex=settings.jwt_signing_seed_hex,
        kms_key_ref=settings.kms_token_key_ref,
        kms_public_key_hex=settings.kms_token_public_key_hex,
        remote_sign=remote_sign,
    )
    if signer is not None:
        verify_keys.append(VerifyKey(signer.kid, public_key_from_jwk(signer.public_jwk())))
    # Extra public keys held during a rotation overlap. The active signer's kid wins a collision.
    active = {k.kid for k in verify_keys}
    verify_keys.extend(
        k for k in parse_verify_keys(settings.jwt_verification_keys_csv) if k.kid not in active
    )
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
    return AuthContext(verifier=verifier, keyset=keyset, signer=signer)
