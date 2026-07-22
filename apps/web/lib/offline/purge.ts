// Cache purge / de-enrolment mechanism (Phase 6.2C-1).
//
// Clears a learner's on-device child-learning data (the C2 stores: read_cache, progress_local,
// checkpoints, evidence_queue) so a consent withdrawal / de-enrolment reaches the device — the
// erasure obligation (retention schedule; OFFLINE_SECURITY_REVIEW §5, gap SG-5). The C0 curriculum
// stores (packages/content) hold no child data and are left in place.
//
// This is the MECHANISM only. The TRIGGER (who is de-enrolled) is governance-gated (M-Gov / WS8) and
// out of scope for 6.2C-1; a server may deliver it later via a `purge` field on the sync response.
// Whether un-synced-but-withdrawn data is discarded or synced-then-erased is a policy decision (D-5);
// the default here is to erase (includeUnsynced = true).

import type { SyncDiagnosticsStore } from "./diagnostics";
import type { KVStore } from "./kv";
import { STORES } from "./kv";
import type { LocalProgressEvent, QueuedDelta, SessionCheckpoint } from "./types";
import type { CachedRead } from "./readCache";

export interface PurgeResult {
  readCache: number;
  progress: number;
  checkpoints: number;
  queued: number;
}

export class PurgeService {
  constructor(
    private readonly store: KVStore,
    private readonly diagnostics?: SyncDiagnosticsStore,
  ) {}

  // Clear all C2 data for one learner. Returns how many records were removed per store.
  async purgeStudent(
    studentRef: string,
    opts: { includeUnsynced?: boolean } = {},
  ): Promise<PurgeResult> {
    const includeUnsynced = opts.includeUnsynced ?? true;
    const result: PurgeResult = { readCache: 0, progress: 0, checkpoints: 0, queued: 0 };

    const reads = await this.store.getAll<CachedRead>(STORES.readCache);
    for (const r of reads) {
      if (r.student_ref === studentRef) {
        await this.store.delete(STORES.readCache, r.cache_key);
        result.readCache++;
      }
    }

    const progress = await this.store.getAll<LocalProgressEvent>(STORES.progress);
    for (const p of progress) {
      if (p.student_ref === studentRef) {
        await this.store.delete(STORES.progress, p.client_event_id);
        result.progress++;
      }
    }

    const checkpoints = await this.store.getAll<SessionCheckpoint>(STORES.checkpoints);
    for (const c of checkpoints) {
      if (c.student_ref === studentRef) {
        await this.store.delete(STORES.checkpoints, c.session_id);
        result.checkpoints++;
      }
    }

    const queued = await this.store.getAll<QueuedDelta>(STORES.evidenceQueue);
    for (const q of queued) {
      if (String(q.payload["student_ref"]) !== studentRef) continue;
      const settled = q.syncState === "dead";
      if (includeUnsynced || settled) {
        await this.store.delete(STORES.evidenceQueue, q.clientEventId);
        result.queued++;
      }
    }

    await this.diagnostics?.recordPurge();
    return result;
  }
}
