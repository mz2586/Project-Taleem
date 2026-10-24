// A child's kept homework text must not outlive their session on a shared family phone. Checked:
// learner sign-out, a terminal refresh failure (401), the learner gate's 403 (consent withdrawn /
// paused), and a guardian withdrawing consent — each removes that learner's drafts, and only theirs.
import { beforeEach, describe, expect, it, vi } from "vitest";

import { familyApi } from "../../guardian/api";
import { publicIdentityApi } from "../../session/identityApi";
import { sessionStore, withSession } from "../../session/store";
import type { SessionEnvelope } from "../../session/types";
import { ApiError } from "../../student/types";
import { draftKey, localDrafts } from "../drafts";

const withdrawMock = vi.fn();

vi.mock("../../session/identityApi", () => ({
  publicIdentityApi: { refresh: vi.fn(), signOut: vi.fn() },
  createGuardianIdentityApi: () => ({ withdrawConsent: (body: unknown) => withdrawMock(body) }),
}));
vi.mock("../../session/device", () => ({ deviceId: () => "device-test" }));

function envelope(role: "student" | "guardian", subject: string): SessionEnvelope {
  return {
    session: {
      access_token: "access-1",
      token_type: "Bearer",
      expires_at: Math.floor(Date.now() / 1000) + 600,
      expires_in: 600,
      role,
      subject,
    },
    refresh_token: "rft_1.s1",
  } as SessionEnvelope;
}

const mine = draftKey("stu_1", "a1", "i1");
const sibling = draftKey("stu_2", "a1", "i1");

beforeEach(() => {
  sessionStore.clear();
  window.localStorage.clear();
  vi.mocked(publicIdentityApi.refresh).mockReset();
  vi.mocked(publicIdentityApi.signOut).mockReset();
  withdrawMock.mockReset();
  localDrafts.write(mine, "my homework");
  localDrafts.write(sibling, "my sister's homework");
});

describe("learner session end clears that learner's drafts", () => {
  it("on sign-out", async () => {
    sessionStore.adopt(envelope("student", "stu_1"));
    await sessionStore.signOut();
    expect(localDrafts.read(mine)).toBeNull();
    expect(localDrafts.read(sibling)).toBe("my sister's homework");
  });

  it("on a terminal refresh failure after a 401", async () => {
    sessionStore.adopt(envelope("student", "stu_1"));
    vi.mocked(publicIdentityApi.refresh).mockRejectedValue(new ApiError(401, { code: "REVOKED" }));
    await expect(withSession(() => Promise.reject(new ApiError(401, {})))).rejects.toBeInstanceOf(ApiError);
    expect(sessionStore.peek()).toBeNull();
    expect(localDrafts.read(mine)).toBeNull();
    expect(localDrafts.read(sibling)).not.toBeNull();
  });

  it("but not when the refresh only failed for being offline (the session is kept)", async () => {
    sessionStore.adopt(envelope("student", "stu_1"));
    vi.mocked(publicIdentityApi.refresh).mockRejectedValue(new ApiError(0, { code: "OFFLINE" }));
    await expect(withSession(() => Promise.reject(new ApiError(401, {})))).rejects.toBeInstanceOf(ApiError);
    expect(localDrafts.read(mine)).toBe("my homework");
  });

  it("a guardian signing out does not touch any child's drafts", async () => {
    sessionStore.adopt(envelope("guardian", "gdn_1"));
    await sessionStore.signOut();
    expect(localDrafts.read(mine)).toBe("my homework");
  });
});

describe("the learner gate's 403 clears the drafts", () => {
  for (const code of ["CONSENT_REQUIRED", "LEARNER_INACTIVE"]) {
    it(`on ${code}`, async () => {
      sessionStore.adopt(envelope("student", "stu_1"));
      await expect(withSession(() => Promise.reject(new ApiError(403, { code })))).rejects.toBeInstanceOf(ApiError);
      expect(localDrafts.read(mine)).toBeNull();
      expect(localDrafts.read(sibling)).not.toBeNull();
    });
  }

  it("not on an unrelated 403", async () => {
    sessionStore.adopt(envelope("student", "stu_1"));
    await expect(withSession(() => Promise.reject(new ApiError(403, { code: "FORBIDDEN" })))).rejects.toBeInstanceOf(ApiError);
    expect(localDrafts.read(mine)).toBe("my homework");
  });
});

describe("a guardian withdrawing consent clears that child's drafts", () => {
  it("after the server accepts the withdrawal, for that child only", async () => {
    sessionStore.adopt(envelope("guardian", "gdn_1"));
    withdrawMock.mockResolvedValue({ granted_scopes: [] });
    await familyApi.withdrawConsent({ studentRef: "stu_1" });
    expect(withdrawMock).toHaveBeenCalledWith({ studentRef: "stu_1" });
    expect(localDrafts.read(mine)).toBeNull();
    expect(localDrafts.read(sibling)).toBe("my sister's homework");
  });

  it("keeps them when the withdrawal did not happen", async () => {
    sessionStore.adopt(envelope("guardian", "gdn_1"));
    withdrawMock.mockRejectedValue(new ApiError(0, { code: "OFFLINE" }));
    await expect(familyApi.withdrawConsent({ studentRef: "stu_1" })).rejects.toBeInstanceOf(ApiError);
    expect(localDrafts.read(mine)).toBe("my homework");
  });
});
