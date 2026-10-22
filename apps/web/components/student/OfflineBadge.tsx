"use client";
// Persistent, calm online/offline indicator (+ pending-to-sync count). Never alarming; the learner
// is never blocked or scolded for being offline.
import { useEffect, useState } from "react";

import { useLocale } from "../../lib/i18n/useLocale";
import { watchConnectivity } from "../../lib/offline";

export function OfflineBadge({ pendingCount = 0 }: { pendingCount?: number }) {
  const [online, setOnline] = useState(true);
  const { t } = useLocale();

  useEffect(() => watchConnectivity(setOnline), []);

  const message = online
    ? pendingCount > 0
      ? t("common.connectivity.saving", { count: pendingCount })
      : t("common.connectivity.online")
    : pendingCount > 0
      ? t("common.connectivity.offlineSaved", { count: pendingCount })
      : t("common.connectivity.offline");

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
