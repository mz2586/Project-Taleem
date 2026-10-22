"use client";
// Homework — an honest empty state. `GET /students/{ref}/homework` exists, but nothing assigns
// homework yet (no teacher assignment flow, and no published lessons), so there is nothing to list;
// the screen says so and routes back to guided learning rather than rendering an empty list.
import { AppShell } from "@/components/student/AppShell";
import { EmptyState } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { useLearner } from "@/lib/session/useLearner";

export default function HomeworkPage() {
  const { band } = useLearner();
  const { t } = useLocale();
  return (
    <AppShell title={t("student.homework.title")} band={band}>
      <EmptyState
        title={t("student.homework.emptyTitle")}
        body={t("student.homework.emptyBody")}
        action={<ButtonLink href="/student/today" variant="brand" label={t("common.goToToday")} />}
      />
    </AppShell>
  );
}
