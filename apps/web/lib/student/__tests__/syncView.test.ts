import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import { summarizeSyncStatus, type SyncStatusSummary } from "../../offline";
import { heldReasonKey, syncView, type SyncView } from "../syncView";

function summary(over: Partial<SyncStatusSummary> = {}): SyncStatusSummary {
  return { ...summarizeSyncStatus({ queue: [], acks: [] }), ...over };
}

function text(view: SyncView, locale: "en" | "ur" = "en"): string {
  return translate(locale, view.headline.key, view.headline.params);
}

const LOST = /lost|deleted|failed|error/i;

describe("syncView headline", () => {
  it("is plain 'Online' with nothing to report", () => {
    const view = syncView({ online: true, summary: summary(), lastSyncAt: null });
    expect(text(view)).toBe("Online");
    expect(view.hasDetail).toBe(false);
  });

  it("says work is saved on this phone while offline", () => {
    const view = syncView({ online: false, summary: summary({ savedOnDevice: 3, waiting: 3 }), lastSyncAt: null });
    expect(text(view)).toBe("Offline · saved on this phone: 3");
    expect(view.waitingReason).toBe("student.sync.waiting.offline");
    expect(view.tone).toBe("calm");
  });

  it("says 'Offline' alone when nothing is waiting", () => {
    expect(text(syncView({ online: false, summary: summary(), lastSyncAt: null }))).toBe("Offline");
  });

  it("says sending while online with work waiting", () => {
    const view = syncView({ online: true, summary: summary({ savedOnDevice: 2, waiting: 2 }), lastSyncAt: null });
    expect(text(view)).toBe("Sending: 2");
    expect(view.tone).toBe("busy");
  });

  it("says it will send later when the server or sign-in is in the way", () => {
    const s = summary({ savedOnDevice: 2, waiting: 2, blocked: "server" });
    const view = syncView({ online: true, summary: s, lastSyncAt: null });
    expect(text(view)).toBe("Will send later · saved on this phone: 2");
    expect(view.waitingReason).toBe("student.sync.waiting.server");
    expect(syncView({ online: true, summary: { ...s, blocked: "auth" }, lastSyncAt: null }).waitingReason).toBe(
      "student.sync.waiting.signIn",
    );
  });

  it("says all work is sent once the server has acknowledged it", () => {
    const view = syncView({ online: true, summary: summary({ synchronized: 1, serverConfirmed: 4 }), lastSyncAt: 1_761_134_400_000 });
    expect(text(view)).toBe("All work sent");
    expect(view.lastSyncAt).toBe(1_761_134_400);
    expect(view.hasDetail).toBe(true);
  });
});

describe("held work (permission withdrawn) is waiting, never lost", () => {
  const held = summary({ savedOnDevice: 5, held: 5, blocked: "permission", blockedCode: "CONSENT_REQUIRED" });

  it("puts held work first, even offline", () => {
    for (const online of [true, false]) {
      const view = syncView({ online, summary: held, lastSyncAt: null });
      expect(text(view)).toBe("Waiting for a grown-up · saved on this phone: 5");
      expect(view.tone).toBe("attention");
    }
  });

  it("explains consent in grown-up terms and says the work is kept", () => {
    const view = syncView({ online: true, summary: held, lastSyncAt: null });
    const message = translate("en", view.held!.key, view.held!.params);
    expect(message).toMatch(/grown-up needs to allow learning again/);
    expect(message).toMatch(/kept on this phone/);
    expect(message).not.toMatch(LOST);
  });

  it("maps each refusal code, with a safe fallback", () => {
    expect(heldReasonKey("CONSENT_REQUIRED")).toBe("student.sync.held.consent");
    expect(heldReasonKey("LEARNER_INACTIVE")).toBe("student.sync.held.paused");
    expect(heldReasonKey("FORBIDDEN")).toBe("student.sync.held.other");
    expect(heldReasonKey(null)).toBe("student.sync.held.other");
  });

  it("never says held work is lost, in either language", () => {
    for (const key of ["student.sync.held.consent", "student.sync.held.paused", "student.sync.held.other"] as const) {
      expect(translate("en", key, { count: 1 })).not.toMatch(LOST);
      expect(translate("ur", key, { count: 1 })).toContain("محفوظ");
    }
  });
});

describe("rejected work", () => {
  it("is kept on the phone and points to a grown-up or teacher", () => {
    const view = syncView({ online: true, summary: summary({ savedOnDevice: 1, rejected: 1 }), lastSyncAt: null });
    expect(text(view)).toBe("Needs help · kept on this phone: 1");
    const message = translate("en", view.rejected!.key, view.rejected!.params);
    expect(message).toMatch(/still kept on this phone/);
    expect(message).toMatch(/grown-up or your teacher/);
  });
});

describe("detail rows", () => {
  it("always lists the three states in order, with counts", () => {
    const view = syncView({
      online: true,
      summary: summary({ savedOnDevice: 2, waiting: 2, synchronized: 3, serverConfirmed: 7 }),
      lastSyncAt: null,
    });
    expect(view.rows.map((r) => [r.kind, r.count])).toEqual([
      ["device", 2],
      ["sent", 3],
      ["confirmed", 7],
    ]);
    expect(view.rows.map((r) => translate("en", r.label.key, r.label.params))).toEqual([
      "Saved on this phone: 2",
      "Sent to Taleem: 3",
      "Saved safely by Taleem: 7",
    ]);
  });

  it("distinguishes a local save from a server-confirmed one in Urdu too", () => {
    const view = syncView({ online: true, summary: summary({ savedOnDevice: 1, serverConfirmed: 1 }), lastSyncAt: null });
    const [device, , confirmed] = view.rows.map((r) => translate("ur", r.label.key, r.label.params));
    expect(device).toBe("اس فون پر محفوظ: 1");
    expect(confirmed).toBe("تعلیم کے پاس محفوظ: 1");
  });
});
