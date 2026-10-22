// Session wiring of the browser offline client: which learner may sync, and held work being
// released (once) when a learner session is adopted.
import "fake-indexeddb/auto";

import { describe, expect, it } from "vitest";

import { sessionStore } from "../../session/store";
import type { SessionEnvelope } from "../../session/types";
import { getOfflineClient, learnerOf } from "../offlineClient";

function envelope(subject: string, role: "student" | "guardian"): SessionEnvelope {
  return {
    session: {
      access_token: `tok-${subject}`,
      token_type: "Bearer",
      expires_at: Math.floor(Date.now() / 1000) + 600,
      expires_in: 600,
      role,
      subject,
    },
    refresh_token: `rt-${subject}`,
  };
}

describe("offline client session wiring", () => {
  it("only a student session can carry a learner's sync", () => {
    expect(learnerOf(null)).toBeNull();
    expect(learnerOf(sessionStore.adopt(envelope("G1", "guardian")))).toBeNull();
    expect(learnerOf(sessionStore.adopt(envelope("S1", "student")))).toBe("S1");
    sessionStore.clear();
  });

  it("releases a learner's permission-held deltas when that learner signs in", async () => {
    sessionStore.clear();
    const client = getOfflineClient();
    const q = client.sync.queue;
    await q.enqueue({
      clientEventId: "held-1",
      type: "attempt.submitted",
      entityKey: "student:S9|item:i1",
      payload: { student_ref: "S9", evidence_id: "ev-held-1" },
      clientSeq: 1,
    });
    await q.hold(["held-1"], "CONSENT_REQUIRED");
    expect((await q.held()).length).toBe(1);

    sessionStore.adopt(envelope("S9", "student"));
    // release is fire-and-forget from the listener; let it settle
    for (let i = 0; i < 20 && (await q.held()).length > 0; i++) await new Promise((r) => setTimeout(r, 5));
    expect((await q.held()).length).toBe(0);
    expect((await q.get("held-1"))?.syncState).toBe("pending");
    sessionStore.clear();
  });
});
