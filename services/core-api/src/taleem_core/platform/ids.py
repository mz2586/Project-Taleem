"""Identifier generation (pure-stdlib).

UUIDv7-style time-ordered ids: globally unique across contexts and offline clients, safe to
generate on an offline device, index-locality-friendly (docs/09-database-design.md §3).

Implemented without the (3.14-optional) uuid.uuid7 to keep it portable: 48-bit ms timestamp
prefix + 74 random bits, laid out per the RFC 9562 v7 field structure.
"""

from __future__ import annotations

import os
import time


def uuid7(now_ms: int | None = None) -> str:
    """Return a UUIDv7-shaped identifier as a canonical hex string.

    now_ms may be injected for determinism in tests. On real offline devices, prefer a
    server-synced clock where available; the random tail guarantees uniqueness regardless.
    """
    ts = now_ms if now_ms is not None else int(time.time() * 1000)
    ts &= (1 << 48) - 1
    rand = os.urandom(10)  # 80 bits; we use 74
    b = bytearray(16)
    b[0] = (ts >> 40) & 0xFF
    b[1] = (ts >> 32) & 0xFF
    b[2] = (ts >> 24) & 0xFF
    b[3] = (ts >> 16) & 0xFF
    b[4] = (ts >> 8) & 0xFF
    b[5] = ts & 0xFF
    b[6] = 0x70 | (rand[0] & 0x0F)  # version 7
    b[7] = rand[1]
    b[8] = 0x80 | (rand[2] & 0x3F)  # variant 10xx
    b[9:16] = rand[3:10]
    h = b.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
