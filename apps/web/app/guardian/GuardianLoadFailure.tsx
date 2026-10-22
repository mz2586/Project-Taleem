"use client";
// A failed load on a guardian screen, described the same honest way as the student screens
// (offline is calm and retryable; a lost session points to the GUARDIAN sign-in; anything else is an
// error with a retry). The retry sits outside the red banner so its text keeps canvas contrast.
import { EmptyState, ErrorBanner } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import type { LoadFailure } from "@/lib/student/journey";

export function GuardianLoadFailure({
  failure,
  offlineTitle,
  offlineBody,
  errorMessage,
  onRetry,
}: {
  failure: LoadFailure;
  offlineTitle: MessageKey;
  offlineBody: MessageKey;
  errorMessage: MessageKey;
  onRetry: () => void;
}) {
  const { t } = useLocale();
  if (failure === "offline") {
    return (
      <EmptyState
        title={t(offlineTitle)}
        body={t(offlineBody)}
        action={<Button variant="ghost" label={t("common.tryAgain")} onClick={onRetry} />}
      />
    );
  }
  if (failure === "signed-out") {
    return (
      <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
        <ErrorBanner message={t("common.signedOut")} />
        <ButtonLink href="/guardian/signin" variant="brand" label={t("common.signInAgain")} />
      </div>
    );
  }
  return (
    <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
      <ErrorBanner message={t(errorMessage)} />
      <Button variant="ghost" label={t("common.retry")} onClick={onRetry} />
    </div>
  );
}
