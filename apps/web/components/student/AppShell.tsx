"use client";
// App shell — header (the page's single h1), scrollable content, sticky bottom nav, offline badge,
// and a skip link that becomes visible on focus. Screens announce async changes through their own
// polite live regions; the shell's badge is a status region too.
//
// Every screen's header also carries "Tell a grown-up": the safeguarding entry, with a picture and
// words, reachable in one tap (doc 15 SAC-7). It is separate from the lesson player's "Help" (stuck
// on a question); it opens /student/help with the screen (and lesson, if any) as context.
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { buttonStyle } from "../../design-system/Button";
import { useLocale } from "../../lib/i18n/useLocale";
import { helpHref } from "../../lib/safeguarding/context";
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
  const pathname = usePathname() ?? "";
  const [help, setHelp] = useState(() => helpHref(pathname));
  useEffect(() => {
    // The lesson id, when a screen has one, is in the query string (read after mount, not in render).
    setHelp(helpHref(pathname, new URLSearchParams(window.location.search).get("lesson")));
  }, [pathname]);
  const onHelp = pathname === "/student/help";
  return (
    // App-shell layout: a full-height column where only <main> scrolls and the bottom nav is the
    // last row. A sticky nav over scrolling content covered whatever control sat beneath it (axe
    // target-size caught "Why this next?" left with a 17px visible strip).
    <div data-print-shell="" style={{ display: "flex", flexDirection: "column", height: "100dvh", maxWidth: 720, margin: "0 auto" }}>
      <a href="#main" className="skip-link">
        {t("common.skipToContent")}
      </a>
      <header
        data-print="hide"
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          flexWrap: "wrap",
          gap: "var(--space-2)",
          padding: "var(--space-3) var(--space-4)",
          borderBottom: "1px solid var(--color-focus-ring)",
        }}
      >
        <h1 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{title}</h1>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "var(--space-2)" }}>
          <SyncStatusBadge />
          <Link
            href={help}
            aria-current={onHelp ? "page" : undefined}
            style={{ ...buttonStyle("ghost"), border: "2px solid var(--color-brand)", fontWeight: 700 }}
          >
            <span aria-hidden="true">🙋</span>
            <span>{t("safeguarding.entry.label")}</span>
          </Link>
        </div>
      </header>
      <main
        id="main"
        tabIndex={-1}
        // minmax(0, 1fr): a grid track otherwise grows to its widest child, so one long Urdu line
        // could widen the page past the screen (the browser journey caught a 395px page on 393px).
        style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "var(--space-4)", display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: "var(--space-4)", alignContent: "start", overflowWrap: "anywhere" }}
      >
        {children}
      </main>
      {showNav ? <BottomNav band={band} /> : null}
    </div>
  );
}
