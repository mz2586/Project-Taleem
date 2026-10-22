// useSyncStatus (Phase 6.2B) — live sync status for the UI, and the auto-drain wiring.
// Registers Background Sync, drains automatically on reconnect, and surfaces the per-item status
// model (saved on this device / synchronized / server-confirmed, plus what is blocked and why).
// Client-only (runs in an effect). The model itself is the pure `summarizeSyncStatus`; this hook
// only gathers its inputs.

import { useEffect, useState } from "react";

import { summarizeSyncStatus, watchConnectivity } from "../offline";
import type { SyncStatusSummary } from "../offline";
import { sessionStore } from "../session/store";
import { getOfflineClient, learnerOf } from "./offlineClient";

export interface SyncStatusValue extends SyncStatusSummary {
  online: boolean;
  // Items still waiting to go (kept for existing callers; equals `waiting`).
  pending: number;
  lastSyncAt: number | null;
}

const EMPTY: SyncStatusSummary = summarizeSyncStatus({ queue: [], acks: [] });

export function useSyncStatus(pollMs = 4000): SyncStatusValue {
  const [online, setOnline] = useState(true);
  const [summary, setSummary] = useState<SyncStatusSummary>(EMPTY);
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null);

  useEffect(() => {
    const client = getOfflineClient();
    let alive = true;

    const refresh = async () => {
      const [queue, acks, lastBlock, diag] = await Promise.all([
        client.sync.queue.all(),
        client.sync.acks.all(),
        client.sync.acks.lastBlock(),
        client.sync.diagnostics.get(),
      ]);
      if (!alive) return;
      setSummary(
        summarizeSyncStatus({
          queue,
          acks,
          lastBlock,
          studentRef: learnerOf(sessionStore.peek()),
        }),
      );
      setLastSyncAt(diag.lastSyncAt);
    };

    void client.sync.registerBackgroundSync();
    const stopDrain = client.sync.startAutoDrain();
    const stopConn = watchConnectivity((o) => {
      setOnline(o);
      if (o) void client.sync.drain().then(refresh);
    });

    void refresh();
    const timer = setInterval(() => void refresh(), pollMs);

    return () => {
      alive = false;
      clearInterval(timer);
      stopDrain();
      stopConn();
    };
  }, [pollMs]);

  return { ...summary, online, pending: summary.waiting, lastSyncAt };
}
