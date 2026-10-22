// Per-item sync status model (GLOBAL_PRODUCT_SCOPE §E: "a visible distinction between saved on
// this device, synchronized, and server-confirmed").
//
// The three states, defined against what the server actually guarantees today:
//
//   saved_on_device   The item is in the durable IndexedDB queue and the server has NOT
//                     acknowledged it. It survives reloads, crashes and restarts. (Includes items
//                     that are waiting, retrying, held for permission, or rejected — `blocked`
//                     says which.)
//   synchronized      The server acknowledged the item, but its effect is NOT a durable server
//                     record: progress / completion / preference deltas are applied to the
//                     server's process-local policy store, and an `ignored` attempt (e.g. a
//                     summative awaiting a mentor) was received but not recorded as evidence.
//   server_confirmed  The server acknowledged the item AND it is a durable server record: an
//                     `attempt.submitted` answered `applied` or `duplicate` — the AssessmentEvidence
//                     row was committed (or already existed, keyed by evidence_id) before the
//                     response was sent.
//
// Pure functions only — no storage, no React — so the model is unit-tested directly and
// `useSyncStatus` is a thin adapter over it. The bounded ack ledger that lets the UI keep showing
// an item after its local queue copy is released lives in `AckLedger` below.

import type { KVStore } from "./kv";
import { STORES } from "./kv";
import { ownerOf } from "./syncQueue";
import type { AckRecord, QueuedDelta, SyncBlock, SyncStatus } from "./types";

export type ItemSyncState = "saved_on_device" | "synchronized" | "server_confirmed";

// Why a saved-on-device item is not moving (null = it will go on the next drain).
export type ItemBlock = "permission" | "rejected" | null;

export interface ItemStatus {
  clientEventId: string;
  state: ItemSyncState;
  blocked: ItemBlock;
  reason: string | null;
}

// Status of an item still in the local queue.
export function queuedItemStatus(d: QueuedDelta): ItemStatus {
  const blocked: ItemBlock =
    d.syncState === "held" ? "permission" : d.syncState === "dead" ? "rejected" : null;
  return {
    clientEventId: d.clientEventId,
    state: "saved_on_device",
    blocked,
    reason: blocked ? (d.heldReason ?? d.lastError ?? null) : null,
  };
}

// Is a server acknowledgement a DURABLE server record? (see the module comment)
export function isDurableAck(type: AckRecord["type"], status: SyncStatus): boolean {
  return type === "attempt.submitted" && (status === "applied" || status === "duplicate");
}

// Status of an item the server acknowledged (its local queue copy has been released).
export function ackedItemStatus(a: AckRecord): ItemStatus {
  return {
    clientEventId: a.clientEventId,
    state: isDurableAck(a.type, a.status) ? "server_confirmed" : "synchronized",
    blocked: null,
    reason: null,
  };
}

// One item's status, preferring the live queue record over the ledger (a re-queued id is, again,
// only saved on this device until the server answers).
export function itemStatus(
  clientEventId: string,
  queue: readonly QueuedDelta[],
  acks: readonly AckRecord[],
): ItemStatus | null {
  const q = queue.find((d) => d.clientEventId === clientEventId);
  if (q) return queuedItemStatus(q);
  const a = acks.find((r) => r.clientEventId === clientEventId);
  return a ? ackedItemStatus(a) : null;
}

export interface SyncStatusSummary {
  savedOnDevice: number; // everything not yet acknowledged (waiting + held + rejected)
  waiting: number; // will go on the next drain
  held: number; // blocked by permission (consent withdrawn / learner suspended / not this learner)
  rejected: number; // server rejected — retained with a reason for support
  synchronized: number;
  serverConfirmed: number;
  // The single most important thing the UI should say about sync right now.
  blocked: SyncBlock | null;
  blockedCode: string | null;
}

