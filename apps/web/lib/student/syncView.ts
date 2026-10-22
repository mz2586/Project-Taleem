// What the student screens say about offline sync. Pure; unit-tested.
//
// GLOBAL_PRODUCT_SCOPE §E: "the UI distinguishes local saves from server-confirmed synchronization".
// The data is lib/offline/syncStatus.ts `summarizeSyncStatus` (via useSyncStatus); this module
// turns it into words for a child who may read slowly:
//
//   saved on device   -> "Saved on this phone"   (in the durable queue; not acknowledged yet)
//   synchronized      -> "Sent to Taleem"        (acknowledged, but not a durable server record)
//   server confirmed  -> "Saved safely by Taleem" (acknowledged AND a committed evidence record)
//
// Two rules that matter more than the wording:
// - Held work (a 403: permission withdrawn, account paused) is never described as lost or failed.
//   It is kept on the phone and goes when a grown-up allows learning again.
// - Rejected (dead-lettered) work is also kept on the phone with its reason, so the message says
//   that and points to a grown-up or teacher — not "error" or "failed".
//
// The synchronized / server-confirmed counts come from a bounded acknowledgement ledger (the most
// recent 500), so the panel calls them "recent work" rather than a lifetime total.

import type { MessageKey } from "../i18n/messages";
import type { SyncStatusSummary } from "../offline";

export interface SyncViewInput {
  online: boolean;
  summary: SyncStatusSummary;
  /** Milliseconds since the epoch (SyncDiagnostics.lastSyncAt), or null if never. */
  lastSyncAt: number | null;
}

export interface Line {
  key: MessageKey;
  params?: Record<string, number>;
}

export type SyncTone = "calm" | "busy" | "attention";

export interface SyncRow {
  kind: "device" | "sent" | "confirmed";
  label: Line;
  /** One short sentence: what this state means. */
  meaning: MessageKey;
  count: number;
}

export interface SyncView {
  /** The badge's one line. */
  headline: Line;
  tone: SyncTone;
  /** Decorative symbol (aria-hidden); the headline carries the meaning. */
  symbol: string;
  /** The three states, always in this order, for the detail panel. */
  rows: SyncRow[];
  /** Why some work is waiting for a grown-up, or null. */
  held: Line | null;
  /** Work the server refused, kept on the phone, or null. */
  rejected: Line | null;
  /** Why work that would go is not going right now (offline, sign-in, server), or null. */
  waitingReason: MessageKey | null;
  /** Unix seconds of the last successful sync, or null. */
  lastSyncAt: number | null;
  /** Whether anything at all is worth opening the panel for. */
  hasDetail: boolean;
}

const HELD_REASON: Record<string, MessageKey> = {
  CONSENT_REQUIRED: "student.sync.held.consent",
  LEARNER_INACTIVE: "student.sync.held.paused",
};

export function heldReasonKey(code: string | null): MessageKey {
  return (code && HELD_REASON[code]) || "student.sync.held.other";
}

export function syncView({ online, summary, lastSyncAt }: SyncViewInput): SyncView {
  const { waiting, held, rejected, savedOnDevice, synchronized, serverConfirmed, blocked, blockedCode } = summary;

  let headline: Line;
  let tone: SyncTone;
  let symbol: string;
  if (held > 0) {
    // Most important: work exists that cannot go until a grown-up acts. Calm words, but noticed.
    headline = { key: "student.sync.badge.held", params: { count: savedOnDevice } };
    tone = "attention";
    symbol = "⏸";
  } else if (!online) {
    headline =
      savedOnDevice > 0
        ? { key: "student.sync.badge.offlineSaved", params: { count: savedOnDevice } }
        : { key: "student.sync.badge.offline" };
    tone = "calm";
    symbol = "◍";
  } else if (waiting > 0 && (blocked === "server" || blocked === "auth" || blocked === "offline")) {
    headline = { key: "student.sync.badge.later", params: { count: savedOnDevice } };
    tone = "calm";
    symbol = "◐";
  } else if (waiting > 0) {
    headline = { key: "student.sync.badge.sending", params: { count: waiting } };
    tone = "busy";
    symbol = "↻";
  } else if (rejected > 0) {
    headline = { key: "student.sync.badge.rejected", params: { count: rejected } };
    tone = "attention";
    symbol = "!";
  } else if (synchronized + serverConfirmed > 0) {
    headline = { key: "student.sync.badge.allSent" };
    tone = "calm";
    symbol = "✓";
  } else {
    headline = { key: "student.sync.badge.online" };
    tone = "calm";
    symbol = "●";
  }

  const waitingReason: MessageKey | null =
    waiting === 0
      ? null
      : !online || blocked === "offline"
        ? "student.sync.waiting.offline"
        : blocked === "auth"
          ? "student.sync.waiting.signIn"
          : blocked === "server"
            ? "student.sync.waiting.server"
            : null;

  return {
    headline,
    tone,
    symbol,
    rows: [
      { kind: "device", label: { key: "student.sync.rows.device", params: { count: savedOnDevice } }, meaning: "student.sync.rows.deviceMeaning", count: savedOnDevice },
      { kind: "sent", label: { key: "student.sync.rows.sent", params: { count: synchronized } }, meaning: "student.sync.rows.sentMeaning", count: synchronized },
      {
        kind: "confirmed",
        label: { key: "student.sync.rows.confirmed", params: { count: serverConfirmed } },
        meaning: "student.sync.rows.confirmedMeaning",
        count: serverConfirmed,
      },
    ],
    held: held > 0 ? { key: heldReasonKey(blockedCode), params: { count: held } } : null,
    rejected: rejected > 0 ? { key: "student.sync.rejected", params: { count: rejected } } : null,
    waitingReason,
    lastSyncAt: lastSyncAt === null ? null : Math.floor(lastSyncAt / 1000),
    hasDetail: savedOnDevice + synchronized + serverConfirmed > 0 || !online,
  };
}
