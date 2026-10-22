"use client";
// A failed load on a teacher screen. Offline is calm and retryable; a lost session points to the
// TEACHER sign-in; an inactive (locked/suspended) account says so plainly; and "not available"
// covers both 404 and 403 with one wording, so the screen never reveals whether a class exists.
import { EmptyState, ErrorBanner } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import type { TeacherFailure } from "@/lib/teacher/errors";

export function TeacherState({ failure, onRetry }: { failure: TeacherFailure; onRetry: () => void }) {
  const { t } = useLocale();
  switch (failure) {
    case "offline":
      return (
        <EmptyState
          title={t("teacher.state.offlineTitle")}
          body={t("teacher.state.offlineBody")}
          action={<Button variant="ghost" label={t("teacher.state.retry")} onClick={onRetry} />}
        />
      );
    case "signed-out":
      return (
        <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
          <ErrorBanner message={t("teacher.state.signedOut")} />
          <ButtonLink href="/teacher/signin" variant="brand" label={t("teacher.state.signInAgain")} />
        </div>
      );
    case "inactive":
      return <EmptyState title={t("teacher.state.inactiveTitle")} body={t("teacher.state.inactiveBody")} />;
    case "not-available":
      return (
        <EmptyState
          title={t("teacher.state.notAvailableTitle")}
          body={t("teacher.state.notAvailableBody")}
          action={<ButtonLink href="/teacher" variant="ghost" label={t("teacher.state.backToClasses")} />}
        />
      );
    default:
      return (
        <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
          <ErrorBanner message={t("teacher.state.error")} />
          <Button variant="ghost" label={t("teacher.state.retry")} onClick={onRetry} />
        </div>
      );
  }
}