export interface SummaryInput {
  queue: readonly QueuedDelta[];
  acks: readonly AckRecord[];
  lastBlock?: { reason: SyncBlock; code: string | null } | null;
  // Restrict the summary to one learner (shared device); device-level deltas are always included.
  studentRef?: string | null;
}

// Summarise the whole picture for the UI. Pure.
export function summarizeSyncStatus(input: SummaryInput): SyncStatusSummary {
  const mine = (owner: string | null) =>
    input.studentRef == null || owner === null || owner === input.studentRef;
  const queue = input.queue.filter((d) => mine(ownerOf(d)));
  const acks = input.acks.filter((a) => mine(a.studentRef));

  let waiting = 0;
  let held = 0;
  let rejected = 0;
  let heldCode: string | null = null;
  for (const d of queue) {
    const s = queuedItemStatus(d);
    if (s.blocked === "permission") {
      held++;
      heldCode = heldCode ?? s.reason;
    } else if (s.blocked === "rejected") rejected++;
    else waiting++;
  }
  let synchronized = 0;
  let serverConfirmed = 0;
  for (const a of acks) {
    if (ackedItemStatus(a).state === "server_confirmed") serverConfirmed++;
    else synchronized++;
  }

  // Held items always surface as a permission block, even if the last drain stopped for another
  // reason — the learner/guardian must see that some work cannot be sent.
  let blocked: SyncBlock | null = input.lastBlock?.reason ?? null;
  let blockedCode: string | null = input.lastBlock?.code ?? null;
  if (held > 0 && blocked !== "permission") {
    blocked = "permission";
    blockedCode = heldCode;
  }
  if (blocked !== "permission" && waiting === 0) {
    // Nothing waiting: a stale offline/server/auth block is no longer meaningful.
    blocked = null;
    blockedCode = null;
  }

  return {
    savedOnDevice: queue.length,
    waiting,
    held,
    rejected,
    synchronized,
    serverConfirmed,
    blocked,
    blockedCode,
  };
}

// ---------------------------------------------------------------- bounded ack ledger

const ACKS_KEY = "sync_acks";
const BLOCK_KEY = "sync_block";
export const ACK_LEDGER_LIMIT = 500;

export class AckLedger {
  constructor(
    private readonly store: KVStore,
    private readonly limit: number = ACK_LEDGER_LIMIT,
  ) {}

  async all(): Promise<AckRecord[]> {
    return (await this.store.get<AckRecord[]>(STORES.syncMeta, ACKS_KEY)) ?? [];
  }

  // Record acknowledgements (newest last), keeping only the most recent `limit`. Recorded BEFORE
  // the queue copy is released, so a crash in between leaves the item in the queue (re-sent →
  // duplicate) rather than missing from both.
  async record(records: AckRecord[]): Promise<void> {
    if (records.length === 0) return;
    const byId = new Map((await this.all()).map((r) => [r.clientEventId, r] as const));
    for (const r of records) {
      byId.delete(r.clientEventId);
      byId.set(r.clientEventId, r);
    }
    const merged = Array.from(byId.values());
    await this.store.put<AckRecord[]>(
      STORES.syncMeta,
      ACKS_KEY,
      merged.slice(Math.max(0, merged.length - this.limit)),
    );
  }

  // Drop a learner's acks (de-enrolment purge: the ledger carries student_refs).
  async forget(studentRef: string): Promise<void> {
    const kept = (await this.all()).filter((r) => r.studentRef !== studentRef);
    await this.store.put<AckRecord[]>(STORES.syncMeta, ACKS_KEY, kept);
  }

  async lastBlock(): Promise<{ reason: SyncBlock; code: string | null } | null> {
    return (await this.store.get<{ reason: SyncBlock; code: string | null }>(STORES.syncMeta, BLOCK_KEY)) ?? null;
  }

  async setBlock(block: { reason: SyncBlock; code: string | null } | null): Promise<void> {
    if (block) await this.store.put(STORES.syncMeta, BLOCK_KEY, block);
    else await this.store.delete(STORES.syncMeta, BLOCK_KEY);
  }
}
