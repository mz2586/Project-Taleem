"use client";
// App shell — header slot, scrollable content, sticky bottom nav, offline badge, and a skip link.
// The single aria-live region for the shell lives here (screens announce via their own regions too).
import type { ReactNode } from "react";

import type { GradeBand } from "../../lib/student/config";
import { BottomNav } from "./BottomNav";
import { OfflineBadge } from "./OfflineBadge";

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
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", maxWidth: 720, margin: "0 auto" }}>
      <a href="#main" style={{ position: "absolute", insetInlineStart: -9999 }}>
        Skip to content
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
        <OfflineBadge />
      </header>
      <main id="main" style={{ flex: 1, padding: "var(--space-4)", display: "grid", gap: "var(--space-4)", alignContent: "start" }}>
        {children}
      </main>
      {showNav ? <BottomNav band={band} /> : null}
    </div>
  );
}
