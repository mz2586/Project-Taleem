// Offline dashboard read cache (Phase 6.2A).
//
// Caches the derived student read-model responses (today / homework / reviews / …) so the dashboard
// renders offline. Cached reads are DISPOSABLE snapshots, labelled with `fetched_at` so the UI can
// show an honest "as of" time. On reconnect they are refreshed. No child PII beyond student_ref.

import type { KVStore } from "./kv";
import { STORES } from "./kv";

export interface CachedRead<T = unknown> {
  cache_key: string;
  student_ref: string;
  endpoint: string;
  body: T;
  fetched_at: number;
}

function cacheKey(studentRef: string, endpoint: string): string {
  return `${endpoint}:${studentRef}`;
}

export class ReadCache {
  constructor(
    private readonly store: KVStore,
    private readonly now: () => number = Date.now,
  ) {}

  async put<T>(studentRef: string, endpoint: string, body: T): Promise<void> {
    const key = cacheKey(studentRef, endpoint);
    const rec: CachedRead<T> = {
      cache_key: key,
      student_ref: studentRef,
      endpoint,
      body,
      fetched_at: this.now(),
    };
    await this.store.put<CachedRead<T>>(STORES.readCache, key, rec);
  }

  async get<T>(studentRef: string, endpoint: string): Promise<CachedRead<T> | undefined> {
    return this.store.get<CachedRead<T>>(STORES.readCache, cacheKey(studentRef, endpoint));
  }

  // Clear a learner's cached reads (e.g. on "switch learner" — shared-device isolation).
  async clearStudent(studentRef: string): Promise<void> {
    const all = await this.store.getAll<CachedRead>(STORES.readCache);
    for (const rec of all) {
      if (rec.student_ref === studentRef) {
        await this.store.delete(STORES.readCache, rec.cache_key);
      }
    }
  }
}
