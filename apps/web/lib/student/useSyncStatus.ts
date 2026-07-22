// useSyncStatus (Phase 6.2B) — live sync status for the UI, and the auto-drain wiring.
// Registers Background Sync, drains automatically on reconnect, and surfaces the pending count +
// last-sync time. Client-only (runs in an effect). No offline auth, no consent-gated telemetry.

import { useEffect, useState } from "react";

import { watchConnectivity } from "../offline";
import { getOfflineClient } from "./offlineClient";

export interface SyncStatusValue {
  online: boolean;
  pending: number;
  lastSyncAt: number | null;
}

export function useSyncStatus(pollMs = 4000): SyncStatusValue {
  const [online, setOnline] = useState(true);
  const [pending, setPending] = useState(0);
  const [lastSyncAt, setLastSyncAt] = useState<number | null>(null);

  useEffect(() => {
    const client = getOfflineClient();
    let alive = true;

    const refresh = async () => {
      const count = await client.sync.queue.pendingCount();
      const diag = await client.sync.diagnostics.get();
      if (alive) {
        setPending(count);
        setLastSyncAt(diag.lastSyncAt);
      }
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

  return { online, pending, lastSyncAt };
}
