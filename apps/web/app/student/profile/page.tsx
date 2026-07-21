"use client";
// Profile — the learner's own view: mastery map (state via label+shape, never colour-only) + a
// plain-language summary. IDOR-guarded server-side: a learner sees only their own data.
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { Card, EmptyState, ErrorBanner, Skeleton, StateBadge } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { learningApi } from "@/lib/student/api";
import { DEV_LEARNER } from "@/lib/student/config";
import { ApiError, type KnowledgeView } from "@/lib/student/types";

export default function ProfilePage() {
  const ref = DEV_LEARNER.student_ref;
  const [knowledge, setKnowledge] = useState<KnowledgeView | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "offline" | "error">("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      setKnowledge(await learningApi.knowledge(ref));
      setStatus("ready");
    } catch (e) {
      setStatus(e instanceof ApiError && (e.status === 0 || e.isAuth) ? "offline" : "error");
    }
  }, [ref]);

  useEffect(() => {
    void load();
  }, [load]);

  const objectives = knowledge ? Object.entries(knowledge.objectives) : [];
  const mastered = objectives.filter(([, o]) => o.state === "mastered").length;

  return (
    <AppShell title="My Profile" band={DEV_LEARNER.grade_band}>
      <section style={{ display: "grid", gap: "var(--space-1)" }}>
        <h2 style={{ margin: 0 }}>{DEV_LEARNER.display_name}</h2>
        <span>Grade band: {DEV_LEARNER.grade_band}</span>
      </section>

      {status === "loading" ? <Skeleton lines={5} /> : null}
      {status === "offline" ? (
        <EmptyState title="Offline" body="Your saved map will show when you&apos;re back online." action={<Button variant="ghost" label="Try again" onClick={() => void load()} />} />
      ) : null}
      {status === "error" ? (
        <ErrorBanner message="Couldn&apos;t load your map." action={<Button variant="ghost" label="Retry" onClick={() => void load()} />} />
      ) : null}

      {status === "ready" ? (
        <>
          <p style={{ margin: 0 }}>
            You&apos;ve mastered <strong>{mastered}</strong> of {objectives.length} ideas so far. Keep going!
          </p>
          <section aria-label="Mastery map" style={{ display: "grid", gap: "var(--space-2)" }}>
            {objectives.length === 0 ? (
              <EmptyState title="Your map will fill as you learn" body="Start a lesson from Today to add your first idea." />
            ) : (
              objectives.map(([code, o]) => (
                <Card key={code}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)" }}>
                    <span>{code}</span>
                    <StateBadge state={o.state} />
                  </div>
                </Card>
              ))
            )}
          </section>
        </>
      ) : null}
    </AppShell>
  );
}
