"use client";
// "Ask your teacher" on the lesson screen. Rules live in lib/student/askTeacher.ts; this only
// renders. Answers are verbatim lesson text, so they are shown like the lesson (own lang/dir, read
// aloud). The holding message never shows lesson text and never repeats what the child wrote.
import Link from "next/link";
import { useId, useState } from "react";

import { ReadAloud } from "@/components/student/ReadAloud";
import { Card, ErrorBanner, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { contentAttrs } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import { helpHref } from "@/lib/safeguarding/context";
import {
  ASK_FAILURE_COPY,
  ASK_INTENT_LABEL,
  ASK_TAP_INTENTS,
  QUESTION_MAX_CHARS,
  questionToSend,
  type AskState,
  type AskTapIntent,
} from "@/lib/student/askTeacher";
import { speechLang } from "@/lib/student/speech";

export function AskTeacherPanel({
  state,
  online,
  lessonId,
  onOpen,
  onIntent,
  onQuestion,
  onClose,
}: {
  state: AskState;
  online: boolean;
  lessonId?: string | null;
  onOpen: () => void;
  onIntent: (intent: AskTapIntent) => void;
  onQuestion: (question: string) => void;
  onClose: () => void;
}) {
  const { t } = useLocale();
  const [draft, setDraft] = useState("");
  const inputId = useId();
  const hintId = useId();

  if (!online) return null; // Answers come from the server; offline the lesson itself still works.
  if (state.status === "closed") {
    return (
      <div>
        <Button variant="ghost" label={t("student.askTeacher.open")} icon={<span aria-hidden="true">❓</span>} onClick={onOpen} />
      </div>
    );
  }

  const busy = state.status === "loading";
  const toSend = questionToSend(draft);
  return (
    <section aria-label={t("student.askTeacher.title")} style={{ display: "grid", gap: "var(--space-3)" }}>
      <Card>
        <div style={{ display: "grid", gap: "var(--space-3)" }}>
          <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("student.askTeacher.title")}</h2>
          <p style={{ margin: 0 }}>{t("student.askTeacher.intro")}</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
            {ASK_TAP_INTENTS.map((intent) => (
              <Button key={intent} variant="ghost" label={t(ASK_INTENT_LABEL[intent])} disabled={busy} onClick={() => onIntent(intent)} />
            ))}
          </div>
          {state.freeText ? (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (toSend && !busy) {
                  onQuestion(toSend);
                  setDraft("");
                }
              }}
              style={{ display: "grid", gap: "var(--space-2)" }}
            >
              <label htmlFor={inputId}>{t("student.askTeacher.typeLabel")}</label>
              <input
                id={inputId}
                type="text"
                value={draft}
                maxLength={QUESTION_MAX_CHARS}
                autoComplete="off"
                aria-describedby={hintId}
                onChange={(e) => setDraft(e.target.value)}
                style={{ padding: "var(--space-2)", fontSize: "var(--font-size-body-min-urdu)" }}
              />
              <small id={hintId}>{t("student.askTeacher.typeHint", { max: QUESTION_MAX_CHARS })}</small>
              <div>
                <Button variant="brand" type="submit" label={t("student.askTeacher.send")} disabled={busy || !toSend} />
              </div>
            </form>
          ) : null}
        </div>
      </Card>

      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-3)" }}>
        {busy ? <Skeleton lines={2} label={t("student.askTeacher.loading")} /> : null}
        {state.status === "failed" ? <ErrorBanner message={t(ASK_FAILURE_COPY[state.error])} /> : null}
        {state.status === "loaded" ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-3)" }}>
              <p style={{ margin: 0, fontWeight: 600 }}>{t(state.view.message)}</p>
              {state.view.passages.map((p, i) => (
                <div key={i} style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                  <p {...contentAttrs({ locale: p.locale, text: p.text })} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                    {p.text}
                  </p>
                  <ReadAloud label={t("student.aiTeacher.teacherAudio")} text={p.text} lang={speechLang(p.text, p.locale)} />
                </div>
              ))}
              {state.view.outcome === "holding" ? (
                <div>
                  <Link href={helpHref("/student/session", lessonId)}>{t("student.askTeacher.getHelp")}</Link>
                </div>
              ) : null}
            </div>
          </Card>
        ) : null}
      </div>

      <div>
        <Button variant="ghost" label={t("student.aiTeacher.close")} onClick={onClose} />
      </div>
    </section>
  );
}
