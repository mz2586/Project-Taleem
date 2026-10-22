"""The signer port (FD-14): callers get signatures over bytes and never touch key material.

Everything that signs — access-token issuance (``identity/application/tokens.py``) and offline
lesson packages (``learning/adapters/package_signer.py``) — depends on ``Signer``, not on a seed.
Two implementations:

- ``EnvSeedSigner`` — the current behaviour: an Ed25519 seed supplied through the environment and
  held in process memory. Byte-identical signatures to the pre-port code (pinned by a golden test).
  Development, test, and the synthetic pilot only, per the FD-14 brief.
- ``KmsSigner`` — a **skeleton** for a key that never leaves a KMS/HSM. It takes an injected
  ``remote_sign`` callable and is wired to no provider: there is no SDK dependency and no network
  code here. Choosing a provider is the open FD-14 decision; until then ``build_token_signer``
  refuses the ``kms`` backend because nothing can supply that callable from configuration.

Only ``EdDSA`` is supported, because it is the only asymmetric algorithm the verifier accepts. If
the chosen KMS lacks Ed25519 (the brief allows a move to ES256), the verifier changes first.
"""

from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Protocol

from ..platform import ed25519

ALG_EDDSA = "EdDSA"

# (provider key reference, message) -> raw 64-byte Ed25519 signature. Supplied by a provider adapter
# that does not exist yet; never constructed from configuration alone.
RemoteSign = Callable[[str, bytes], bytes]


class SignerError(RuntimeError):
    """A signer produced no usable signature (remote failure, or a signature that won't verify)."""


class SignerConfigurationError(ValueError):
    """The configured signer backend cannot be constructed."""


class Signer(Protocol):
    """Signs bytes with a kid-addressed key whose private half the caller never sees."""

    @property
    def kid(self) -> str: ...

    @property
    def algorithm(self) -> str: ...

    def sign(self, message: bytes) -> bytes: ...

    def public_jwk(self) -> dict[str, str]: ...


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def ed25519_jwk(kid: str, public_key: bytes) -> dict[str, str]:
    """A public Ed25519 key as a JWK (RFC 8037 OKP)."""
    return {
        "kty": "OKP",
        "crv": "Ed25519",
        "kid": kid,
        "use": "sig",
        "alg": ALG_EDDSA,
        "x": _b64url(public_key),
    }


def public_key_from_jwk(jwk: dict[str, str]) -> bytes:
    """The raw 32-byte Ed25519 public key in a JWK, validated."""
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise SignerConfigurationError("only Ed25519 (OKP) public keys are supported")
    x = jwk.get("x", "")
    raw = base64.urlsafe_b64decode(x + "=" * (-len(x) % 4))
    if len(raw) != 32:
        raise SignerConfigurationError("Ed25519 public key must be 32 bytes")
    return raw


class EnvSeedSigner:
    """Ed25519 with an in-memory seed from the environment (dev/test/synthetic pilot)."""

    def __init__(self, kid: str, seed: bytes) -> None:
        if not kid:
            raise SignerConfigurationError("a signer needs a key id")
        if len(seed) != 32:
            raise SignerConfigurationError("Ed25519 seed must be 32 bytes")
        self._kid = kid
        self._seed = seed
        self._public = ed25519.public_key(seed)

    @classmethod
    def from_hex(cls, kid: str, seed_hex: str) -> EnvSeedSigner:
        try:
            seed = bytes.fromhex(seed_hex.strip())
        except ValueError:
            raise SignerConfigurationError("Ed25519 seed must be hex") from None
        return cls(kid, seed)

    @property
    def kid(self) -> str:
        return self._kid

    @property
    def algorithm(self) -> str:
        return ALG_EDDSA

    def sign(self, message: bytes) -> bytes:
        return ed25519.sign(message, self._seed, self._public)

    def public_jwk(self) -> dict[str, str]:
        return ed25519_jwk(self._kid, self._public)


class KmsSigner:
    """A non-exportable remote key, reached through an injected ``remote_sign`` callable.

    The signer is configured with the key's *public* half (published in the JWKS) and checks every
    returned signature against it before handing it out. That costs one local verification per
    signature and turns a misrouted key reference, a rotated-away key, or a provider fault into an
    explicit ``SignerError`` instead of a token every verifier would silently reject.
    """

    def __init__(
        self,
        *,
        kid: str,
        key_ref: str,
        public_key: bytes,
        remote_sign: RemoteSign,
        algorithm: str = ALG_EDDSA,
    ) -> None:
        if algorithm != ALG_EDDSA:
            raise SignerConfigurationError(
                f"unsupported signing algorithm {algorithm!r}; the verifier accepts EdDSA only"
            )
        if not kid or not key_ref:
            raise SignerConfigurationError("a KMS signer needs a key id and a key reference")
        if len(public_key) != 32:
            raise SignerConfigurationError("Ed25519 public key must be 32 bytes")
        self._kid = kid
        self._key_ref = key_ref
        self._public = public_key
        self._remote_sign = remote_sign

    @property
    def kid(self) -> str:
        return self._kid

    @property
    def algorithm(self) -> str:
        return ALG_EDDSA

    def sign(self, message: bytes) -> bytes:
        try:
            signature = self._remote_sign(self._key_ref, message)
        except Exception as exc:  # noqa: BLE001 — any provider failure is a signing failure
            raise SignerError(f"remote signing failed: {type(exc).__name__}") from exc
        if (
            not isinstance(signature, bytes)
            or len(signature) != 64
            or not ed25519.verify(signature, message, self._public)
        ):
            raise SignerError("remote signature does not verify against the configured public key")
        return signature

    def public_jwk(self) -> dict[str, str]:
        return ed25519_jwk(self._kid, self._public)


SIGNER_BACKENDS = ("env", "kms")


def build_token_signer(
    *,
    backend: str,
    kid: str,
    seed_hex: str = "",
    kms_key_ref: str = "",
    kms_public_key_hex: str = "",
    remote_sign: RemoteSign | None = None,
) -> Signer | None:
    """The token signer for this deployment, or ``None`` when no asymmetric key is configured.

    ``kms`` needs a key reference, its public key, *and* a ``remote_sign`` callable. The callable
    comes from a provider adapter that does not exist until FD-14 is decided, so today the ``kms``
    backend cannot be built from configuration and startup fails closed rather than falling back to
    a seed.
    """
    choice = backend.strip().lower() or "env"
    if choice == "env":
        return EnvSeedSigner.from_hex(kid, seed_hex) if seed_hex.strip() else None
    if choice == "kms":
        if not kms_key_ref.strip() or not kms_public_key_hex.strip():
            raise SignerConfigurationError(
                "TALEEM_SIGNER_BACKEND=kms needs TALEEM_KMS_TOKEN_KEY_REF and "
                "TALEEM_KMS_TOKEN_PUBLIC_KEY"
            )
        if remote_sign is None:
            raise SignerConfigurationError(
                "TALEEM_SIGNER_BACKEND=kms selected, but no KMS provider is wired "
                "(FD-14 is undecided); refusing to start rather than sign with a seed"
            )
        try:
            public_key = bytes.fromhex(kms_public_key_hex.strip())
        except ValueError:
            raise SignerConfigurationError("TALEEM_KMS_TOKEN_PUBLIC_KEY must be hex") from None
        return KmsSigner(
            kid=kid, key_ref=kms_key_ref.strip(), public_key=public_key, remote_sign=remote_sign
        )
    raise SignerConfigurationError(
        f"unknown TALEEM_SIGNER_BACKEND {backend!r} (expected one of {', '.join(SIGNER_BACKENDS)})"
    )
