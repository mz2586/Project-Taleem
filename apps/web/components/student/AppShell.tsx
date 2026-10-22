"use client";
// App shell — header (the page's single h1), scrollable content, sticky bottom nav, offline badge,
// and a skip link that becomes visible on focus. Screens announce async changes through their own
// polite live regions; the shell's badge is a status region too.
import type { ReactNode } from "react";

import { useLocale } from "../../lib/i18n/useLocale";
import type { GradeBand } from "../../lib/student/config";
import { BottomNav } from "./BottomNav";
import { SyncStatusBadge } from "./SyncStatusBadge";

export function AppShell({
  title,
  band,
  showNav = true,
  children,
}: {
  title: string;
  band: GradeBand;
  showNav?: boolean;
  children: ReactNode;
}) {
  const { t } = useLocale();
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", maxWidth: 720, margin: "0 auto" }}>
      <a href="#main" className="skip-link">
        {t("common.skipToContent")}
      </a>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: "var(--space-2)",
          padding: "var(--space-3) var(--space-4)",
          borderBottom: "1px solid var(--color-focus-ring)",
        }}
      >
        <h1 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{title}</h1>
        <SyncStatusBadge />
      </header>
      <main
        id="main"
        tabIndex={-1}
        style={{ flex: 1, padding: "var(--space-4)", display: "grid", gap: "var(--space-4)", alignContent: "start" }}
      >
        {children}
      </main>
      {showNav ? <BottomNav band={band} /> : null}
    </div>
  );
}
