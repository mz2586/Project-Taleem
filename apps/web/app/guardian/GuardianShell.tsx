"use client";
// Guardian portal shell — skip link, the page's single h1, guardian navigation, the language choice,
// and sign-out. Token-only styling; logical properties so it mirrors correctly in RTL and LTR.
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { Button } from "@/design-system/Button";
import { useLocale } from "@/lib/i18n/useLocale";
import { sessionStore } from "@/lib/session/store";

import { LanguagePicker } from "./LanguagePicker";

const NAV = [
  { href: "/guardian", key: "guardian.shell.dashboard" },
  { href: "/guardian/family", key: "guardian.shell.family" },
] as const;

export function GuardianShell({ title, children }: { title: string; children: ReactNode }) {
  const { t } = useLocale();
  const pathname = usePathname();
  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: "100vh", maxWidth: 820, margin: "0 auto" }}>
      <a href="#main" className="skip-link">
        {t("common.skipToContent")}
      </a>
      <header
        style={{
          display: "grid",
          gap: "var(--space-2)",
          padding: "var(--space-3) var(--space-4)",
          borderBottom: "1px solid var(--color-focus-ring)",
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "var(--space-2)" }}>
          <h1 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{title}</h1>
          <LanguagePicker />
        </div>
        <nav aria-label={t("guardian.shell.navLabel")}>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "flex", flexWrap: "wrap", gap: "var(--space-2)", alignItems: "center" }}>
            {NAV.map((item) => {
              const current = pathname === item.href;
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={current ? "page" : undefined}
                    style={{
                      display: "inline-flex",
                      alignItems: "center",
                      minHeight: "var(--size-touch-min)",
                      padding: "0 var(--space-3)",
                      borderRadius: "var(--radius-md)",
                      color: "var(--color-action-primary)",
                      // Current page is shown by weight and an underline, not colour alone.
                      fontWeight: current ? 700 : 400,
                      textDecoration: current ? "underline" : "none",
                    }}
                  >
                    {t(item.key)}
                  </Link>
                </li>
              );
            })}
            <li style={{ marginInlineStart: "auto" }}>
              <Button variant="ghost" label={t("guardian.shell.signOut")} onClick={() => void sessionStore.signOut()} />
            </li>
          </ul>
        </nav>
      </header>
      <main
        id="main"
        tabIndex={-1}
        style={{ flex: 1, padding: "var(--space-4)", display: "grid", gap: "var(--space-4)", alignContent: "start" }}
      >
        {children}
      </main>
    </div>
  );
}
