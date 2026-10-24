"use client";
// Offline lesson player — plays a lesson saved on this phone with no network: paced steps, the
// questions, and the package's authored hints. The package carries no answer key, so an answer is
// "saved on this phone" and graded by the server when it syncs — this screen never says right or
// wrong. Each answer is a durable queued sync delta plus a checkpoint (lib/student/offlinePlayer.ts),
// so closing the app resumes at the next question. The sync badge in the header shows the answers
// moving from "saved on this phone" to "saved safely by Taleem" as they drain.
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useReducer, useRef, useState } from "react";

import { AppShell } from "@/components/student/AppShell";
import { ItemInteraction } from "@/components/student/ItemInteraction";
import { ReadAloud } from "@/components/student/ReadAloud";
import { Card, EmptyState, ErrorBanner, Skeleton } from "@/components/student/ui";
import { Button } from "@/design-system/Button";
import { ButtonLink } from "@/design-system/ButtonLink";
import { contentAttrs, pickLocalized } from "@/lib/i18n/content";
import { useLocale } from "@/lib/i18n/useLocale";
import type { SessionCheckpoint } from "@/lib/offline/types";
import { useLearner } from "@/lib/session/useLearner";
import { itemKind, type AnswerBody } from "@/lib/student/itemAnswer";
import { INSTRUCTION_LOCALE_PREFERENCE } from "@/lib/student/journey";
import { isLastStep, presentationSteps } from "@/lib/student/lessonPlayer";
import { getOfflineClient } from "@/lib/student/offlineClient";
import {
  canShowHint,
  contentLocale,
  createOfflineRunner,
  initialOfflineState,
  offlineItem,
  offlineReducer,
  type OfflineRunner,
} from "@/lib/student/offlinePlayer";
import { speechLang } from "@/lib/student/speech";

type Status = "loading" | "not-installed" | "resume" | "playing" | "error";

