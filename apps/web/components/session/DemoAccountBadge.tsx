"use client";
// "Demo account" badge for the learner and guardian shells (DEMO_COHORT_CONTRACT §2). Shown only
// when the signed-in session's access token carries `cohort: "demo"` — decoded client-side purely
// for display; the server decides what a demo account may see from the account, not the claim.
import { useLocale } from "@/lib/i18n/useLocale";
import type { Translator } from "@/lib/i18n/translate";
import { isDemoToken } from "@/lib/session/cohort";
import { useSession } from "@/lib/session/useSession";

/** The badge itself (pure; rendered to static markup in the unit suite). */
export function DemoAccountBadgeView({ t }: { t: Translator }) {
  return (
    <span
      data-demo-badge=""
      title={t("common.demoAccount.hint")}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "var(--space-1) var(--space-2)",
        borderRadius: "var(--radius-md)",
        border: "2px dashed var(--color-brand)",
        fontWeight: 700,
      }}
    >
      {t("common.demoAccount.label")}
    </span>
  );
}

export function DemoAccountBadge() {
  const { session } = useSession();
  const { t } = useLocale();
  if (!session || !isDemoToken(session.accessToken)) return null;
  return <DemoAccountBadgeView t={t} />;
}
