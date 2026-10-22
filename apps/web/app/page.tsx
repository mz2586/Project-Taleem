"use client";
// Landing page. Replaces the M1 placeholder that said, in its own words, "Governance-safe
// scaffolding only".
//
// Two doors, and the child's is first. That ordering is the whole design: the person who opens this
// most often is a child on a shared phone, and they should not have to read past an adult's
// onboarding to reach their lesson. Nothing here needs a session; it is a client component only so
// the copy follows the person's interface locale. The server still renders a complete first paint in
// the deployment default locale, which is what a 2G connection deserves.

import Link from "next/link";

import { useLocale } from "@/lib/i18n/useLocale";

const linkCard = {
  display: "grid",
  gap: "var(--space-1)",
  padding: "var(--space-4)",
  borderRadius: "var(--radius-md)",
  textDecoration: "none",
  color: "var(--color-text-primary)",
  minHeight: "var(--size-touch-min)",
} as const;

export default function Home() {
  const { t } = useLocale();
  return (
    <main
      style={{
        maxWidth: 460,
        margin: "0 auto",
        padding: "var(--space-6) var(--space-4)",
        display: "grid",
        gap: "var(--space-6)",
        alignContent: "start",
        minHeight: "100vh",
      }}
    >
      <header style={{ display: "grid", gap: "var(--space-2)" }}>
        <h1 style={{ margin: 0, color: "var(--color-brand)", fontSize: "40px" }}>{t("common.appName")}</h1>
        <p style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("home.tagline")}</p>
      </header>

      <nav aria-label={t("home.entryLabel")} style={{ display: "grid", gap: "var(--space-3)" }}>
        <Link
          href="/signin"
          style={{
            ...linkCard,
            background: "var(--color-brand)",
            color: "var(--color-on-brand)",
          }}
        >
          <strong style={{ fontSize: "22px" }}>{t("home.studentTitle")}</strong>
          <span>{t("home.studentBody")}</span>
        </Link>

        <Link href="/guardian/signin" style={{ ...linkCard, border: "1px solid var(--color-focus-ring)" }}>
          <strong style={{ fontSize: "22px" }}>{t("home.guardianTitle")}</strong>
          <span>{t("home.guardianBody")}</span>
        </Link>

        <Link href="/join" style={{ ...linkCard, border: "1px solid var(--color-focus-ring)" }}>
          <strong style={{ fontSize: "22px" }}>{t("home.joinTitle")}</strong>
          <span>{t("home.joinBody")}</span>
        </Link>
      </nav>

      <section style={{ display: "grid", gap: "var(--space-3)" }}>
        <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("home.whatTitle")}</h2>
        <ul style={{ margin: 0, paddingInlineStart: "1.2em", display: "grid", gap: "var(--space-2)" }}>
          <li>{t("home.whatPoints.curriculum")}</li>
          <li>{t("home.whatPoints.pace")}</li>
          <li>{t("home.whatPoints.offline")}</li>
          <li>{t("home.whatPoints.guardians")}</li>
        </ul>
      </section>

      <section
        style={{
          border: "1px solid var(--color-focus-ring)",
          borderRadius: "var(--radius-md)",
          padding: "var(--space-4)",
          display: "grid",
          gap: "var(--space-2)",
        }}
      >
        <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("home.safetyTitle")}</h2>
        <p style={{ margin: 0 }}>{t("home.safetyBody")}</p>
      </section>
    </main>
  );
}
