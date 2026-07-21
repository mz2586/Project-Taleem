"use client";
// Progress — supportive learning statistics (never a rank or a score to beat).
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { Card, EmptyState, ErrorBanner, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { learningApi } from "@/lib/student/api";
import { DEV_LEARNER } from "@/lib/student/config";
import { ApiError, type ProgressView } from "@/lib/student/types";

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
  const ref = DEV_LEARNER.student_ref;
  const [progress, setProgress] = useState<ProgressView | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "offline" | "error">("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setProgress(await learningApi.progress(ref));
      setStatus("ready");
    } catch (e) {
      setStatus(e instanceof ApiError && (e.status === 0 || e.isAuth) ? "offline" : "error");
    }
  }, [ref]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <AppShell title="Progress" band={DEV_LEARNER.grade_band}>
      {status === "loading" ? <Skeleton lines={4} /> : null}
      {status === "offline" ? (
        <EmptyState title="Offline" body="Your saved progress will show when you&apos;re online." action={<Button variant="ghost" label="Try again" onClick={() => void load()} />} />
      ) : null}
      {status === "error" ? (
        <ErrorBanner message="Couldn&apos;t load progress." action={<Button variant="ghost" label="Retry" onClick={() => void load()} />} />
      ) : null}

      {status === "ready" && progress ? (
        <section aria-label="Your statistics" style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-2)" }}>
          <StatTile label="Ideas mastered" value={String(progress.objectives_mastered)} />
          <StatTile label="Ideas in progress" value={String(progress.objectives_in_progress)} />
          <StatTile label="Questions answered" value={String(progress.total_attempts)} />
          <StatTile label="Accuracy" value={`${Math.round(progress.accuracy * 100)}%`} />
          <StatTile label="Reviews scheduled" value={String(progress.reviews_scheduled)} />
          <StatTile label="Misconceptions cleared" value={String(progress.misconceptions_cleared)} />
        </section>
      ) : null}
    </AppShell>
  );
}
