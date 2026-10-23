"use client";
// Bottom navigation — ≤5 thumb-reachable destinations, direction-mirrored by the document's `dir`,
// aria-current on the active one. Labels come from the catalog via the nav model's keys.
import Link from "next/link";
import { usePathname } from "next/navigation";

import { useLocale } from "../../lib/i18n/useLocale";
import type { GradeBand } from "../../lib/student/config";
import { isActive, navItemsFor } from "../../lib/student/navModel";

export function BottomNav({ band }: { band: GradeBand }) {
  const pathname = usePathname();
  const { t } = useLocale();
  const items = navItemsFor(band);
  return (
    <nav
      aria-label={t("student.nav.label")}
      style={{
        // The last row of the AppShell column (see AppShell): it never overlays the content.
        flexShrink: 0,
        display: "flex",
        justifyContent: "space-around",
        borderTop: "1px solid var(--color-focus-ring)",
        background: "var(--color-bg-canvas)",
        padding: "var(--space-1) 0",
      }}
    >
      {items.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            aria-current={active ? "page" : undefined}
            style={{
              minHeight: "var(--size-touch-min)",
              minWidth: "var(--size-touch-min)",
              // Equal shares of the bar, never wider: Nastaliq labels are wider than their English
              // counterparts, and content-sized items pushed the Urdu page 2-3px past a 393px screen.
              flex: "1 1 0",
              textAlign: "center",
              overflowWrap: "anywhere",
              display: "inline-flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: "2px",
              textDecoration: "none",
              color: active ? "var(--color-brand)" : "var(--color-text-primary)",
              fontWeight: active ? 700 : 400,
              fontSize: "var(--font-size-body-min)",
            }}
          >
            <span aria-hidden="true" style={{ fontSize: "20px" }}>
              {item.symbol}
            </span>
            <span>{t(item.labelKey)}</span>
          </Link>
        );
      })}
    </nav>
  );
}
