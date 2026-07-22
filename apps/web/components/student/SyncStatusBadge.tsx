"use client";
// Sync status indicator (Phase 6.2B). Wires the live pending-to-sync count into the calm
// OfflineBadge and drives the auto-drain on reconnect. Never blocks or alarms the learner.
import { useSyncStatus } from "../../lib/student/useSyncStatus";
import { OfflineBadge } from "./OfflineBadge";

export function SyncStatusBadge() {
  const { pending } = useSyncStatus();
  return <OfflineBadge pendingCount={pending} />;
}
