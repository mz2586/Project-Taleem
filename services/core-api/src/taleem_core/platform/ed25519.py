"""Ed25519 (RFC 8032) — pure-stdlib reference implementation.

Vendored so the platform keeps its "no third-party installs" discipline (see pyproject NOTE) while
still producing STANDARD Ed25519 signatures — the same construction WebCrypto (`crypto.subtle` with
``{name: "Ed25519"}``) verifies on the client. Signs offline package manifests (Phase 6.2C-1); the
private seed never leaves the server — the client holds only the 32-byte public key.

This is the well-known RFC 8032 reference (SHA-512 over Curve25519 in Edwards form). It is not
constant-time and is not fast — fine for build-time signing + verification, not a hot path. For a
production KMS/HSM signing topology see FOUNDER_DECISIONS FD-14.
"""

from __future__ import annotations

import hashlib

_b = 256
_q = 2**255 - 19
_L = 2**252 + 27742317777372353535851937790883648493


def _sha512(m: bytes) -> bytes:
    return hashlib.sha512(m).digest()


def _inv(x: int) -> int:
    return pow(x, _q - 2, _q)


_d = (-121665 * _inv(121666)) % _q
_I = pow(2, (_q - 1) // 4, _q)


def _xrecover(y: int) -> int:
    xx = (y * y - 1) * _inv(_d * y * y + 1)
    x = pow(xx, (_q + 3) // 8, _q)
    if (x * x - xx) % _q != 0:
        x = (x * _I) % _q
    if x % 2 != 0:
        x = _q - x
    return x


_By = (4 * _inv(5)) % _q
_Bx = _xrecover(_By)
_B = (_Bx % _q, _By % _q)


def _edwards(p: tuple[int, int], q: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = p
    x2, y2 = q
    x3 = (x1 * y2 + x2 * y1) * _inv(1 + _d * x1 * x2 * y1 * y2)
    y3 = (y1 * y2 + x1 * x2) * _inv(1 - _d * x1 * x2 * y1 * y2)
    return (x3 % _q, y3 % _q)


def _scalarmult(p: tuple[int, int], e: int) -> tuple[int, int]:
    if e == 0:
        return (0, 1)
    q = _scalarmult(p, e // 2)
    q = _edwards(q, q)
    if e & 1:
        q = _edwards(q, p)
    return q


def _encodeint(y: int) -> bytes:
    return y.to_bytes(_b // 8, "little")


def _encodepoint(p: tuple[int, int]) -> bytes:
    x, y = p
    bits = [(y >> i) & 1 for i in range(_b - 1)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(_b // 8))


def _bit(h: bytes, i: int) -> int:
    return (h[i // 8] >> (i % 8)) & 1


def _clamped_scalar(h: bytes) -> int:
    total: int = 2 ** (_b - 2)
    for i in range(3, _b - 2):
        total += 2**i * _bit(h, i)
    return total


def public_key(seed: bytes) -> bytes:
    """Return the 32-byte public key for a 32-byte secret seed."""
    if len(seed) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    h = _sha512(seed)
    a = _clamped_scalar(h)
    return _encodepoint(_scalarmult(_B, a))


def sign(message: bytes, seed: bytes, pub: bytes | None = None) -> bytes:
    """Return the 64-byte Ed25519 signature of ``message`` under the 32-byte ``seed``."""
    if len(seed) != 32:
        raise ValueError("Ed25519 seed must be 32 bytes")
    pk = pub if pub is not None else public_key(seed)
    h = _sha512(seed)
    a = _clamped_scalar(h)
    r = int.from_bytes(_sha512(h[_b // 8 : _b // 4] + message), "little")
    big_r = _scalarmult(_B, r)
    enc_r = _encodepoint(big_r)
    s = (r + int.from_bytes(_sha512(enc_r + pk + message), "little") * a) % _L
    return enc_r + _encodeint(s)


def _isoncurve(p: tuple[int, int]) -> bool:
    x, y = p
    return (-x * x + y * y - 1 - _d * x * x * y * y) % _q == 0


def _decodepoint(s: bytes) -> tuple[int, int]:
    y = int.from_bytes(s, "little") & ((1 << (_b - 1)) - 1)
    x = _xrecover(y)
    if (x & 1) != _bit(s, _b - 1):
        x = _q - x
    p = (x, y)
    if not _isoncurve(p):
        raise ValueError("decoding point that is not on the curve")
    return p


def verify(signature: bytes, message: bytes, pub: bytes) -> bool:
    """Verify a 64-byte signature over ``message`` for the 32-byte public key ``pub``."""
    if len(signature) != 64 or len(pub) != 32:
        return False
    try:
        big_r = _decodepoint(signature[:32])
        a = _decodepoint(pub)
    except ValueError:
        return False
    s = int.from_bytes(signature[32:], "little")
    h = int.from_bytes(_sha512(signature[:32] + pub + message), "little")
    return _scalarmult(_B, s) == _edwards(big_r, _scalarmult(a, h))
