"use client";
// Bottom navigation — ≤5 thumb-reachable destinations, RTL-mirrored, aria-current on the active one.
import Link from "next/link";
import { usePathname } from "next/navigation";

import type { GradeBand } from "../../lib/student/config";

interface NavItem {
  href: string;
  label: string;
  symbol: string;
}

// Early band shows fewer choices (less to reason about); older bands get browsing destinations.
const FULL: NavItem[] = [
  { href: "/student/today", label: "Today", symbol: "☀" },
  { href: "/student/subjects", label: "Learn", symbol: "📚" },
  { href: "/student/homework", label: "Homework", symbol: "✎" },
  { href: "/student/progress", label: "Progress", symbol: "▲" },
  { href: "/student/profile", label: "Profile", symbol: "👤" },
];
const EARLY: NavItem[] = [FULL[0]!, FULL[3]!, FULL[4]!];

export function BottomNav({ band }: { band: GradeBand }) {
  const pathname = usePathname();
  const items = band === "early" ? EARLY : FULL;
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
        const active = pathname?.startsWith(item.href) ?? false;
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
