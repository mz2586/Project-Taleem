"use client";
// Bottom navigation — ≤5 thumb-reachable destinations, RTL-mirrored, aria-current on the active one.
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { GradeBand } from "../../lib/student/config";
import { isActive, navItemsFor } from "../../lib/student/navModel";

export function BottomNav({ band }: { band: GradeBand }) {
  const pathname = usePathname();
  const items = navItemsFor(band);
  return (
    <nav
      aria-label="Main"
      style={{
        position: "sticky",
        bottom: 0,
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
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
