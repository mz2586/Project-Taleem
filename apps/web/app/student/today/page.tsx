"use client";
// Dashboard "Today" — answers "what should I do now?" with one clear action, plus encouraging
// progress. Governance-safe: reads the synthetic learner's progress/knowledge from /v1/learning.
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { ReadAloud } from "@/components/student/ReadAloud";
import { Card, EmptyState, ErrorBanner, ProgressRing, Skeleton, StateBadge } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { learningApi } from "@/lib/student/api";
import { DEV_LEARNER } from "@/lib/student/config";
import { ApiError, type KnowledgeView, type ProgressView } from "@/lib/student/types";

const REVIEW_STATES = new Set(["needs_review", "at_risk"]);

export default function TodayPage() {
  const ref = DEV_LEARNER.student_ref;
  const [knowledge, setKnowledge] = useState<KnowledgeView | null>(null);
  const [progress, setProgress] = useState<ProgressView | null>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "offline" | "error">("loading");

  const load = useCallback(async () => {
    setStatus("loading");
    try {
      const [k, p] = await Promise.all([learningApi.knowledge(ref), learningApi.progress(ref)]);
      setKnowledge(k);
      setProgress(p);
      setStatus("ready");
    } catch (e) {
      if (e instanceof ApiError && (e.status === 0 || e.isAuth)) setStatus("offline");
      else setStatus("error");
    }
  }, [ref]);

  useEffect(() => {
    void load();
  }, [load]);

  const objectives = knowledge ? Object.entries(knowledge.objectives) : [];
  const total = objectives.length;
  const mastered = objectives.filter(([, o]) => o.state === "mastered").length;
  const dueCount = objectives.filter(([, o]) => REVIEW_STATES.has(o.state)).length;
  const masteryValue = total > 0 ? mastered / total : 0;

  return (
    <AppShell title="Taleem" band={DEV_LEARNER.grade_band}>
      <section style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: "var(--space-2)" }}>
        <div>
          <h2 style={{ margin: 0 }}>السلام علیکم، {DEV_LEARNER.display_name}</h2>
          <p style={{ margin: 0 }}>آئیے آج سیکھتے ہیں۔</p>
        </div>
        <ReadAloud label="Greeting" />
      </section>

      {/* The one clear action — largest, first-focus. */}
      <Card>
        <div style={{ display: "grid", gap: "var(--space-2)" }}>
          <strong style={{ fontSize: "var(--font-size-body-min-urdu)" }}>Start today&apos;s learning</strong>
          <p style={{ margin: 0 }}>Your AI teacher will pick the best next step for you.</p>
          <Link href="/student/session" style={{ textDecoration: "none" }}>
            <Button variant="brand" label="Start" icon={<span aria-hidden="true">▶</span>} />
          </Link>
        </div>
      </Card>

      {status === "loading" ? <Skeleton lines={4} /> : null}

      {status === "offline" ? (
        <EmptyState
          title="You&apos;re offline"
          body="We&apos;ll show your saved plan and sync when you&apos;re back online."
          action={<Button variant="ghost" label="Try again" onClick={() => void load()} />}
        />
      ) : null}

      {status === "error" ? (
        <ErrorBanner
          message="We couldn&apos;t load your progress. Let&apos;s try again."
          action={<Button variant="ghost" label="Retry" onClick={() => void load()} />}
        />
      ) : null}

      {status === "ready" ? (
        <>
          <section style={{ display: "flex", gap: "var(--space-4)", alignItems: "center", flexWrap: "wrap" }}>
            <ProgressRing value={masteryValue} label="Mastery" />
            <div style={{ display: "grid", gap: "var(--space-1)" }}>
              <span>
                <strong>{mastered}</strong> of {total} ideas mastered
              </span>
              <Link href="/student/session" style={{ color: "var(--color-action-primary)" }}>
                {dueCount > 0 ? `${dueCount} to review today →` : "No reviews due — great!"}
              </Link>
              {progress ? <span>Accuracy so far: {Math.round(progress.accuracy * 100)}%</span> : null}
            </div>
          </section>

          {total === 0 ? (
            <EmptyState
              title="Your journey starts here"
              body="Tap Start to begin your first lesson. Your progress map will fill as you learn."
            />
          ) : (
            <section aria-label="Your ideas" style={{ display: "grid", gap: "var(--space-2)" }}>
              {objectives.slice(0, 8).map(([code, o]) => (
                <Card key={code}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)" }}>
                    <span>{code}</span>
                    <StateBadge state={o.state} />
                  </div>
                </Card>
              ))}
            </section>
          )}
        </>
      ) : null}
    </AppShell>
  );
}
