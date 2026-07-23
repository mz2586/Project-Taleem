// Pure navigation model for the student bottom nav — no React, unit-testable.
//
// The early band deliberately shows fewer destinations (less to reason about for the youngest
// learners); middle/senior get the full browsing set. Active-state detection is a prefix match so a
// nested route (e.g. /student/today/detail) still highlights its top-level destination.

import type { GradeBand } from "./config";

export interface NavItem {
  href: string;
  label: string;
  symbol: string;
}

export const FULL_NAV: readonly NavItem[] = [
  { href: "/student/today", label: "Today", symbol: "☀" },
  { href: "/student/subjects", label: "Learn", symbol: "📚" },
  { href: "/student/homework", label: "Homework", symbol: "✎" },
  { href: "/student/progress", label: "Progress", symbol: "▲" },
  { href: "/student/profile", label: "Profile", symbol: "👤" },
];

// Early band: Today / Progress / Profile only (a subset of FULL, same objects so labels stay in sync).
export const EARLY_NAV: readonly NavItem[] = [FULL_NAV[0]!, FULL_NAV[3]!, FULL_NAV[4]!];

export function navItemsFor(band: GradeBand): readonly NavItem[] {
  return band === "early" ? EARLY_NAV : FULL_NAV;
}

export function isActive(pathname: string | null | undefined, href: string): boolean {
  return pathname ? pathname.startsWith(href) : false;
}
