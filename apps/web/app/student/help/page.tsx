"use client";
// "Tell a grown-up" — the child's safeguarding entry. Tap a picture, then Send: no typing needed
// (words are optional, behind their own button). The flow is lib/safeguarding/childFlow.ts.
//
// What this screen promises, and what it does not:
// - a trained person will read it — never how fast (the response time is FD-06, undecided);
// - nothing the child sent is shown back on this device (family devices are often shared);
// - offline, nothing is sent and nothing is stored, and the child is told so plainly — the offline
//   queue is deliberately not used, because it would sit on that shared device.
import { useEffect, useId, useReducer, useRef, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { Card, ErrorBanner } from "@/components/student/ui";
import { Button, buttonStyle } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { useLocale } from "@/lib/i18n/useLocale";
import { childConcernApi } from "@/lib/safeguarding/api";
import { CATEGORY_OPTIONS, categoryOption, MAX_TEXT } from "@/lib/safeguarding/categories";
import { childPayload, childReducer, failureOutcome, initialChildState } from "@/lib/safeguarding/childFlow";
import { readHelpContext, type ConcernContext } from "@/lib/safeguarding/context";
import { useLearner } from "@/lib/session/useLearner";

// Large, full-width targets: the child taps a picture with words, not a small control.
const bigButton = (variant: "ghost" | "brand", disabled = false) =>
  ({
    ...buttonStyle(variant, disabled),
    minHeight: "calc(var(--size-touch-min) * 1.5)",
    width: "100%",
    fontSize: "var(--font-size-body-min-urdu)",
    textAlign: "start",
  }) as const;

export default function TellAGrownUpPage() {
  const { band } = useLearner();
  const { t } = useLocale();
  const [state, dispatch] = useReducer(childReducer, initialChildState);
  const [context, setContext] = useState<ConcernContext>({ screen: "", lessonId: null });
  const headingRef = useRef<HTMLHeadingElement>(null);
  const wordsId = useId();
  const chooseId = useId();

  useEffect(() => {
    setContext(readHelpContext(window.location.search));
  }, []);

  // Move focus to the new step's heading so a screen-reader user hears where they are.
  useEffect(() => {
    if (state.step !== "choose") headingRef.current?.focus();
  }, [state.step]);

  async function send() {
    const payload = childPayload(state, context);
    if (!payload) return dispatch({ type: "send" });
    dispatch({ type: "send" });
    try {
      await childConcernApi.raise(payload);
      dispatch({ type: "sent" });
    } catch (error) {
      dispatch({ type: "failed", outcome: failureOutcome(error) });
    }
  }

  const chosen = state.category ? categoryOption(state.category) : null;

  return (
    <AppShell title={t("safeguarding.child.title")} band={band}>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {state.step === "choose" ? (
          <section aria-labelledby={chooseId} style={{ display: "grid", gap: "var(--space-3)" }}>
            <p style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("safeguarding.child.intro")}</p>
            <h2 id={chooseId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
              {t("safeguarding.child.chooseLabel")}
            </h2>
            <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)" }}>
              {CATEGORY_OPTIONS.map((option) => (
                <li key={option.value}>
                  <button
                    type="button"
                    style={bigButton("ghost")}
                    onClick={() => dispatch({ type: "choose", category: option.value })}
                  >
                    <span aria-hidden="true" style={{ fontSize: "28px" }}>
                      {option.symbol}
                    </span>
                    <span>{t(option.childKey)}</span>
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        {(state.step === "confirm" || state.step === "sending") && chosen ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-3)", justifyItems: "start" }}>
              <h2 ref={headingRef} tabIndex={-1} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                {t("safeguarding.child.chosen")}{" "}
                <span aria-hidden="true">{chosen.symbol}</span> {t(chosen.childKey)}
              </h2>
              {state.wordsOpen ? (
                <div style={{ display: "grid", gap: "var(--space-1)", width: "100%" }}>
                  <label htmlFor={wordsId} style={{ fontSize: "var(--font-size-body-min-urdu)" }}>
                    {t("safeguarding.child.wordsLabel")}
                  </label>
                  <span id={`${wordsId}-hint`}>{t("safeguarding.child.wordsHint", { max: MAX_TEXT })}</span>
                  <textarea
                    id={wordsId}
                    dir="auto"
                    rows={4}
                    value={state.text}
                    aria-describedby={`${wordsId}-hint${state.textTooLong ? ` ${wordsId}-error` : ""}`}
                    aria-invalid={state.textTooLong || undefined}
                    onChange={(e) => dispatch({ type: "setText", text: e.target.value })}
                    style={{
                      font: "inherit",
                      fontSize: "var(--font-size-body-min-urdu)",
                      padding: "var(--space-2)",
                      borderRadius: "var(--radius-md)",
                      border: "1px solid var(--color-focus-ring)",
                      background: "var(--color-bg-canvas)",
                      color: "var(--color-text-primary)",
                      width: "100%",
                      boxSizing: "border-box",
                    }}
                  />
                  {state.textTooLong ? (
                    <span id={`${wordsId}-error`} role="alert" style={{ color: "var(--color-danger)" }}>
                      {t("safeguarding.child.tooLong")}
                    </span>
                  ) : null}
                </div>
              ) : (
                <Button
                  variant="ghost"
                  icon={<span aria-hidden="true">✏️</span>}
                  label={t("safeguarding.child.addWords")}
                  onClick={() => dispatch({ type: "openWords" })}
                />
              )}
              <button
                type="button"
                style={{ ...bigButton("brand", state.step === "sending"), justifyContent: "center" }}
                disabled={state.step === "sending"}
                aria-busy={state.step === "sending"}
                onClick={() => void send()}
              >
                <span aria-hidden="true">📨</span>
                <span>{state.step === "sending" ? t("safeguarding.child.sending") : t("safeguarding.child.send")}</span>
              </button>
              <Button
                variant="ghost"
                label={t("safeguarding.child.chooseAgain")}
                disabled={state.step === "sending"}
                onClick={() => dispatch({ type: "back" })}
              />
            </div>
          </Card>
        ) : null}

        {state.step === "sent" ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-3)", justifyItems: "start" }}>
              <h2 ref={headingRef} tabIndex={-1} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                <span aria-hidden="true">💚 </span>
                {t("safeguarding.child.sentTitle")}
              </h2>
              <p style={{ margin: 0 }}>{t("safeguarding.child.sentBody")}</p>
              <p style={{ margin: 0, fontWeight: 700 }}>{t("safeguarding.child.sentNow")}</p>
              <p style={{ margin: 0 }}>{t("safeguarding.child.sentPrivacy")}</p>
              <ButtonLink href="/student/today" variant="brand" label={t("safeguarding.child.done")} />
            </div>
          </Card>
        ) : null}

        {state.step === "offline" || state.step === "busy" || state.step === "error" ? (
          <div style={{ display: "grid", gap: "var(--space-3)", justifyItems: "start" }}>
            <h2 ref={headingRef} tabIndex={-1} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
              {state.step === "offline" ? t("safeguarding.child.offlineTitle") : t("safeguarding.child.title")}
            </h2>
            <ErrorBanner
              message={
                state.step === "offline"
                  ? t("safeguarding.child.offlineBody")
                  : state.step === "busy"
                    ? t("safeguarding.child.busy")
                    : t("safeguarding.child.error")
              }
            />
            {state.step !== "busy" ? (
              <Button variant="brand" label={t("safeguarding.child.tryAgain")} onClick={() => dispatch({ type: "retry" })} />
            ) : null}
            <ButtonLink href="/student/today" variant="ghost" label={t("safeguarding.child.done")} />
          </div>
        ) : null}
      </div>
    </AppShell>
  );
}
