"use client";
// Learning Session player — the AI teacher interaction. Drives the real /v1/learning session:
// start -> next(decision) -> teach -> present (one step at a time) -> ask (+ authored hints) ->
// answer (loop) -> end. The teaching rules live in `lib/student/lessonPlayer.ts`; this page only
// renders approved server content (utterances/items/hints) and never constructs AI content.
import Link from "next/link";
import { useEffect, useReducer, useRef } from "react";

import { ReadAloud } from "@/components/student/ReadAloud";
import { Card, ErrorBanner, ProgressRing, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { learningApi } from "@/lib/student/api";
import {
  canRequestHint,
  continueAfterFeedback,
  currentItem,
  hintsUsed,
  initialPlayerState,
  isLastStep,
  nextHintLevel,
  playerReducer,
  presentationSteps,
} from "@/lib/student/lessonPlayer";
import { useLearner } from "@/lib/session/useLearner";
import { ApiError } from "@/lib/student/types";

const TEACHABLE = new Set(["teach", "continue", "review", "remediate", "diagnose"]);

function loc(text: Record<string, string>): string {
  return text["ur"] ?? text["en"] ?? "";
}

export default function SessionPage() {
  const { studentRef: ref } = useLearner();
  const started = useRef(false);
  const [state, dispatch] = useReducer(playerReducer, initialPlayerState);
  const { phase, sessionId, objective, teach, step, itemIndex, hints, answer, mastery, summary } = state;

  const fail = (e: unknown) =>
    dispatch({ type: "failed", offline: e instanceof ApiError && (e.status === 0 || e.isAuth) });

  const plan = async (id: string) => {
    dispatch({ type: "planning" });
    try {
      const decision = await learningApi.next(id);
      if (decision.decision === "escalate") return dispatch({ type: "escalated" });
      if (TEACHABLE.has(decision.decision) && decision.objective_code) {
        const t = await learningApi.teach(id, decision.objective_code);
        dispatch({ type: "taught", objective: decision.objective_code, teach: t });
        return;
      }
      dispatch({ type: "completed", summary: await learningApi.end(id) });
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
        dispatch({ type: "started", sessionId: s.session_id });
        await plan(s.session_id);
      } catch (e) {
        fail(e);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const steps = presentationSteps(state);
  const item = currentItem(state);

  const onReady = () => {
    if (item) dispatch({ type: "ready" });
    else void plan(sessionId); // a lesson with no practice items: move on
  };

  const requestHint = async () => {
    if (!item) return;
    try {
      const h = await learningApi.hint(sessionId, {
        objective_code: objective,
        item_ref: item.item_ref,
        hint_level: nextHintLevel(state),
      });
      dispatch({ type: "hint", hint: h.hint, exhausted: h.exhausted });
    } catch (e) {
      fail(e);
    }
  };

  const submit = async (option: number) => {
    if (!item) return;
    try {
      const a = await learningApi.answer(sessionId, {
        objective_code: objective,
        item_ref: item.item_ref,
        option,
        hints_used: hintsUsed(state),
      });
      dispatch({ type: "answered", answer: a });
    } catch (e) {
      fail(e);
    }
  };

  const onContinue = () => {
    const next = continueAfterFeedback(state);
    if (next === "plan") void plan(sessionId);
    else dispatch({ type: next });
  };

  return (
    <div style={{ maxWidth: 640, margin: "0 auto", minHeight: "100vh", padding: "var(--space-4)", display: "grid", gap: "var(--space-4)", alignContent: "start" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <Link href="/student/today" style={{ color: "var(--color-action-primary)" }}>
          ‹ Pause
        </Link>
        <ProgressRing value={mastery} label="Mastery" />
        <Button variant="ghost" label="Help" icon={<span aria-hidden="true">✋</span>} onClick={() => dispatch({ type: "escalated" })} />
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

        {phase === "presenting" && steps[step] ? (
          <section aria-label="Lesson" style={{ display: "grid", gap: "var(--space-3)" }}>
            <p style={{ margin: 0 }}>
              Step {step + 1} of {steps.length}
            </p>
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                {step === 0 ? (
                  <h1 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{steps[step].text}</h1>
                ) : (
                  <p style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{steps[step].text}</p>
                )}
                <ReadAloud label="Teacher" />
              </div>
            </Card>
            <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "space-between" }}>
              <Button variant="ghost" label="Back" disabled={step === 0} onClick={() => dispatch({ type: "previousStep" })} />
              {isLastStep(state) ? (
                <Button variant="brand" label="I'm ready" onClick={onReady} />
              ) : (
                <Button variant="brand" label="Next" onClick={() => dispatch({ type: "nextStep" })} />
              )}
            </div>
          </section>
        ) : null}

        {(phase === "asking" || phase === "feedback") && item && teach ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-3)" }}>
              <p style={{ margin: 0 }}>
                Question {itemIndex + 1} of {teach.items.length}
              </p>
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
              {hints.length > 0 ? (
                <ol aria-label="Hints" style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
                  {hints.map((h, i) => (
                    <li key={i}>💡 {h}</li>
                  ))}
                </ol>
              ) : null}
              {canRequestHint(state) ? (
                <Button variant="ghost" label={hints.length === 0 ? "Give me a hint" : "Another hint"} onClick={() => void requestHint()} />
              ) : null}
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
                onClick={onContinue}
              />
            </div>
          </Card>
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
