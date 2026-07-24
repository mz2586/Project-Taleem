"use client";
// Guardian dashboard — one card per linked child: progress, streak, open interventions, and the
// offline-sync freshness. Loading / empty / error / retry states; optimistic refresh on demand.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/design-system/Button";
import { Card, EmptyState, ErrorBanner, ProgressRing, Skeleton } from "@/components/student/ui";
import { guardianApi } from "@/lib/guardian/api";
import { DEV_GUARDIAN_NAME } from "@/lib/guardian/config";
import type { ChildSummary, GuardianDashboard } from "@/lib/guardian/types";
import { ApiError } from "@/lib/student/types";

import { GuardianShell } from "./GuardianShell";

type Status = "loading" | "ready" | "offline" | "error";

function SyncPill({ stale }: { stale: boolean }) {
  return (
    <span
      style={{
        fontSize: "var(--font-size-body-min)",
        padding: "2px 8px",
        borderRadius: "var(--radius-md)",
        background: stale ? "var(--color-danger)" : "var(--color-surface-2, #eef)",
        color: stale ? "var(--color-on-danger)" : "var(--color-text-primary)",
      }}
    >
      {stale ? "Data may be out of date" : "Synced recently"}
    </span>
  );
}

function ChildCard({ child }: { child: ChildSummary }) {
  const total =
    child.progress.objectives_mastered + child.progress.objectives_in_progress || 1;
  const mastery = child.progress.objectives_mastered / total;
  return (
    <Card>
      <div style={{ display: "flex", alignItems: "center", gap: "var(--space-4)" }}>
        <ProgressRing value={mastery} label="Mastered" />
        <div style={{ display: "grid", gap: "var(--space-1)", flex: 1 }}>
          <strong>{child.student_ref}</strong>
          <span>
            {child.progress.objectives_mastered} mastered ·{" "}
            {child.progress.objectives_in_progress} in progress
          </span>
          <span>🔥 {child.streak.current}-day streak · 🏅 {child.achievements_count}</span>
          <SyncPill stale={child.sync_status.is_stale} />
          {child.open_interventions > 0 ? (
            <span role="status" style={{ color: "var(--color-danger)" }}>
              {child.open_interventions} thing(s) need attention
            </span>
          ) : null}
        </div>
      </div>
      <div style={{ marginTop: "var(--space-3)" }}>
        <Link href={`/guardian/children/${encodeURIComponent(child.student_ref)}`}>
          <Button label="View details" />
        </Link>
      </div>
    </Card>
  );
}

export default function GuardianDashboardPage() {
  const [data, setData] = useState<GuardianDashboard | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setData(await guardianApi.dashboard());
      setStatus("ready");
    } catch (e) {
      if (e instanceof ApiError && (e.status === 0 || e.isAuth)) setStatus("offline");
      else setStatus("error");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <GuardianShell title="Taleem — Guardian">
      <section>
        <h2 style={{ margin: 0 }}>السلام علیکم، {DEV_GUARDIAN_NAME}</h2>
        <p style={{ margin: 0 }}>Your children&apos;s learning at a glance.</p>
      </section>

      {status === "loading" ? <Skeleton lines={4} /> : null}

      {status === "offline" ? (
        <ErrorBanner
          message="You're offline or your session expired."
          action={<Button label="Try again" onClick={() => void load()} />}
        />
      ) : null}

      {status === "error" ? (
        <ErrorBanner
          message="Something went wrong loading the dashboard."
          action={<Button label="Retry" onClick={() => void load()} />}
        />
      ) : null}

      {status === "ready" && data && data.children.length === 0 ? (
        <EmptyState
          title="No children linked yet"
          body="When a child is linked to your account, their progress will appear here."
        />
      ) : null}

      {status === "ready" && data && data.children.length > 0 ? (
        <>
          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button label="Refresh" onClick={() => void load()} />
          </div>
          {data.children.map((child) => (
            <ChildCard key={child.student_ref} child={child} />
          ))}
        </>
      ) : null}
    </GuardianShell>
  );
}
