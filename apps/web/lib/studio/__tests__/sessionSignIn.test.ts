import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { studioSession } from "../session";
import { refreshStaffSession, signInStaff, signOutStaff } from "../sessionSignIn";

// The node suite has no sessionStorage; give this file one so the tab-scoped storage branch runs.
const stored = new Map<string, string>();
const memorySession = {
  getItem: (k: string) => stored.get(k) ?? null,
  setItem: (k: string, v: string) => void stored.set(k, String(v)),
  removeItem: (k: string) => void stored.delete(k),
  clear: () => stored.clear(),
  key: (i: number) => Array.from(stored.keys())[i] ?? null,
  get length() {
    return stored.size;
  },
};
(globalThis as unknown as { sessionStorage: Storage }).sessionStorage = memorySession as Storage;

function jwt(claims: Record<string, unknown>): string {
  const enc = (o: unknown) =>
    Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${enc({ alg: "EdDSA", typ: "JWT" })}.${enc(claims)}.sig`;
}

const later = Math.floor(Date.now() / 1000) + 3600;

function envelope(role = "subject_expert", refresh = "rft_1.secret") {
  return {
    staff: {
      staff_ref: "stf_abc",
      email: "rev@example.com",
      display_name: "Reviewer",
      role,
      status: "active",
      created_at: 0,
    },
    session: {
      access_token: jwt({ sub: "stf_abc", role, exp: later }),
      role,
      subject: "stf_abc",
      expires_at: later,
    },
    refresh_token: refresh,
  };
}

function respond(status: number, body: unknown) {
  return Promise.resolve(
    new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }),
  );
}

describe("staff sign-in session", () => {
  beforeEach(() => {
    studioSession.clear();
    stored.clear();
  });
  afterEach(() => vi.unstubAllGlobals());

  it("adopts the server's role and subject and keeps the refresh token for this tab", async () => {
    const fetchMock = vi.fn(() => respond(200, envelope()));
    vi.stubGlobal("fetch", fetchMock);
    const result = await signInStaff("rev@example.com", "a-reviewer-passphrase");
    expect(result.ok).toBe(true);
    expect(studioSession.actor()).toMatchObject({ subject: "stf_abc", role: "subject_expert" });
    expect(studioSession.refreshToken()).toBe("rft_1.secret");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toMatch(/\/v1\/identity\/staff:signin$/);
    expect(JSON.parse(String(init.body))).toEqual({
      email: "rev@example.com",
      passphrase: "a-reviewer-passphrase",
    });
  });

  it("surfaces the uniform 401 and stores nothing", async () => {
    vi.stubGlobal("fetch", vi.fn(() => respond(401, { code: "UNAUTHORIZED" })));
    await expect(signInStaff("rev@example.com", "wrong")).rejects.toMatchObject({ status: 401 });
    expect(studioSession.actor()).toBeNull();
    expect(studioSession.refreshToken()).toBeNull();
  });

  it("refuses a token for a non-Studio role even if a server returned one", async () => {
    vi.stubGlobal("fetch", vi.fn(() => respond(200, envelope("guardian"))));
    const result = await signInStaff("rev@example.com", "a-reviewer-passphrase");
    expect(result.ok).toBe(false);
    expect(studioSession.actor()).toBeNull();
    expect(studioSession.refreshToken()).toBeNull();
  });

  it("rotates the refresh token, and signs the tab out when refresh is refused", async () => {
    vi.stubGlobal("fetch", vi.fn(() => respond(200, envelope())));
    await signInStaff("rev@example.com", "a-reviewer-passphrase");
    vi.stubGlobal("fetch", vi.fn(() => respond(200, envelope("subject_expert", "rft_2.secret"))));
    expect(await refreshStaffSession()).toBe(true);
    expect(studioSession.refreshToken()).toBe("rft_2.secret");

    vi.stubGlobal("fetch", vi.fn(() => respond(401, { code: "UNAUTHORIZED" })));
    expect(await refreshStaffSession()).toBe(false);
    expect(studioSession.actor()).toBeNull();
    expect(studioSession.refreshToken()).toBeNull();
  });

  it("sign-out ends the server session and forgets the tab's tokens, even offline", async () => {
    vi.stubGlobal("fetch", vi.fn(() => respond(200, envelope())));
    await signInStaff("rev@example.com", "a-reviewer-passphrase");
    const signOut = vi.fn(() => Promise.reject(new TypeError("offline")));
    vi.stubGlobal("fetch", signOut);
    await signOutStaff();
    expect(signOut).toHaveBeenCalledTimes(1);
    expect(studioSession.actor()).toBeNull();
    expect(studioSession.refreshToken()).toBeNull();
  });
});
