"""Ed25519 package signer (adapter) — Phase 6.2C-1.

Implements the ``PackageSigner`` port the offline-package domain depends on, using the vendored
pure-stdlib Ed25519 (`platform.ed25519`). The private seed is held here (server-side) and never
serialized into a manifest; the client verifies with the 32-byte public key exposed via
``public_key_hex``. Signing is over a canonicalization-free payload (``signing_payload``) so
Python↔WebCrypto interop never depends on JSON key ordering.
"""

from __future__ import annotations

from ....platform import ed25519


class Ed25519PackageSigner:
    """Holds the signing seed + key id; signs manifest payloads. Implements PackageSigner."""

    def __init__(self, seed_hex: str, key_id: str) -> None:
        seed = bytes.fromhex(seed_hex)
        if len(seed) != 32:
            raise ValueError("offline signing seed must be 32 bytes (64 hex chars)")
        self._seed = seed
        self._public = ed25519.public_key(seed)
        self._key_id = key_id

    @property
    def key_id(self) -> str:
        return self._key_id

    @property
    def public_key_hex(self) -> str:
        return self._public.hex()

    def sign(self, payload: bytes) -> str:
        """Return the hex Ed25519 signature over ``payload``."""
        return ed25519.sign(payload, self._seed, self._public).hex()
