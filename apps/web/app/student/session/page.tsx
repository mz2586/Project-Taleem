"use client";
// Learning Session player — the AI teacher interaction. Drives the real /v1/learning session:
// start -> next(decision) -> teach -> present (one step at a time) -> ask (+ authored hints) ->
// answer (loop) -> end. The teaching rules live in `lib/student/lessonPlayer.ts`; what an end of
// session MEANS (a finished lesson, a break, or "nothing published yet") lives in
// `lib/student/journey.ts`. This page only renders approved server content and never constructs AI
// content.
//
// Two languages meet on this screen and are kept apart: the chrome (buttons, progress, messages) is
// in the interface locale; every piece of lesson content carries its own `lang`/`dir`, so an Urdu
// lesson stays right-to-left inside an English interface and vice versa.
import { useEffect, useId, useReducer, useRef, useState } from "react";

import { ReadAloud } from "@/components/student/ReadAloud";
import { Card, ErrorBanner, ProgressRing, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { contentAttrs, pickLocalized } from "@/lib/i18n/content";
import { speechLang } from "@/lib/student/speech";
import { useLocale } from "@/lib/i18n/useLocale";
import { useLearner } from "@/lib/session/useLearner";
import { aiTeacherApi, learningApi } from "@/lib/student/api";
import {
  classifyExplainError,
  EXPLAIN_FAILURE_COPY,
  explainAvailability,
  explainReducer,
  explanationView,
  initialExplainState,
  styleLabel,
  styleToRequest,
  type CapabilitiesWire,
  type ExplainContext,
  type ExplainState,
} from "@/lib/student/aiTeacher";
import { watchConnectivity } from "@/lib/offline";
import { formatList } from "@/lib/guardian/format";
import { helpHref } from "@/lib/safeguarding/context";
import {
  classifyLoadError,
  ENDING_COPY,
  INSTRUCTION_LOCALE_PREFERENCE,
  needsTodayToExplain,
  planOutcome,
  teachFailureEnding,
  type SessionEnding,
} from "@/lib/student/journey";
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
import type { TodayView } from "@/lib/student/types";

/**
 * "Explain it another way" — verified authored text shown like the lesson; an AI-written rephrase
 * (only ever present when the generative tier is on) shown in a separate, labelled block with its
 * notice always visible and announced with it. See lib/student/aiTeacher.ts.
 */
function ExplainPanel({
  state,
  onAgain,
  onClose,
  canAskAgain,
}: {
  state: ExplainState;
  onAgain: () => void;
  onClose: () => void;
  canAskAgain: boolean;
}) {
  const { t, locale } = useLocale();
  const noticeId = useId();
  if (state.status === "closed") return null;
  return (
    <section aria-label={t("student.aiTeacher.title")} style={{ display: "grid", gap: "var(--space-3)" }}>
      {state.status === "loading" ? <Skeleton lines={3} label={t("student.aiTeacher.loading")} /> : null}
      {state.status === "failed" ? <ErrorBanner message={t(EXPLAIN_FAILURE_COPY[state.error])} /> : null}
      {state.status === "shown" ? (
        <Card>
          <div style={{ display: "grid", gap: "var(--space-3)" }}>
            <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
              {t("student.aiTeacher.title")} · {t(styleLabel(state.view.style))}
            </h2>
            {state.view.utterances.map((u, i) => (
              <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                <p {...contentAttrs({ locale: u.locale, text: u.text })} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                  {u.text}
                </p>
                <ReadAloud label={t("student.aiTeacher.teacherAudio")} text={u.text} lang={speechLang(u.text, u.locale)} />
              </div>
            ))}
            {state.view.escalate ? <p style={{ margin: 0 }}>{t("student.aiTeacher.mentorSoon")}</p> : null}
          </div>
        </Card>
      ) : null}
      {state.status === "shown" && state.view.generated ? (
        // Visually and semantically separate from verified curriculum text: its own landmark, a
        // dashed frame, a visible "written by a computer" label, and the notice before the text
        // (also tied to it with aria-describedby). Generated text never renders without it.
        <aside
          aria-label={t("student.aiTeacher.generated.label")}
          style={{
            display: "grid",
            gap: "var(--space-2)",
            padding: "var(--space-4)",
            border: "2px dashed var(--color-action-primary)",
            borderRadius: "var(--radius-md)",
          }}
        >
          <strong style={{ color: "var(--color-action-primary)" }}>
            <span aria-hidden="true">✎ </span>
            {t("student.aiTeacher.generated.label")}
          </strong>
          <p id={noticeId} style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
            {t(state.view.generated.notice)}
          </p>
          <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
            <p
              {...contentAttrs({ locale: state.view.generated.locale, text: state.view.generated.text })}
              aria-describedby={noticeId}
              style={{ margin: 0, fontStyle: "italic" }}
            >
              {state.view.generated.text}
            </p>
            <ReadAloud
              label={t("student.aiTeacher.generated.audio")}
              text={state.view.generated.text}
              lang={speechLang(state.view.generated.text, state.view.generated.locale)}
            />
          </div>
          {state.view.generated.groundedOn.length > 0 ? (
            <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
              {t("student.aiTeacher.generated.basedOn", {
                list: formatList(state.view.generated.groundedOn.map((g) => t(g.key, g.params)), locale),
              })}
            </p>
          ) : null}
        </aside>
      ) : null}
      {state.status !== "loading" ? (
        <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
          {canAskAgain ? <Button variant="ghost" label={t("student.aiTeacher.explainAgain")} onClick={onAgain} /> : null}
          <Button variant="ghost" label={t("student.aiTeacher.close")} onClick={onClose} />
        </div>
      ) : null}
    </section>
  );
}

export default function SessionPage() {
  const { studentRef: ref, band } = useLearner();
  const { t, formatPercent } = useLocale();
  const started = useRef(false);
  const [state, dispatch] = useReducer(playerReducer, initialPlayerState);
  // How a session that ended without the normal celebration ended (null: still going, or finished).
  const [ending, setEnding] = useState<Exclude<SessionEnding, "finished"> | null>(null);
  const { phase, sessionId, objective, teach, step, itemIndex, hints, answer, mastery, summary } = state;
  // "Explain it another way": its own reducer, so the lesson player is unchanged.
  const [explain, dispatchExplain] = useReducer(explainReducer, initialExplainState);
  const [capabilities, setCapabilities] = useState<CapabilitiesWire | null>(null);
  const [online, setOnline] = useState(true);

  useEffect(() => watchConnectivity(setOnline), []);
  useEffect(() => {
    if (!ref) return;
    // Without an answer the server stays the gate; the feature is offered and :explain decides.
    aiTeacherApi.capabilities(ref).then(setCapabilities).catch(() => setCapabilities(null));
  }, [ref]);
  // A new objective starts the styles over; leaving the lesson or the feedback closes the panel.
  useEffect(() => {
    dispatchExplain({ type: "reset" });
  }, [objective]);
  useEffect(() => {
    if (phase !== "presenting" && phase !== "feedback") dispatchExplain({ type: "close" });
  }, [phase]);

  // Only a network failure is "offline". A 401 that survives the session refresh has already cleared
  // the session (the route guard redirects to sign-in); calling it "offline" sent children to look
  // for wifi.
  const fail = (e: unknown) => dispatch({ type: "failed", offline: classifyLoadError(e) === "offline" });

  const finish = async (id: string, how: SessionEnding) => {
    if (how === "finished") {
      dispatch({ type: "completed", summary: await learningApi.end(id) });
      return;
    }
    setEnding(how);
    // Close the session server-side; best effort, because the child's screen is already honest.
    void learningApi.end(id).catch(() => undefined);
  };

  const plan = async (id: string) => {
    dispatch({ type: "planning" });
    try {
      const decision = await learningApi.next(id);
      // `teach` is set once any lesson has been presented in this session.
      const taughtThisSession = state.teach !== null;
      let today: TodayView | null = null;
      if (needsTodayToExplain(decision, taughtThisSession)) {
        today = await learningApi.today(ref).catch(() => null);
      }
      const outcome = planOutcome(decision, { taughtThisSession, today });
      if (outcome.kind === "escalate") return dispatch({ type: "escalated" });
      if (outcome.kind === "teach") {
        try {
          const lesson = await learningApi.teach(id, outcome.objective);
          dispatch({ type: "taught", objective: outcome.objective, teach: lesson });
        } catch (e) {
          const missing = teachFailureEnding(e);
          if (!missing) throw e;
          await finish(id, missing);
        }
        return;
      }
      await finish(id, outcome.ending);
    } catch (e) {
      fail(e);
    }
  };

  useEffect(() => {
    // Start only once the signed-in learner is known; never ask the server for an empty ref.
    if (started.current || !ref) return;
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
  }, [ref]);

  const steps = presentationSteps(state);
  const item = currentItem(state);
  const prompt = item ? pickLocalized(item.prompt, INSTRUCTION_LOCALE_PREFERENCE) : null;
  // The lesson's content language, as declared by its first item. Untagged lesson text (steps,
  // hints) is read in it only when the text's script agrees — see `speechLang`.
  const lessonLocale = teach?.items[0] ? (pickLocalized(teach.items[0].prompt, INSTRUCTION_LOCALE_PREFERENCE)?.locale ?? null) : null;

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

  const availability = explainAvailability(capabilities, online);

  const requestExplain = async (context: ExplainContext) => {
    if (!availability.available || !objective) return;
    const style = styleToRequest(explain, availability.styles);
    dispatchExplain({ type: "request", context });
    try {
      const wire = await aiTeacherApi.explain(sessionId, {
        objective_code: objective,
        ...(style ? { style } : {}),
        grade_band: band,
        // The lesson's content language, never the interface language.
        ...(lessonLocale ? { locale: lessonLocale } : {}),
      });
      dispatchExplain({ type: "loaded", view: explanationView(wire) });
    } catch (e) {
      dispatchExplain({ type: "failed", error: classifyExplainError(e) });
    }
  };

  const explainControls = (context: ExplainContext) => {
    if (explain.status !== "closed" && explain.context === context) {
      return (
        <ExplainPanel
          state={explain}
          canAskAgain={availability.available}
          onAgain={() => void requestExplain(context)}
          onClose={() => dispatchExplain({ type: "close" })}
        />
      );
    }
    if (!availability.available) {
      return availability.reason === "offline" ? <p style={{ margin: 0 }}>{t("student.aiTeacher.offline")}</p> : null;
    }
    return (
      <div>
        <Button
          variant="ghost"
          label={t("student.aiTeacher.explainAnother")}
          icon={<span aria-hidden="true">💬</span>}
          onClick={() => void requestExplain(context)}
        />
      </div>
    );
  };

  const onContinue = () => {
    const next = continueAfterFeedback(state);
    if (next === "plan") void plan(sessionId);
    else dispatch({ type: next });
  };

  const showEnding = ending !== null && phase !== "offline" && phase !== "error" && phase !== "escalated";

  return (
    <div style={{ maxWidth: 640, margin: "0 auto", minHeight: "100vh", padding: "var(--space-4)", display: "grid", gap: "var(--space-4)", alignContent: "start" }}>
      <h1 className="visually-hidden">{t("student.session.title")}</h1>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: "var(--space-2)" }}>
        <ButtonLink href="/student/today" variant="ghost" label={t("student.session.pause")} icon={<span aria-hidden="true">⏸</span>} />
        <ProgressRing value={mastery} label={t("common.mastery.label")} formatPercent={formatPercent} />
        <Button variant="ghost" label={t("student.session.help")} icon={<span aria-hidden="true">✋</span>} onClick={() => dispatch({ type: "escalated" })} />
      </header>

      <main aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {phase === "starting" && !showEnding ? <Skeleton lines={5} label={t("student.session.preparing")} /> : null}

        {phase === "offline" ? (
          <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
            <ErrorBanner message={t("student.session.offline")} />
            <ButtonLink href="/student/today" variant="ghost" label={t("common.goToToday")} />
          </div>
        ) : null}
        {phase === "error" ? (
          <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
            <ErrorBanner message={t("student.session.error")} />
            <ButtonLink href="/student/today" variant="ghost" label={t("common.backToToday")} />
          </div>
        ) : null}

        {phase === "escalated" ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
              <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("student.session.escalatedTitle")}</h2>
              <p style={{ margin: 0 }}>{t("student.session.escalatedBody")}</p>
              <ButtonLink href="/student/today" variant="brand" label={t("common.backToToday")} />
              {/* Help here means "stuck on the lesson". Something wrong or upsetting goes to a person. */}
              <p style={{ margin: 0 }}>{t("safeguarding.child.somethingElse")}</p>
              <ButtonLink
                href={helpHref("/student/session")}
                variant="ghost"
                icon={<span aria-hidden="true">🙋</span>}
                label={t("safeguarding.entry.label")}
              />
            </div>
          </Card>
        ) : null}

        {showEnding && ending ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)", textAlign: "center", justifyItems: "center" }}>
              <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t(ENDING_COPY[ending].title)}</h2>
              <p style={{ margin: 0 }}>{t(ENDING_COPY[ending].body)}</p>
              <ButtonLink href="/student/today" variant="brand" label={t("common.backToToday")} />
            </div>
          </Card>
        ) : null}

        {phase === "presenting" && steps[step] ? (
          <section aria-label={t("student.session.lessonLabel")} style={{ display: "grid", gap: "var(--space-3)" }}>
            <p style={{ margin: 0 }}>{t("student.session.stepOf", { current: step + 1, total: steps.length })}</p>
            <Card>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                {step === 0 ? (
                  <h2 {...contentAttrs({ text: steps[step].text })} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                    {steps[step].text}
                  </h2>
                ) : (
                  <p {...contentAttrs({ text: steps[step].text })} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                    {steps[step].text}
                  </p>
                )}
                <ReadAloud
                  label={t("student.session.teacherAudio")}
                  text={steps[step].text}
                  lang={speechLang(steps[step].text, null, lessonLocale)}
                />
              </div>
            </Card>
            <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "space-between" }}>
              <Button variant="ghost" label={t("common.back")} disabled={step === 0} onClick={() => dispatch({ type: "previousStep" })} />
              {isLastStep(state) ? (
                <Button variant="brand" label={t("student.session.ready")} onClick={onReady} />
              ) : (
                <Button variant="brand" label={t("common.next")} onClick={() => dispatch({ type: "nextStep" })} />
              )}
            </div>
            {explainControls("presenting")}
          </section>
        ) : null}

        {(phase === "asking" || phase === "feedback") && item && teach ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-3)" }}>
              <p style={{ margin: 0 }}>{t("student.session.questionOf", { current: itemIndex + 1, total: teach.items.length })}</p>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                <p {...contentAttrs({ locale: prompt?.locale, text: prompt?.text })} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                  {prompt?.text ?? ""}
                </p>
                <ReadAloud label={t("student.session.questionAudio")} text={prompt?.text} lang={prompt?.locale} />
              </div>
              <div role="group" aria-label={t("student.session.answers")} style={{ display: "grid", gap: "var(--space-2)" }}>
                {item.options.map((opt, i) => (
                  <Button
                    key={i}
                    variant="primary"
                    label={opt}
                    {...contentAttrs({ text: opt })}
                    disabled={phase === "feedback"}
                    onClick={() => void submit(i)}
                  />
                ))}
              </div>
              {hints.length > 0 ? (
                <ol aria-label={t("student.session.hints")} style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
                  {hints.map((h, i) => (
                    <li key={i} style={{ display: "flex", gap: "var(--space-2)", alignItems: "start", justifyContent: "space-between" }}>
                      <span>
                        <span aria-hidden="true">💡 </span>
                        <span {...contentAttrs({ text: h })}>{h}</span>
                      </span>
                      <ReadAloud label={t("student.session.hintAudio")} text={h} lang={speechLang(h, null, lessonLocale)} />
                    </li>
                  ))}
                </ol>
              ) : null}
              {canRequestHint(state) ? (
                <Button
                  variant="ghost"
                  label={hints.length === 0 ? t("student.session.hint") : t("student.session.anotherHint")}
                  onClick={() => void requestHint()}
                />
              ) : null}
            </div>
          </Card>
        ) : null}

        {phase === "feedback" && answer ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
              <strong style={{ color: answer.outcome === "correct" ? "var(--color-brand)" : "var(--color-text-primary)" }}>
                {answer.outcome === "correct" ? t("student.session.correct") : t("student.session.notYet")}
              </strong>
              {answer.feedback.map((f, i) => (
                <p key={i} {...contentAttrs({ text: f })} style={{ margin: 0 }}>
                  {f}
                </p>
              ))}
              <Button
                variant="brand"
                label={answer.outcome === "correct" ? t("common.continue") : t("common.tryAgain")}
                onClick={onContinue}
              />
            </div>
          </Card>
        ) : null}

        {phase === "feedback" && answer && answer.outcome !== "correct" ? explainControls("feedback") : null}

        {phase === "complete" ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)", textAlign: "center", justifyItems: "center" }}>
              <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t(ENDING_COPY.finished.title)}</h2>
              <p style={{ margin: 0 }}>{t(ENDING_COPY.finished.body, { count: summary?.interactions ?? 0 })}</p>
              <ButtonLink href="/student/today" variant="brand" label={t("common.backToToday")} />
            </div>
          </Card>
        ) : null}
      </main>
    </div>
  );
}
