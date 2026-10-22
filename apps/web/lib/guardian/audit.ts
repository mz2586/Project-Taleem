// The family audit trail, made readable. Pure; unit-tested.
//
// `GET /v1/identity/audit` returns refs and machine action names, never names (by design: the audit
// log holds no PII). A guardian needs "Ali signed in · 22 Oct, 14:05", so this maps each action to a
// catalog sentence, resolves the subject ref to a display name from the guardian's own learner list
// (a ref the guardian does not own stays anonymous), and reads the scope list from the detail of a
// consent event so "permission given" says which permissions.

import type { MessageKey } from "../i18n/messages";
import type { AuditEvent, ConsentScope } from "../session/types";
import { isKnownScope, scopeCopy } from "./consent";

// Every action in services/core-api identity/domain/audit.py `AuditAction`.
const ACTION_KEYS: Record<string, MessageKey> = {
  "guardian.registered": "guardian.audit.actions.guardian_registered",
  "guardian.signed_in": "guardian.audit.actions.guardian_signed_in",
  "guardian.sign_in_failed": "guardian.audit.actions.guardian_sign_in_failed",
  "guardian.locked": "guardian.audit.actions.guardian_locked",
  "learner.created": "guardian.audit.actions.learner_created",
  "learner.signed_in": "guardian.audit.actions.learner_signed_in",
  "learner.sign_in_failed": "guardian.audit.actions.learner_sign_in_failed",
  "learner.sign_in_denied_no_consent": "guardian.audit.actions.learner_sign_in_denied_no_consent",
  "learner.locked": "guardian.audit.actions.learner_locked",
  "learner.pin_reset": "guardian.audit.actions.learner_pin_reset",
  "learner.suspended": "guardian.audit.actions.learner_suspended",
  "learner.reinstated": "guardian.audit.actions.learner_reinstated",
  "consent.granted": "guardian.audit.actions.consent_granted",
  "consent.withdrawn": "guardian.audit.actions.consent_withdrawn",
  "session.refreshed": "guardian.audit.actions.session_refreshed",
  "session.signed_out": "guardian.audit.actions.session_signed_out",
  "session.revoked": "guardian.audit.actions.session_revoked",
  "session.reuse_detected": "guardian.audit.actions.session_reuse_detected",
};

/** Actions a guardian should notice: something went wrong or a protection kicked in. */
const WARNING_ACTIONS = new Set([
  "guardian.sign_in_failed",
  "guardian.locked",
  "learner.sign_in_failed",
  "learner.sign_in_denied_no_consent",
  "learner.locked",
  "learner.suspended",
  "session.reuse_detected",
]);

/** Routine token housekeeping: true, but noise in a list a guardian reads. Hidden by default. */
const ROUTINE_ACTIONS = new Set(["session.refreshed"]);

export interface AuditEntry {
  id: string;
  at: number;
  /** The sentence; `{action}` is filled for an unknown action. */
  key: MessageKey;
  params: Record<string, string>;
  /** The child's display name when the event is about one of the guardian's own learners. */
  childName: string | null;
  /** Permission titles named by a consent event. */
  scopes: MessageKey[];
  warning: boolean;
}

function scopesOf(event: AuditEvent): ConsentScope[] {
  const raw = event.detail?.["scopes"];
  if (!Array.isArray(raw)) return [];
  return raw.filter((s): s is ConsentScope => typeof s === "string" && isKnownScope(s));
}

export function auditEntry(event: AuditEvent, names: ReadonlyMap<string, string>): AuditEntry {
  const key = ACTION_KEYS[event.action];
  return {
    id: event.event_id,
    at: event.at,
    key: key ?? "guardian.audit.actions.unknown",
    params: key ? {} : { action: event.action },
    childName: names.get(event.subject_ref) ?? null,
    scopes: event.action.startsWith("consent.") ? scopesOf(event).map((s) => scopeCopy(s).title) : [],
    warning: WARNING_ACTIONS.has(event.action),
  };
}

export interface AuditView {
  entries: AuditEntry[];
  /** How many routine entries were left out. */
  hiddenRoutine: number;
}

/** Events (newest first, as served) to readable entries, routine refreshes hidden unless asked. */
export function auditView(
  events: readonly AuditEvent[],
  names: ReadonlyMap<string, string>,
  options: { showRoutine?: boolean } = {},
): AuditView {
  const visible = options.showRoutine ? events : events.filter((e) => !ROUTINE_ACTIONS.has(e.action));
  return {
    entries: visible.map((e) => auditEntry(e, names)),
    hiddenRoutine: events.length - visible.length,
  };
}

/** Page sizes for "show more". The server caps `limit` at 500. */
export const AUDIT_PAGE = 100;
export const AUDIT_MAX = 500;

export function nextAuditLimit(current: number, received: number): number | null {
  if (received < current) return null; // the server had no more to give
  if (current >= AUDIT_MAX) return null;
  return Math.min(AUDIT_MAX, current + AUDIT_PAGE);
}
