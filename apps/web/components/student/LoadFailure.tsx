"use client";
// One rendering of a failed load, so every student screen describes failure the same honest way
// (lib/student/journey.ts `classifyLoadError`): offline is calm and retryable, a lost session points
// to sign-in, anything else is an error with a retry. The retry sits outside the red banner so its
// text keeps the canvas contrast.
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import type { MessageKey } from "@/lib/i18n/messages";
import { useLocale } from "@/lib/i18n/useLocale";
import type { LoadFailure as Failure } from "@/lib/student/journey";

import { EmptyState, ErrorBanner } from "./ui";

export function LoadFailure({
  failure,
  offlineTitle,
  offlineBody,
  errorMessage,
  onRetry,
}: {
  failure: Failure;
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
        <ButtonLink href="/signin" variant="brand" label={t("common.signInAgain")} />
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
