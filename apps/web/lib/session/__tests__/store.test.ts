// Session store behaviour.
//
// The tests that matter here are not "it stores a token". They are the four ways this store could
// silently sign a child out or hand the server a replayed token:
//
//   1. Two components refreshing at once, burning the same rotating token → family revoked.
//   2. Persisting the successor *after* returning it → a crash strands the session.
//   3. Treating a transient offline blip as a revocation → a child loses their session in a tunnel.
//   4. Using a token that expires while the request is in flight.

import { beforeEach, describe, expect, it, vi } from "vitest";

import { publicIdentityApi } from "../identityApi";
import { currentAccessToken, sessionStore, withSession } from "../store";
import type { SessionEnvelope } from "../types";
import { ApiError } from "../../student/types";

vi.mock("../identityApi", () => ({
  publicIdentityApi: {
    refresh: vi.fn(),
    signOut: vi.fn(),
  },
}));

vi.mock("../device", () => ({ deviceId: () => "device-test" }));

const refreshMock = vi.mocked(publicIdentityApi.refresh);
const signOutMock = vi.mocked(publicIdentityApi.signOut);

function envelope(overrides: Partial<SessionEnvelope["session"]> = {}, refresh = "rft_1.s1"): SessionEnvelope {
  return {
    session: {
      access_token: "access-1",
      token_type: "Bearer",
      expires_at: Math.floor(Date.now() / 1000) + 600,
      expires_in: 600,
      role: "student",
      subject: "stu_1",
      ...overrides,
    },
    refresh_token: refresh,
  };
}

beforeEach(() => {
  window.localStorage.clear();
  sessionStore.clear();
  refreshMock.mockReset();
  signOutMock.mockReset();
});

describe("persistence", () => {
  it("adopts a sign-in envelope and exposes its access token", () => {
    sessionStore.adopt(envelope());
    expect(currentAccessToken()).toBe("access-1");
    expect(sessionStore.peek()?.subject).toBe("stu_1");
  });

  it("survives a reload by reading back from storage", () => {
    sessionStore.adopt(envelope());
    // Simulate a fresh page: the module-level cache is dropped by clearing and re-peeking is not
    // enough, so assert on what was actually written.
    const raw = window.localStorage.getItem("taleem.session.v1");
    expect(raw).toBeTruthy();
    expect(JSON.parse(raw as string).refreshToken).toBe("rft_1.s1");
  });

  it("treats unparseable storage as no session rather than crashing", () => {
    window.localStorage.setItem("taleem.session.v1", "{not json");
    sessionStore.clear();
    window.localStorage.setItem("taleem.session.v1", "{not json");
    expect(() => sessionStore.peek()).not.toThrow();
  });

  it("clear removes the stored session", () => {
    sessionStore.adopt(envelope());
    sessionStore.clear();
    expect(sessionStore.peek()).toBeNull();
    expect(window.localStorage.getItem("taleem.session.v1")).toBeNull();
  });

  it("notifies subscribers on adopt and clear", () => {
    const seen: (string | null)[] = [];
    const unsubscribe = sessionStore.subscribe((s) => seen.push(s?.subject ?? null));
    sessionStore.adopt(envelope());
    sessionStore.clear();
    unsubscribe();
    sessionStore.adopt(envelope());
    expect(seen).toEqual(["stu_1", null]);
  });
});

