"use client";
// Learning Session player — the AI teacher interaction. Drives the real /v1/learning session:
// start -> next(decision) -> teach -> answer(loop) -> end. Renders ONLY approved server content
// (utterances/items); it never constructs AI content. Governance-safe (synthetic learner).
import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { ReadAloud } from "@/components/student/ReadAloud";
import { Card, ErrorBanner, ProgressRing, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { learningApi } from "@/lib/student/api";
import { DEV_LEARNER } from "@/lib/student/config";
import {
  ApiError,
  type AnswerView,
  type ItemView,
  type SessionEndView,
  type TeachView,
  type Utterance,
} from "@/lib/student/types";

type Phase =
  | "starting"
  | "teaching"
  | "asking"
  | "feedback"
  | "complete"
  | "escalated"
  | "offline"
  | "error";

const TEACHABLE = new Set(["teach", "continue", "review", "remediate", "diagnose"]);

function loc(text: Record<string, string>): string {
  return text["ur"] ?? text["en"] ?? "";
}

export default function SessionPage() {
  const ref = DEV_LEARNER.student_ref;
  const started = useRef(false);
  const [phase, setPhase] = useState<Phase>("starting");
  const [sessionId, setSessionId] = useState<string>("");
  const [objective, setObjective] = useState<string>("");
  const [teach, setTeach] = useState<TeachView | null>(null);
  const [itemIndex, setItemIndex] = useState(0);
  const [answer, setAnswer] = useState<AnswerView | null>(null);
  const [summary, setSummary] = useState<SessionEndView | null>(null);
  const [mastery, setMastery] = useState(0);

  const fail = (e: unknown) => {
    if (e instanceof ApiError && (e.status === 0 || e.isAuth)) setPhase("offline");
    else setPhase("error");
  };

  const plan = async (id: string) => {
    try {
      const decision = await learningApi.next(id);
      if (decision.decision === "escalate") return setPhase("escalated");
      if (TEACHABLE.has(decision.decision) && decision.objective_code) {
        const t = await learningApi.teach(id, decision.objective_code);
        setObjective(decision.objective_code);
        setTeach(t);
        setItemIndex(0);
        setAnswer(null);
        setPhase("teaching");
        return;
      }
      const end = await learningApi.end(id);
      setSummary(end);
      setPhase("complete");
    } catch (e) {
      fail(e);
    }
  };

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void (async () => {
      try {
        const s = await learningApi.startSession(ref);
        setSessionId(s.session_id);
        await plan(s.session_id);
      } catch (e) {
        fail(e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const item: ItemView | undefined = teach?.items[itemIndex];

  const submit = async (option: number) => {
    if (!item) return;
    try {
      const a = await learningApi.answer(sessionId, {
        objective_code: objective,
        item_ref: item.item_ref,
        option,
      });
      setAnswer(a);
      setMastery(a.mastery);
      setPhase("feedback");
    } catch (e) {
      fail(e);
    }
  };

  const onContinue = async () => {
    if (!answer) return;
    if (answer.outcome !== "correct") {
      setPhase("asking"); // retry the same item (never reveal the answer)
      return;
    }
    const nextIndex = itemIndex + 1;
    if (teach && nextIndex < teach.items.length) {
      setItemIndex(nextIndex);
      setAnswer(null);
      setPhase("asking");
    } else {
      setPhase("starting");
      await plan(sessionId);
    }
  };

  return (
    <div style={{ maxWidth: 640, margin: "0 auto", minHeight: "100vh", padding: "var(--space-4)", display: "grid", gap: "var(--space-4)", alignContent: "start" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Link href="/student/today" style={{ color: "var(--color-action-primary)" }}>
          ‹ Pause
        </Link>
        <ProgressRing value={mastery} label="Mastery" />
        <Button variant="ghost" label="Help" icon={<span aria-hidden="true">✋</span>} onClick={() => setPhase("escalated")} />
      </header>

      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {phase === "starting" ? <Skeleton lines={5} /> : null}

        {phase === "offline" ? (
          <ErrorBanner message="You&apos;re offline. Your saved lessons are on the Today screen." action={<Link href="/student/today" style={{ color: "var(--color-on-danger)" }}>Go to Today</Link>} />
        ) : null}
        {phase === "error" ? (
          <ErrorBanner message="Something went wrong. Let&apos;s go back and try again." action={<Link href="/student/today" style={{ color: "var(--color-on-danger)" }}>Back</Link>} />
        ) : null}

        {phase === "escalated" ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)" }}>
              <strong>We&apos;re getting someone to help you.</strong>
              <p style={{ margin: 0 }}>It&apos;s okay to take a break. A mentor will check in with you.</p>
              <Link href="/student/today" style={{ textDecoration: "none" }}>
                <Button variant="brand" label="Back to Today" />
              </Link>
            </div>
          </Card>
        ) : null}

        {(phase === "teaching" || phase === "asking" || phase === "feedback") && teach ? (
          <>
            {phase === "teaching" ? (
              <section style={{ display: "grid", gap: "var(--space-3)" }}>
                {teach.utterances.map((u: Utterance, i) => (
                  <Card key={i}>
                    <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                      <p style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{u.text}</p>
                      <ReadAloud label="Teacher" />
                    </div>
                  </Card>
                ))}
                <Button variant="brand" label="I'm ready" onClick={() => setPhase("asking")} />
              </section>
            ) : null}

            {(phase === "asking" || phase === "feedback") && item ? (
              <Card>
                <div style={{ display: "grid", gap: "var(--space-3)" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                    <p style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{loc(item.prompt)}</p>
                    <ReadAloud label="Question" />
                  </div>
                  <div role="group" aria-label="Answers" style={{ display: "grid", gap: "var(--space-2)" }}>
                    {item.options.map((opt, i) => (
                      <Button
                        key={i}
                        variant="primary"
                        label={opt}
                        disabled={phase === "feedback"}
                        onClick={() => void submit(i)}
                      />
                    ))}
                  </div>
                </div>
              </Card>
            ) : null}

            {phase === "feedback" && answer ? (
              <Card>
                <div style={{ display: "grid", gap: "var(--space-2)" }}>
                  <strong style={{ color: answer.outcome === "correct" ? "var(--color-brand)" : "var(--color-text-primary)" }}>
                    {answer.outcome === "correct" ? "بہت خوب! ✓" : "آئیے دوبارہ سوچتے ہیں"}
                  </strong>
                  {answer.feedback.map((f, i) => (
                    <p key={i} style={{ margin: 0 }}>
                      {f}
                    </p>
                  ))}
                  <Button
                    variant="brand"
                    label={answer.outcome === "correct" ? "Continue" : "Try again"}
                    onClick={() => void onContinue()}
                  />
                </div>
              </Card>
            ) : null}
          </>
        ) : null}

        {phase === "complete" ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)", textAlign: "center" }}>
              <strong style={{ fontSize: "var(--font-size-body-min-urdu)" }}>You did great today! 🎉</strong>
              <p style={{ margin: 0 }}>
                You learned {summary?.interactions ?? 0} steps. We&apos;ll review this again in a few days.
              </p>
              <Link href="/student/today" style={{ textDecoration: "none" }}>
                <Button variant="brand" label="Back to Today" />
              </Link>
            </div>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
