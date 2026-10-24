"use client";
// Progress — supportive learning statistics (never a rank or a score to beat). Before the first
// answered question the screen says there is no progress yet, rather than showing a grid of zeros
// and a "0%" accuracy the child has not earned.
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { LoadFailure } from "@/components/student/LoadFailure";
import { Card, EmptyState, Skeleton } from "@/components/student/ui";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { useLearner } from "@/lib/session/useLearner";
import { learningApi } from "@/lib/student/api";
import { classifyLoadError, type LoadFailure as Failure } from "@/lib/student/journey";
import type { ProgressView } from "@/lib/student/types";

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <Card>
      <div style={{ display: "grid", gap: "var(--space-1)", textAlign: "center" }}>
        <strong style={{ fontSize: "var(--font-size-body-min-urdu)" }}>{value}</strong>
        <span>{label}</span>
      </div>
    </Card>
  );
}

export default function ProgressPage() {
  const { studentRef: ref, band } = useLearner();
  const { t, formatNumber, formatPercent } = useLocale();
  const [progress, setProgress] = useState<ProgressView | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | Failure>("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setProgress(await learningApi.progress(ref));
      setStatus("ready");
    } catch (e) {
      setStatus(classifyLoadError(e));
    }
  }, [ref]);

  useEffect(() => {
    void load();
  }, [load]);

  const hasProgress = !!progress && progress.total_attempts > 0;

  return (
    <AppShell title={t("student.progress.title")} band={band}>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={4} label={t("common.loading")} /> : null}
        {status !== "loading" && status !== "ready" ? (
          <LoadFailure
            failure={status}
            offlineTitle="student.progress.offlineTitle"
            offlineBody="student.progress.offlineBody"
            errorMessage="student.progress.error"
            onRetry={() => void load()}
          />
        ) : null}

        {status === "ready" && !hasProgress ? (
          <EmptyState
            title={t("student.progress.emptyTitle")}
            body={t("student.progress.emptyBody")}
            action={<ButtonLink href="/student/today" variant="brand" label={t("common.goToToday")} />}
          />
        ) : null}

        {status === "ready" && progress && hasProgress ? (
          <section
            aria-label={t("student.progress.statsLabel")}
            style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-2)" }}
          >
            <StatTile label={t("student.progress.mastered")} value={formatNumber(progress.objectives_mastered)} />
            <StatTile label={t("student.progress.inProgress")} value={formatNumber(progress.objectives_in_progress)} />
            <StatTile label={t("student.progress.answered")} value={formatNumber(progress.total_attempts)} />
            <StatTile label={t("student.progress.accuracy")} value={formatPercent(progress.accuracy)} />
            <StatTile label={t("student.progress.reviews")} value={formatNumber(progress.reviews_scheduled)} />
            <StatTile label={t("student.progress.misconceptions")} value={formatNumber(progress.misconceptions_cleared)} />
          </section>
        ) : null}
      </div>

      <Card>
        <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
          <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("student.reportCards.title")}</h2>
          <p style={{ margin: 0 }}>{t("student.reportCards.linkIntro")}</p>
          <ButtonLink href="/student/report-cards" variant="primary" label={t("student.reportCards.link")} />
        </div>
      </Card>
    </AppShell>
  );
}
