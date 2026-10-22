"""Ed25519 package signer (adapter) — Phase 6.2C-1.

Implements the ``PackageSigner`` port the offline-package domain depends on, over the platform
``auth.signer.Signer`` port (FD-14): this adapter asks for a signature over bytes and never holds
key material itself, so a KMS-held key can replace the environment seed without touching it. The
client verifies with the 32-byte public key exposed via ``public_key_hex``. Signing is over a
canonicalization-free payload (``signing_payload``) so Python↔WebCrypto interop never depends on
JSON key ordering.
"""

from __future__ import annotations

from ....auth.signer import EnvSeedSigner, Signer, SignerConfigurationError, public_key_from_jwk


class SignerPackageSigner:
    """Implements PackageSigner over any ``Signer``."""

    def __init__(self, signer: Signer) -> None:
        self._signer = signer
        self._public = public_key_from_jwk(signer.public_jwk())

    @property
    def key_id(self) -> str:
        return self._signer.kid

    @property
    def public_key_hex(self) -> str:
        return self._public.hex()

    def sign(self, payload: bytes) -> str:
        """Return the hex Ed25519 signature over ``payload``."""
        return self._signer.sign(payload).hex()


class Ed25519PackageSigner(SignerPackageSigner):
    """The environment-seed signer for packages (dev/test/synthetic pilot; FD-14 option (d))."""

    def __init__(self, seed_hex: str, key_id: str) -> None:
        try:
            signer = EnvSeedSigner.from_hex(key_id, seed_hex)
        except SignerConfigurationError as exc:
            raise ValueError(f"invalid offline signing key: {exc}") from exc
        super().__init__(signer)
