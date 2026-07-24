"use client";
// Guardian portal shell — header + skip link + scrollable content. Reuses the shared design tokens
// (no student bottom-nav; the guardian view is read-only). Responsive: constrained max-width, fluid.
import Link from "next/link";
import type { ReactNode } from "react";

export function GuardianShell({
  title,
  back,
  children,
}: {
  title: string;
  back?: { href: string; label: string };
  children: ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: "100vh",
        maxWidth: 820,
        margin: "0 auto",
      }}
    >
      <a href="#main" style={{ position: "absolute", insetInlineStart: -9999 }}>
        Skip to content
      </a>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-3)",
          padding: "var(--space-3) var(--space-4)",
          borderBottom: "1px solid var(--color-focus-ring)",
        }}
      >
        {back ? (
          <Link href={back.href} aria-label={back.label} style={{ textDecoration: "none" }}>
            <span aria-hidden="true">←</span>
          </Link>
        ) : null}
        <h1 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{title}</h1>
      </header>
      <main
        id="main"
        style={{
          flex: 1,
          padding: "var(--space-4)",
          display: "grid",
          gap: "var(--space-4)",
          alignContent: "start",
        }}
      >
        {children}
      </main>
    </div>
  );
}