describe("expiry", () => {
  it("returns the session untouched while the token is comfortably alive", async () => {
    sessionStore.adopt(envelope());
    const result = await sessionStore.valid();
    expect(result?.accessToken).toBe("access-1");
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("refreshes a token that expires inside the safety margin", async () => {
    // 10 seconds left is less than the 30-second margin: a request over a slow link would land
    // after it died, so it must be refreshed before use.
    sessionStore.adopt(envelope({ expires_at: Math.floor(Date.now() / 1000) + 10 }));
    refreshMock.mockResolvedValue(envelope({ access_token: "access-2" }, "rft_2.s2"));

    const result = await sessionStore.valid();

    expect(refreshMock).toHaveBeenCalledOnce();
    expect(result?.accessToken).toBe("access-2");
  });

  it("refreshes an already-expired token", async () => {
    sessionStore.adopt(envelope({ expires_at: Math.floor(Date.now() / 1000) - 60 }));
    refreshMock.mockResolvedValue(envelope({ access_token: "access-2" }, "rft_2.s2"));
    await sessionStore.valid();
    expect(refreshMock).toHaveBeenCalledOnce();
  });

  it("returns null with no session, rather than attempting a refresh", async () => {
    expect(await sessionStore.valid()).toBeNull();
    expect(refreshMock).not.toHaveBeenCalled();
  });
});

describe("rotation", () => {
  it("stores the successor refresh token", async () => {
    sessionStore.adopt(envelope());
    refreshMock.mockResolvedValue(envelope({ access_token: "access-2" }, "rft_2.s2"));

    await sessionStore.refresh();

    expect(sessionStore.peek()?.refreshToken).toBe("rft_2.s2");
    // Persisted, not merely held in memory — a reload after rotation must not resurrect the dead
    // predecessor and trip the server's reuse detection.
    const raw = JSON.parse(window.localStorage.getItem("taleem.session.v1") as string);
    expect(raw.refreshToken).toBe("rft_2.s2");
  });

  it("sends the device id so the server can enforce its binding", async () => {
    sessionStore.adopt(envelope());
    refreshMock.mockResolvedValue(envelope());
    await sessionStore.refresh();
    expect(refreshMock).toHaveBeenCalledWith({
      refreshToken: "rft_1.s1",
      deviceId: "device-test",
    });
  });

  it("collapses concurrent refreshes into a single request", async () => {
    // The reason this store exists. Rotation means a replayed token is treated as theft and revokes
    // the whole family, so two components hitting 401 together must not fire two refreshes.
    sessionStore.adopt(envelope({ expires_at: Math.floor(Date.now() / 1000) - 1 }));
    let resolve!: (value: SessionEnvelope) => void;
    refreshMock.mockReturnValue(
      new Promise<SessionEnvelope>((r) => {
        resolve = r;
      }),
    );

    const calls = [
      sessionStore.valid(),
      sessionStore.valid(),
      sessionStore.refresh(),
      sessionStore.refresh(),
    ];
    resolve(envelope({ access_token: "access-2" }, "rft_2.s2"));
    const results = await Promise.all(calls);

    expect(refreshMock).toHaveBeenCalledOnce();
    expect(results.every((r) => r?.accessToken === "access-2")).toBe(true);
  });

  it("allows a later refresh once the in-flight one has settled", async () => {
    sessionStore.adopt(envelope());
    refreshMock.mockResolvedValue(envelope({ access_token: "access-2" }, "rft_2.s2"));
    await sessionStore.refresh();
    refreshMock.mockResolvedValue(envelope({ access_token: "access-3" }, "rft_3.s3"));
    const second = await sessionStore.refresh();
    expect(refreshMock).toHaveBeenCalledTimes(2);
    expect(second?.accessToken).toBe("access-3");
  });
});

describe("failure handling", () => {
  it("keeps the session when the refresh fails because the device is offline", async () => {
    sessionStore.adopt(envelope());
    refreshMock.mockRejectedValue(new ApiError(0, { code: "OFFLINE" }));

    const result = await sessionStore.refresh();

    // A tunnel is not a revocation. Discarding a valid refresh token here would sign a child out
    // for the rest of the journey.
    expect(result?.refreshToken).toBe("rft_1.s1");
    expect(sessionStore.peek()).not.toBeNull();
  });

  it("clears the session when the server rejects the refresh token", async () => {
    sessionStore.adopt(envelope());
    refreshMock.mockRejectedValue(new ApiError(401, { code: "UNAUTHORIZED" }));
    expect(await sessionStore.refresh()).toBeNull();
    expect(sessionStore.peek()).toBeNull();
  });

  it("clears the session when consent has been withdrawn", async () => {
    sessionStore.adopt(envelope());
    refreshMock.mockRejectedValue(new ApiError(403, { code: "CONSENT_REQUIRED" }));
    expect(await sessionStore.refresh()).toBeNull();
    expect(sessionStore.peek()).toBeNull();
  });
});

describe("signOut", () => {
  it("clears locally and revokes on the server", async () => {
    sessionStore.adopt(envelope());
    signOutMock.mockResolvedValue({ signed_out: true });
    await sessionStore.signOut();
    expect(signOutMock).toHaveBeenCalledWith("rft_1.s1");
    expect(sessionStore.peek()).toBeNull();
  });

  it("still clears locally when the server call fails", async () => {
    sessionStore.adopt(envelope());
    signOutMock.mockRejectedValue(new ApiError(0, { code: "OFFLINE" }));
    await sessionStore.signOut();
    expect(sessionStore.peek()).toBeNull();
  });

  it("is a no-op when already signed out", async () => {
    await sessionStore.signOut();
    expect(signOutMock).not.toHaveBeenCalled();
  });
});

describe("withSession", () => {
  it("runs the call with a fresh token", async () => {
    sessionStore.adopt(envelope());
    const call = vi.fn().mockResolvedValue("ok");
    expect(await withSession(call)).toBe("ok");
    expect(call).toHaveBeenCalledOnce();
  });

  it("refreshes and retries once on a 401", async () => {
    sessionStore.adopt(envelope());
    refreshMock.mockResolvedValue(envelope({ access_token: "access-2" }, "rft_2.s2"));
    const call = vi
      .fn()
      .mockRejectedValueOnce(new ApiError(401, { code: "UNAUTHORIZED" }))
      .mockResolvedValueOnce("ok");

    expect(await withSession(call)).toBe("ok");
    expect(refreshMock).toHaveBeenCalledOnce();
    expect(call).toHaveBeenCalledTimes(2);
  });

  it("does not retry when the refresh itself fails", async () => {
    sessionStore.adopt(envelope());
    refreshMock.mockRejectedValue(new ApiError(401, { code: "UNAUTHORIZED" }));
    const call = vi.fn().mockRejectedValue(new ApiError(401, { code: "UNAUTHORIZED" }));
    await expect(withSession(call)).rejects.toBeInstanceOf(ApiError);
    expect(call).toHaveBeenCalledOnce();
  });

  it("does not retry a 403 — that is a permission answer, not a stale token", async () => {
    sessionStore.adopt(envelope());
    const call = vi.fn().mockRejectedValue(new ApiError(403, { code: "FORBIDDEN" }));
    await expect(withSession(call)).rejects.toBeInstanceOf(ApiError);
    expect(call).toHaveBeenCalledOnce();
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("propagates an offline error without retrying", async () => {
    sessionStore.adopt(envelope());
    const call = vi.fn().mockRejectedValue(new ApiError(0, { code: "OFFLINE" }));
    await expect(withSession(call)).rejects.toBeInstanceOf(ApiError);
    expect(call).toHaveBeenCalledOnce();
  });
});
