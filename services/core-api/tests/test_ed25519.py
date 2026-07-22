"""Vendored Ed25519 (RFC 8032) — Phase 6.2C-1.

Proves the pure-stdlib signer produces STANDARD signatures (sign/verify roundtrip + tamper), and
locks a **cross-language interop vector**: this exact (seed → public key, message → signature) was
verified by Node/browser WebCrypto (`crypto.subtle` Ed25519) — the client verifier — so a change
that breaks interop fails here. The same vector is asserted in the frontend signature.test.ts.
"""

from __future__ import annotations

import pytest

from taleem_core.platform import ed25519

# Locked interop vector (WebCrypto-verified). seed = bytes(range(32)).
_SEED = bytes(range(32))
_PUB = "03a107bff3ce10be1d70dd18e74bc09967e4d6309ba50d5f1ddc8664125531b8"
_MSG = b"pkg/math-g4-intro-fractions\n1a2b3c4d5e6f\ndeadbeef"
_SIG = (
    "416f96e195fdd7f9bdb85229b8ad2c5b25d4dec068119fcba6d1006eaecb9671"
    "841d4cf2f17a3f691f92b539ccf4ea147b076380b73194d486a7cf76ad6fae06"
)


def test_public_key_matches_locked_vector() -> None:
    assert ed25519.public_key(_SEED).hex() == _PUB


def test_signature_matches_locked_vector() -> None:
    # Ed25519 is deterministic (RFC 8032) — the signature is fixed for a fixed key + message.
    assert ed25519.sign(_MSG, _SEED).hex() == _SIG


def test_locked_vector_verifies() -> None:
    assert ed25519.verify(bytes.fromhex(_SIG), _MSG, bytes.fromhex(_PUB)) is True


def test_sign_verify_roundtrip() -> None:
    seed = bytes([7]) * 32
    pub = ed25519.public_key(seed)
    msg = b"pkg/x\nabc123\n" + b"f" * 64
    sig = ed25519.sign(msg, seed)
    assert ed25519.verify(sig, msg, pub) is True


def test_tampered_message_fails() -> None:
    assert ed25519.verify(bytes.fromhex(_SIG), _MSG + b"x", bytes.fromhex(_PUB)) is False


def test_wrong_key_fails() -> None:
    other_pub = ed25519.public_key(bytes([9]) * 32)
    assert ed25519.verify(bytes.fromhex(_SIG), _MSG, other_pub) is False


def test_malformed_inputs_return_false() -> None:
    assert ed25519.verify(b"short", _MSG, bytes.fromhex(_PUB)) is False
    assert ed25519.verify(bytes.fromhex(_SIG), _MSG, b"short-key") is False


def test_seed_length_enforced() -> None:
    with pytest.raises(ValueError):
        ed25519.public_key(b"too-short")
    with pytest.raises(ValueError):
        ed25519.sign(b"m", b"too-short")
