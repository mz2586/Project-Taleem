// Browser offline client (Phase 6.2B) — wires the offline-lite library to the student API.
// A lazily-built singleton so the durable queue, sync client, and stores are shared app-wide.
// Call only in the browser (uses IndexedDB); safe to reference under SSR but build it in an effect.

import { createOfflineClient } from "../offline";
import type { OfflineClient } from "../offline";
import { offlineApi, syncApi } from "./api";

let singleton: OfflineClient | null = null;

export function getOfflineClient(): OfflineClient {
  if (!singleton) {
    singleton = createOfflineClient({
      fetchPackage: (lessonId: string) => offlineApi.fetchPackage(lessonId),
      postBatch: (cursor, deltas) => syncApi.batch(cursor, deltas),
    });
  }
  return singleton;
}
