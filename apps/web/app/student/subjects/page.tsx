"use client";
// Subjects (Learn) — browse subjects & topics. Scaffolded here; the full subject browser depends on
// the eligibility + curriculum-read endpoints (STUDENT_API_REQUIREMENTS §2.4/§2.6, not yet built).
import { AppShell } from "@/components/student/AppShell";
import { EmptyState } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { useLearner } from "@/lib/session/useLearner";

export default function SubjectsPage() {
  const { band } = useLearner();
  const { t } = useLocale();
  return (
    <AppShell title={t("student.subjects.title")} band={band}>
      <EmptyState
        title={t("student.subjects.emptyTitle")}
        body={t("student.subjects.emptyBody")}
        action={<ButtonLink href="/student/today" variant="brand" label={t("common.goToToday")} />}
      />
      <section style={{ display: "grid", gap: "var(--space-1)", justifyItems: "center", textAlign: "center" }}>
        <p style={{ margin: 0 }}>{t("student.offline.entryBody")}</p>
        <ButtonLink href="/student/offline" variant="ghost" label={t("student.offline.entry")} icon={<span aria-hidden="true">📥</span>} />
      </section>
    </AppShell>
  );
}
