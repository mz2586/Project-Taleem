// Client-side UUIDv7 (mirrors services/core-api platform/ids.py) — time-ordered, offline-safe.
// 48-bit ms timestamp prefix + 74 random bits, laid out per RFC 9562 v7.

export function uuid7(nowMs: number = Date.now(), rand: Uint8Array = randomBytes(10)): string {
  // 48-bit timestamp. Use division/modulo, not bitwise `&`/`>>>` — JS bit ops truncate to 32 bits
  // and would drop the top of a millisecond timestamp.
  const ts = nowMs % 2 ** 48;
  const b = new Uint8Array(16);
  b[0] = Math.floor(ts / 2 ** 40) % 256;
  b[1] = Math.floor(ts / 2 ** 32) % 256;
  b[2] = Math.floor(ts / 2 ** 24) % 256;
  b[3] = Math.floor(ts / 2 ** 16) % 256;
  b[4] = Math.floor(ts / 2 ** 8) % 256;
  b[5] = ts % 256;
  b[6] = 0x70 | ((rand[0] ?? 0) & 0x0f); // version 7
  b[7] = rand[1] ?? 0;
  b[8] = 0x80 | ((rand[2] ?? 0) & 0x3f); // variant 10xx
  b[9] = rand[3] ?? 0;
  b[10] = rand[4] ?? 0;
  b[11] = rand[5] ?? 0;
  b[12] = rand[6] ?? 0;
  b[13] = rand[7] ?? 0;
  b[14] = rand[8] ?? 0;
  b[15] = rand[9] ?? 0;
  const h = Array.from(b)
    .map((x) => x.toString(16).padStart(2, "0"))
    .join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20, 32)}`;
}

function randomBytes(n: number): Uint8Array {
  const out = new Uint8Array(n);
  if (typeof globalThis.crypto?.getRandomValues === "function") {
    globalThis.crypto.getRandomValues(out);
  }
  return out;
}
