"use client";
// Sync status indicator. Wires the live sync summary (useSyncStatus — which also drives the
// auto-drain on reconnect) through lib/student/syncView.ts into the calm OfflineBadge, and opens a
// small panel that separates the three states: saved on this phone, sent to Taleem, and saved
// safely by Taleem — plus anything waiting for a grown-up or kept for help. A native
// <details>/<summary> disclosure: keyboard- and screen-reader-operable with no extra script.
import { formatDateTime } from "../../lib/guardian/format";
import { useLocale } from "../../lib/i18n/useLocale";
import { syncView } from "../../lib/student/syncView";
import { useSyncStatus } from "../../lib/student/useSyncStatus";
import { OfflineBadge } from "./OfflineBadge";

export function SyncStatusBadge() {
  const status = useSyncStatus();
  const { t, locale } = useLocale();
  const view = syncView({ online: status.online, summary: status, lastSyncAt: status.lastSyncAt });

  if (!view.hasDetail) return <OfflineBadge view={view} />;

  return (
    <details style={{ position: "relative" }}>
      <summary
        style={{
          minHeight: "var(--size-touch-min)",
          display: "inline-flex",
          alignItems: "center",
          cursor: "pointer",
          listStyle: "none",
          padding: "0 var(--space-2)",
          border: "1px solid var(--color-focus-ring)",
          borderRadius: "var(--radius-md)",
        }}
      >
        <OfflineBadge view={view} />
      </summary>
      <section
        aria-label={t("student.sync.panelLabel")}
        style={{
          position: "absolute",
          insetInlineEnd: 0,
          top: "100%",
          zIndex: 5,
          marginTop: "var(--space-1)",
          width: "min(320px, 90vw)",
          display: "grid",
          gap: "var(--space-2)",
          padding: "var(--space-3)",
          background: "var(--color-bg-canvas)",
          color: "var(--color-text-primary)",
          border: "1px solid var(--color-focus-ring)",
          borderRadius: "var(--radius-md)",
          fontSize: "var(--font-size-body-min)",
        }}
      >
        {view.held ? (
          <p style={{ margin: 0, fontWeight: 700 }}>
            <span aria-hidden="true">⏸ </span>
            {t(view.held.key, view.held.params)}
          </p>
        ) : null}
        {view.rejected ? <p style={{ margin: 0, fontWeight: 700 }}>{t(view.rejected.key, view.rejected.params)}</p> : null}
        {view.waitingReason ? <p style={{ margin: 0 }}>{t(view.waitingReason)}</p> : null}
        <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
          {view.rows.map((row) => (
            <li key={row.kind} style={{ display: "grid", gap: 2 }}>
              <strong>{t(row.label.key, row.label.params)}</strong>
              <span>{t(row.meaning)}</span>
            </li>
          ))}
        </ul>
        <p style={{ margin: 0, opacity: 0.85 }}>{t("student.sync.rows.recentNote")}</p>
        <p style={{ margin: 0 }}>
          {view.lastSyncAt !== null
            ? t("student.sync.lastSync", { time: formatDateTime(view.lastSyncAt, locale) })
            : t("student.sync.neverSynced")}
        </p>
      </section>
    </details>
  );
}
