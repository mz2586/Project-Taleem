// Curriculum Studio — internal authoring tool chrome (LTR desktop; distinct from the student PWA).
import type { ReactNode } from "react";

export const metadata = {
  title: "Curriculum Studio",
  description: "Internal curriculum authoring platform — no child data.",
};

export default function StudioLayout({ children }: { children: ReactNode }) {
  return (
    <div dir="ltr" style={{ fontFamily: "var(--font-latin)", padding: "var(--space-6)" }}>
      <header style={{ borderBottom: "1px solid var(--color-border-default)", marginBottom: "var(--space-4)" }}>
        <strong style={{ color: "var(--color-brand)" }}>Curriculum Studio</strong>
        <span style={{ color: "var(--color-text-primary)", marginInlineStart: "var(--space-2)" }}>
          — governance-safe · no child data
        </span>
      </header>
      {children}
    </div>
  );
}
