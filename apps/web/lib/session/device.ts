// A per-browser device identifier for binding refresh tokens.
//
// Deliberately *not* a fingerprint. It is a random value this browser generates for itself, stored
// in localStorage, never derived from anything about the device or the person using it. Clearing
// site data rotates it, which is the property that makes it acceptable on a child's device: it
// identifies an installation, not a human, and the human can always discard it.
//
// Its only job is to make a stolen refresh token useless somewhere else. A device that cannot store
// one (a private window, storage blocked) simply gets no binding and no error — the refresh token
// still rotates, and a lost binding is a smaller failure than a child who cannot sign in.

const DEVICE_KEY = "taleem.device.v1";

function randomId(): string {
  const bytes = new Uint8Array(16);
  if (typeof crypto !== "undefined" && "getRandomValues" in crypto) {
    crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

export function deviceId(): string {
  if (typeof window === "undefined") return "";
  try {
    const existing = window.localStorage.getItem(DEVICE_KEY);
    if (existing) return existing;
    const fresh = randomId();
    window.localStorage.setItem(DEVICE_KEY, fresh);
    return fresh;
  } catch {
    // Storage unavailable. No binding, no error.
    return "";
  }
}