function OfflinePlayer() {
  const params = useSearchParams();
  const lessonId = params.get("lesson") ?? "";
  const { studentRef, band } = useLearner();
  const { t, formatNumber } = useLocale();
  const runner = useMemo<OfflineRunner | null>(() => {
    if (typeof window === "undefined" || !studentRef) return null;
    const client = getOfflineClient();
    return createOfflineRunner(
      {
        getLesson: (id) => client.downloads.getLesson(id),
        progress: client.progress,
        checkpoints: client.checkpoints,
        queue: client.sync.queue,
      },
      studentRef,
    );
  }, [studentRef]);

  const [status, setStatus] = useState<Status>("loading");
  const [state, dispatch] = useReducer(offlineReducer, initialOfflineState);
  const [resumeAt, setResumeAt] = useState(0);
  const checkpoint = useRef<SessionCheckpoint | null>(null);
  const shownAt = useRef(Date.now());
  const [saving, setSaving] = useState(false);
  const opened = useRef(false);

  useEffect(() => {
    if (!runner || !lessonId || opened.current) return;
    opened.current = true;
    void (async () => {
      try {
        const lesson = await runner.open(lessonId);
        if (!lesson) return setStatus("not-installed");
        checkpoint.current = lesson.checkpoint;
        dispatch({ type: "load", content: lesson.content });
        if (lesson.resumeAt > 0) {
          setResumeAt(lesson.resumeAt);
          setStatus("resume");
        } else setStatus("playing");
      } catch {
        setStatus("error");
      }
    })();
  }, [runner, lessonId]);

  useEffect(() => {
    if (!lessonId) setStatus("not-installed");
  }, [lessonId]);

  // Finished: record completion once.
  const completed = useRef(false);
  useEffect(() => {
    if (status !== "playing" || !state.done || completed.current || !runner || !checkpoint.current) return;
    completed.current = true;
    void runner.complete(checkpoint.current);
  }, [status, state.done, runner]);

  const item = offlineItem(state);
  useEffect(() => {
    shownAt.current = Date.now();
  }, [item?.item_ref]);

  // `answer` is the contract answer field for the item's kind; a choose answer is `{option}`.
  const choose = async (answer: AnswerBody) => {
    if (!runner || !checkpoint.current || !item || saving) return;
    setSaving(true);
    try {
      checkpoint.current = await runner.answer({
        checkpoint: checkpoint.current,
        item,
        answer,
        hintsUsed: state.player.hints.length,
        responseTimeMs: Date.now() - shownAt.current,
      });
      dispatch({ type: "saved" });
      // Online: send now. Offline: the auto-drain sends it on reconnect.
      if (typeof navigator === "undefined" || navigator.onLine) void getOfflineClient().sync.drain().catch(() => undefined);
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  };

  const skip = async () => {
    if (!runner || !checkpoint.current || !item || saving) return;
    setSaving(true);
    try {
      checkpoint.current = await runner.skip({ checkpoint: checkpoint.current, item });
      dispatch({ type: "skipped" });
    } catch {
      setStatus("error");
    } finally {
      setSaving(false);
    }
  };

  const steps = presentationSteps(state.player);
  const step = state.player.step;
  const lessonLocale = state.content ? contentLocale(state.content) : null;
  const prompt = item ? pickLocalized(item.prompt, INSTRUCTION_LOCALE_PREFERENCE) : null;
  const total = state.player.teach?.items.length ?? 0;

  return (
    <AppShell title={t("student.offline.player.title")} band={band} showNav={false}>
      <div>
        <ButtonLink href="/student/offline" variant="ghost" label={t("student.offline.player.backToLibrary")} />
      </div>
      <div aria-live="polite" style={{ display: "grid", gap: "var(--space-4)" }}>
        {status === "loading" ? <Skeleton lines={4} label={t("student.offline.player.loading")} /> : null}
        {status === "not-installed" ? (
          <EmptyState title={t("student.offline.player.notInstalledTitle")} body={t("student.offline.player.notInstalledBody")} />
        ) : null}
        {status === "error" ? <ErrorBanner message={t("student.offline.player.error")} /> : null}

        {status === "resume" ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
              <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("student.offline.player.resumeTitle")}</h2>
              <p style={{ margin: 0 }}>{t("student.offline.player.resumeBody", { count: resumeAt })}</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
                <Button
                  variant="brand"
                  label={t("student.offline.player.resume")}
                  onClick={() => {
                    if (state.content) dispatch({ type: "load", content: state.content, resumeAt });
                    setStatus("playing");
                  }}
                />
                <Button
                  variant="ghost"
                  label={t("student.offline.player.startAgain")}
                  onClick={() => {
                    void (async () => {
                      if (runner && checkpoint.current) checkpoint.current = await runner.restart(checkpoint.current);
                      if (state.content) dispatch({ type: "load", content: state.content });
                      setStatus("playing");
                    })();
                  }}
                />
              </div>
            </div>
          </Card>
        ) : null}

        {status === "playing" && state.done ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-2)", textAlign: "center", justifyItems: "center" }}>
              <h2 style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>{t("student.offline.player.doneTitle")}</h2>
              <p style={{ margin: 0 }}>
                {state.savedCount > 0
                  ? t("student.offline.player.doneBody", { count: state.savedCount })
                  : t("student.offline.player.doneBodyNone")}
              </p>
              <ButtonLink href="/student/offline" variant="brand" label={t("student.offline.player.backToLibrary")} />
            </div>
          </Card>
        ) : null}

        {status === "playing" && !state.done && state.player.phase === "presenting" && steps[step] ? (
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
                <ReadAloud label={t("student.session.teacherAudio")} text={steps[step].text} lang={speechLang(steps[step].text, null, lessonLocale)} />
              </div>
            </Card>
            <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "space-between" }}>
              <Button variant="ghost" label={t("common.back")} disabled={step === 0} onClick={() => dispatch({ type: "previousStep" })} />
              {isLastStep(state.player) ? (
                <Button variant="brand" label={t("student.session.ready")} onClick={() => dispatch({ type: "ready" })} />
              ) : (
                <Button variant="brand" label={t("common.next")} onClick={() => dispatch({ type: "nextStep" })} />
              )}
            </div>
          </section>
        ) : null}

        {status === "playing" && !state.done && state.player.phase === "asking" && item ? (
          <Card>
            <div style={{ display: "grid", gap: "var(--space-3)" }}>
              {state.justSaved ? (
                <p role="status" style={{ margin: 0, color: "var(--color-brand)" }}>
                  <span aria-hidden="true">✓ </span>
                  {t("student.offline.player.savedNotice")}
                </p>
              ) : null}
              <p style={{ margin: 0 }}>{t("student.session.questionOf", { current: state.player.itemIndex + 1, total })}</p>
              <div style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-2)", alignItems: "start" }}>
                <p {...contentAttrs({ locale: prompt?.locale, text: prompt?.text })} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
                  {prompt?.text ?? ""}
                </p>
                <ReadAloud label={t("student.session.questionAudio")} text={prompt?.text} lang={prompt?.locale} />
              </div>
              <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("student.offline.player.noKeyNote")}</p>
              {itemKind(item) === "choose" ? (
                <div role="group" aria-label={t("student.session.answers")} style={{ display: "grid", gap: "var(--space-2)" }}>
                  {item.options.map((opt, i) => (
                    <Button key={i} variant="primary" label={opt} {...contentAttrs({ text: opt })} disabled={saving} onClick={() => void choose({ option: i })} />
                  ))}
                </div>
              ) : (
                <ItemInteraction
                  key={item.item_ref}
                  item={item}
                  t={t}
                  formatNumber={formatNumber}
                  disabled={saving}
                  submitLabel={t("student.session.items.save")}
                  onSubmit={(body) => void choose(body)}
                  onSkip={() => void skip()}
                />
              )}
              {state.player.hints.length > 0 ? (
                <ol aria-label={t("student.session.hints")} style={{ margin: 0, paddingInlineStart: "var(--space-4)", display: "grid", gap: "var(--space-1)" }}>
                  {state.player.hints.map((h, i) => (
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
              {canShowHint(state) ? (
                <Button
                  variant="ghost"
                  label={state.player.hints.length === 0 ? t("student.session.hint") : t("student.session.anotherHint")}
                  onClick={() => dispatch({ type: "hint" })}
                />
              ) : null}
            </div>
          </Card>
        ) : null}
      </div>
    </AppShell>
  );
}

export default function OfflinePlayerPage() {
  return (
    <Suspense fallback={<Skeleton lines={4} />}>
      <OfflinePlayer />
    </Suspense>
  );
}
