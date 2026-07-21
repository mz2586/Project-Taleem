"use client";
// Persistent, calm online/offline indicator (+ pending-to-sync count). Never alarming; the learner
// is never blocked or scolded for being offline.
import { useEffect, useState } from "react";

export function OfflineBadge({ pendingCount = 0 }: { pendingCount?: number }) {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  const message = online
    ? pendingCount > 0
      ? `Saving ${pendingCount}…`
      : "Online"
    : pendingCount > 0
      ? `Offline · ${pendingCount} saved`
      : "Offline · saved on your device";

  return (
    <span
      role="status"
      aria-live="polite"
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-1)",
        fontSize: "var(--font-size-body-min)",
        color: "var(--color-text-primary)",
      }}
    >
      <span aria-hidden="true">{online ? "●" : "◍"}</span>
      <span>{message}</span>
    </span>
  );
}
