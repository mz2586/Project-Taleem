"use client";
// Guardian child detail — every WS1 section, read-only, aggregated server-side from existing learning
// read models. Loading / empty / error / retry states; sections degrade gracefully when empty.
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { Button } from "@/design-system/Button";
import { Card, EmptyState, ErrorBanner, Skeleton } from "@/components/student/ui";
import { guardianApi } from "@/lib/guardian/api";
import type { ChildOverview } from "@/lib/guardian/types";
import { ApiError } from "@/lib/student/types";

import { GuardianShell } from "../../GuardianShell";

type Status = "loading" | "ready" | "denied" | "offline" | "error";

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <Card>
      <h3 style={{ marginTop: 0 }}>{title}</h3>
      {children}
    </Card>
  );
}

function fmtDay(dayIndex: number | null): string {
  if (dayIndex === null) return "—";
  return new Date(dayIndex * 86_400_000).toISOString().slice(0, 10);
}

export default function GuardianChildPage() {
  const params = useParams<{ studentRef: string }>();
  const ref = decodeURIComponent(String(params.studentRef));
  const [data, setData] = useState<ChildOverview | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setData(await guardianApi.child(ref));
      setStatus("ready");
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) setStatus("denied");
      else if (e instanceof ApiError && (e.status === 0 || e.isAuth)) setStatus("offline");
      else setStatus("error");
    }
  }, [ref]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <GuardianShell title={`Child — ${ref}`} back={{ href: "/guardian", label: "Back to dashboard" }}>
      {status === "loading" ? <Skeleton lines={6} /> : null}

      {status === "denied" ? (
        <EmptyState
          title="Not available"
          body="You don't have access to this learner."
        />
      ) : null}

      {status === "offline" ? (
        <ErrorBanner
          message="You're offline or your session expired."
          action={<Button label="Try again" onClick={() => void load()} />}
        />
      ) : null}

      {status === "error" ? (
        <ErrorBanner
          message="Something went wrong."
          action={<Button label="Retry" onClick={() => void load()} />}
        />
      ) : null}

      {status === "ready" && data ? (
        <>
          <Section title="Progress overview">
            <p style={{ margin: 0 }}>
              {data.progress_overview.objectives_mastered} mastered ·{" "}
              {data.progress_overview.objectives_in_progress} in progress ·{" "}
              {Math.round(data.progress_overview.accuracy * 100)}% accuracy ·{" "}
              {data.progress_overview.total_attempts} attempts
            </p>
          </Section>

          <Section title="Offline sync status">
            <p style={{ margin: 0 }}>
              {data.offline_sync_status.is_stale
                ? "Data may be out of date — the device hasn't synced recently."
                : "Synced recently."}{" "}
              Last sync: {fmtDay(data.offline_sync_status.last_synced_at
                ? Math.floor(data.offline_sync_status.last_synced_at / 86_400)
                : null)}
              . Unsynced work on the device is shown when the child reconnects.
            </p>
          </Section>

          <Section title="Learning streak & attendance">
            <p style={{ margin: 0 }}>
              🔥 Current streak {data.learning_streaks.current} day(s); longest{" "}
              {data.learning_streaks.longest}. Active on {data.attendance.active_days} day(s).
            </p>
          </Section>

          <Section title="This week">
            <p style={{ margin: 0 }}>
              {data.weekly_summary.sessions} session(s), {data.weekly_summary.attempts} attempt(s),{" "}
              {Math.round(data.weekly_summary.accuracy * 100)}% accuracy.
            </p>
          </Section>

          <Section title="Knowledge growth">
            {Object.keys(data.knowledge_growth).length === 0 ? (
              <p style={{ margin: 0 }}>No mastery data yet.</p>
            ) : (
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                {Object.entries(data.knowledge_growth).map(([obj, m]) => (
                  <li key={obj}>
                    {obj}: {Math.round(m * 100)}%
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Things that need attention">
            {data.intervention_notifications.length === 0 ? (
              <p style={{ margin: 0 }}>Nothing right now — great!</p>
            ) : (
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                {data.intervention_notifications.map((n) => (
                  <li key={n.id}>{n.message}</li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Recommendations (from the AI Teacher)">
            {data.recommendations.length === 0 ? (
              <p style={{ margin: 0 }}>No recommendations right now.</p>
            ) : (
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                {data.recommendations.map((r) => (
                  <li key={r.objective_code}>
                    {r.objective_code} — {r.reason}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Learning timeline">
            {data.learning_timeline.length === 0 ? (
              <p style={{ margin: 0 }}>No sessions yet.</p>
            ) : (
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                {data.learning_timeline.map((s) => (
                  <li key={s.session_id}>
                    {fmtDay(Math.floor(s.at / 86_400))}: {s.attempts} attempt(s), {s.correct}{" "}
                    correct ({s.objectives.length} objective(s))
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <Section title="Achievements">
            {data.achievement_history.length === 0 ? (
              <p style={{ margin: 0 }}>No achievements earned yet.</p>
            ) : (
              <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                {data.achievement_history.map((a) => (
                  <li key={a.id}>
                    🏅 {a.name} — {a.description}
                  </li>
                ))}
              </ul>
            )}
          </Section>

          <div style={{ display: "flex", justifyContent: "flex-end" }}>
            <Button label="Refresh" onClick={() => void load()} />
          </div>
        </>
      ) : null}
    </GuardianShell>
  );
}
