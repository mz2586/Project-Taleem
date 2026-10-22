import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import type { AuditEvent } from "../../session/types";
import { AUDIT_MAX, AUDIT_PAGE, auditEntry, auditView, nextAuditLimit } from "../audit";

function event(action: string, over: Partial<AuditEvent> = {}): AuditEvent {
  return {
    event_id: `evt_${action}`,
    at: 1_761_134_400,
    action,
    actor_ref: "gdn_1",
    actor_role: "guardian",
    subject_ref: "stu_1",
    correlation_id: "",
    detail: {},
    ...over,
  };
}

const NAMES = new Map([["stu_1", "Ali"]]);

// Every action in services/core-api identity/domain/audit.py.
const ACTIONS = [
  "guardian.registered",
  "guardian.signed_in",
  "guardian.sign_in_failed",
  "guardian.locked",
  "learner.created",
  "learner.signed_in",
  "learner.sign_in_failed",
  "learner.sign_in_denied_no_consent",
  "learner.locked",
  "learner.pin_reset",
  "learner.suspended",
  "learner.reinstated",
  "consent.granted",
  "consent.withdrawn",
  "session.refreshed",
  "session.signed_out",
  "session.revoked",
  "session.reuse_detected",
];

describe("auditEntry", () => {
  it.each(ACTIONS)("has readable copy for %s in both languages", (action) => {
    const entry = auditEntry(event(action), NAMES);
    expect(entry.key).not.toBe("guardian.audit.actions.unknown");
    expect(translate("en", entry.key)).not.toContain("guardian.");
    expect(translate("ur", entry.key)).not.toContain("guardian.");
  });

  it("names the guardian's own child and nobody else", () => {
    expect(auditEntry(event("learner.signed_in"), NAMES).childName).toBe("Ali");
    expect(auditEntry(event("learner.signed_in", { subject_ref: "stu_other" }), NAMES).childName).toBeNull();
  });

  it("lists the permissions a consent event covered, ignoring unknown scopes", () => {
    const entry = auditEntry(event("consent.granted", { detail: { scopes: ["learning_data", "voice_audio", "mystery"] } }), NAMES);
    expect(entry.scopes).toEqual(["guardian.consent.scopes.learning_data.title", "guardian.consent.scopes.voice_audio.title"]);
  });

  it("flags failures and protections as warnings", () => {
    expect(auditEntry(event("learner.locked"), NAMES).warning).toBe(true);
    expect(auditEntry(event("session.reuse_detected"), NAMES).warning).toBe(true);
    expect(auditEntry(event("learner.signed_in"), NAMES).warning).toBe(false);
  });

  it("shows an unknown action by name rather than dropping it", () => {
    const entry = auditEntry(event("learner.teleported"), NAMES);
    expect(translate("en", entry.key, entry.params)).toBe("Other activity (learner.teleported)");
  });
});

describe("auditView", () => {
  const events = [event("learner.signed_in"), event("session.refreshed"), event("session.refreshed", { event_id: "e2" })];

  it("hides routine token refreshes by default and says how many", () => {
    const view = auditView(events, NAMES);
    expect(view.entries).toHaveLength(1);
    expect(view.hiddenRoutine).toBe(2);
  });

  it("shows everything on request", () => {
    expect(auditView(events, NAMES, { showRoutine: true }).entries).toHaveLength(3);
  });
});

describe("nextAuditLimit", () => {
  it("offers more only when the server filled the page", () => {
    expect(nextAuditLimit(AUDIT_PAGE, 40)).toBeNull();
    expect(nextAuditLimit(AUDIT_PAGE, AUDIT_PAGE)).toBe(AUDIT_PAGE * 2);
  });
  it("stops at the server cap", () => {
    expect(nextAuditLimit(450, 450)).toBe(AUDIT_MAX);
    expect(nextAuditLimit(AUDIT_MAX, AUDIT_MAX)).toBeNull();
  });
});
