"use client";
// One written answer in the teacher's marking queue (HOMEWORK_AND_MARKING_CONTRACT.md §3, §4): who
// and what, the prompt, the child's text, the rubric and the sample answer or guidance; then — while
// it is waiting — the mark form and "send back to try again"; and, on every row, a clearly separate
// "Raise a safeguarding concern" with an in-page confirm step. Body rules: lib/homework/teacher.ts.
import { useId, useRef, useState, type FormEvent, type ReactNode } from "react";

import { FormError, FormNotice } from "@/components/form";
import { Button } from "@/design-system/Button";
import { formatDateTime, isoDateTime } from "@/lib/guardian/format";
import { markingApi } from "@/lib/homework/api";
import {
  CONCERN_NOTE_MAX,
  concernBody,
  concernErrorKey,
  decisionErrorKey,
  FEEDBACK_MAX,
  markBody,
  returnBody,
  type MarkDraft,
  type MarkProblems,
  type SubmissionRowView,
} from "@/lib/homework/teacher";
import type { MarkOutcome } from "@/lib/homework/types";
import { contentAttrs, type LocalizedText } from "@/lib/i18n/content";
import type { Locale } from "@/lib/i18n/config";
import type { MessageKey } from "@/lib/i18n/messages";
import type { Translator } from "@/lib/i18n/translate";
import { CATEGORIES, type Category } from "@/lib/safeguarding/categories";

const card = {
  display: "grid",
  gap: "var(--space-3)",
  padding: "var(--space-4)",
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
  minWidth: 0,
} as const;

const textareaStyle = {
  width: "100%",
  boxSizing: "border-box" as const,
  minHeight: "6rem",
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-focus-ring)",
  background: "var(--color-bg-canvas)",
  color: "var(--color-text-primary)",
  font: "inherit",
  fontSize: "var(--font-size-body-min-urdu)",
  resize: "vertical" as const,
};

const fieldsetStyle = { border: "none", margin: 0, padding: 0, display: "grid", gap: "var(--space-2)", minWidth: 0 } as const;
const radioRow = { display: "flex", flexWrap: "wrap", gap: "var(--space-2)" } as const;
const radioLabel = {
  display: "inline-flex",
  alignItems: "center",
  gap: "var(--space-2)",
  minHeight: "var(--size-touch-min)",
  padding: "0 var(--space-3)",
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
} as const;
const errorText = { color: "var(--color-danger)", fontSize: "var(--font-size-body-min)" } as const;

function Authored({ value, as = "p" }: { value: LocalizedText; as?: "p" | "span" }) {
  const attrs = contentAttrs({ locale: value.locale || null, text: value.text });
  const Tag = as;
  return (
    <Tag lang={attrs.lang} dir={attrs.dir} style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
      {value.text}
    </Tag>
  );
}

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div style={{ display: "grid", gap: "var(--space-1)" }}>
      <strong>{title}</strong>
      {children}
    </div>
  );
}

function Counter({ id, text, max, t }: { id: string; text: string; max: number; t: Translator }) {
  const n = Array.from(text.trim()).length;
  const over = n > max;
  return (
    <span id={id} style={{ fontSize: "var(--font-size-body-min)", color: over ? "var(--color-danger)" : undefined, fontWeight: over ? 700 : 400 }}>
      {over ? <span aria-hidden="true">⚠ </span> : null}
      {t("teacher.marking.counter", { count: n, max })}
    </span>
  );
}

export type Decision = "marked" | "returned";

export interface SubmissionCardProps {
  row: SubmissionRowView;
  t: Translator;
  locale: Locale;
  /** After a mark or a return: the page removes the row and moves focus to its notice. */
  onDecided: (submissionId: string, decision: Decision) => void;
}

// ---- mark ------------------------------------------------------------------------------------------

function MarkForm({ row, t, onDecided }: SubmissionCardProps) {
  const id = useId();
  const [draft, setDraft] = useState<MarkDraft>({ outcome: null, score: "", feedback: "" });
  const [problems, setProblems] = useState<MarkProblems>({});
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);
  const firstOutcome = useRef<HTMLInputElement | null>(null);
  const firstScore = useRef<HTMLInputElement | null>(null);
  const feedbackRef = useRef<HTMLTextAreaElement | null>(null);
  const errorRef = useRef<HTMLDivElement | null>(null);
  const rubric = row.rubric;

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const built = markBody(draft, rubric);
    if (!built.ok) {
      setProblems(built.problems);
      // Focus the first field that needs attention.
      (built.problems.outcome ? firstOutcome : built.problems.score ? firstScore : feedbackRef).current?.focus();
      return;
    }
    setProblems({});
    setBusy(true);
    try {
      await markingApi.mark(row.submissionId, built.body);
      onDecided(row.submissionId, "marked");
    } catch (e) {
      setError(decisionErrorKey(e));
      setBusy(false);
      requestAnimationFrame(() => errorRef.current?.focus());
    }
  }

  const outcomes: Array<{ value: MarkOutcome; key: MessageKey; symbol: string }> = [
    { value: "met", key: "teacher.marking.met", symbol: "✓" },
    { value: "not_yet", key: "teacher.marking.notYet", symbol: "…" },
  ];

  return (
    <form onSubmit={submit} noValidate aria-labelledby={`${id}-title`} style={{ display: "grid", gap: "var(--space-3)" }}>
      <h4 id={`${id}-title`} style={{ margin: 0 }}>
        {t("teacher.marking.submit")}
      </h4>
      <fieldset style={fieldsetStyle} aria-describedby={problems.outcome ? `${id}-outcome-error` : undefined}>
        <legend style={{ padding: 0, marginBottom: "var(--space-1)" }}>{t("teacher.marking.outcomeLegend")}</legend>
        <div style={radioRow}>
          {outcomes.map((o, i) => (
            <label key={o.value} style={radioLabel}>
              <input
                ref={i === 0 ? firstOutcome : undefined}
                type="radio"
                name={`${id}-outcome`}
                value={o.value}
                checked={draft.outcome === o.value}
                onChange={() => setDraft((d) => ({ ...d, outcome: o.value }))}
              />
              <span aria-hidden="true">{o.symbol}</span>
              <span>{t(o.key)}</span>
            </label>
          ))}
        </div>
        {problems.outcome ? (
          <span id={`${id}-outcome-error`} role="alert" style={errorText}>
            {t(problems.outcome)}
          </span>
        ) : null}
      </fieldset>

      {rubric ? (
        <fieldset style={fieldsetStyle} aria-describedby={problems.score ? `${id}-score-error` : undefined}>
          <legend style={{ padding: 0, marginBottom: "var(--space-1)" }}>{t("teacher.marking.scoreLegend", { max: rubric.maxScore })}</legend>
          <div style={radioRow}>
            {rubric.levels.map((level, i) => (
              <label key={level.score} style={radioLabel}>
                <input
                  ref={i === 0 ? firstScore : undefined}
                  type="radio"
                  name={`${id}-score`}
                  value={String(level.score)}
                  checked={draft.score === String(level.score)}
                  onChange={() => setDraft((d) => ({ ...d, score: String(level.score) }))}
                />
                <span>{t("teacher.marking.scoreOption", { score: level.score })}</span>
                {level.label ? <Authored value={level.label} as="span" /> : null}
              </label>
            ))}
          </div>
          {problems.score ? (
            <span id={`${id}-score-error`} role="alert" style={errorText}>
              {t(problems.score)}
            </span>
          ) : null}
        </fieldset>
      ) : null}

      <div style={{ display: "grid", gap: "var(--space-1)" }}>
        <label htmlFor={`${id}-feedback`}>{t("teacher.marking.feedbackLabel")}</label>
        <span id={`${id}-feedback-hint`} style={{ fontSize: "var(--font-size-body-min)" }}>
          {t("teacher.marking.feedbackHint")}
        </span>
        <textarea
          ref={feedbackRef}
          id={`${id}-feedback`}
          dir="auto"
          value={draft.feedback}
          onChange={(e) => setDraft((d) => ({ ...d, feedback: e.target.value }))}
          aria-describedby={`${id}-feedback-hint ${id}-feedback-count${problems.feedback ? ` ${id}-feedback-error` : ""}`}
          aria-invalid={problems.feedback ? true : undefined}
          style={textareaStyle}
        />
        <Counter id={`${id}-feedback-count`} text={draft.feedback} max={FEEDBACK_MAX} t={t} />
        {problems.feedback ? (
          <span id={`${id}-feedback-error`} role="alert" style={errorText}>
            {t(problems.feedback)}
          </span>
        ) : null}
      </div>
      <div ref={errorRef} tabIndex={-1}>
        {error ? <FormError message={t(error)} /> : null}
      </div>
      <div>
        <Button type="submit" variant="brand" label={t("teacher.marking.submit")} loading={busy} />
      </div>
    </form>
  );
}

// ---- send back ---------------------------------------------------------------------------------------

function ReturnForm({ row, t, onDecided }: SubmissionCardProps) {
  const id = useId();
  const [feedback, setFeedback] = useState("");
  const [problem, setProblem] = useState<MessageKey | null>(null);
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);
  const fieldRef = useRef<HTMLTextAreaElement | null>(null);
  const errorRef = useRef<HTMLDivElement | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const built = returnBody(feedback);
    if (!built.ok) {
      setProblem(built.problems.feedback ?? null);
      fieldRef.current?.focus();
      return;
    }
    setProblem(null);
    setBusy(true);
    try {
      await markingApi.return(row.submissionId, built.body);
      onDecided(row.submissionId, "returned");
    } catch (e) {
      setError(decisionErrorKey(e));
      setBusy(false);
      requestAnimationFrame(() => errorRef.current?.focus());
    }
  }

  return (
    <form onSubmit={submit} noValidate aria-labelledby={`${id}-title`} style={{ display: "grid", gap: "var(--space-2)" }}>
      <h4 id={`${id}-title`} style={{ margin: 0 }}>
        {t("teacher.marking.returnTitle")}
      </h4>
      <label htmlFor={`${id}-feedback`}>{t("teacher.marking.returnLabel")}</label>
      <span id={`${id}-hint`} style={{ fontSize: "var(--font-size-body-min)" }}>
        {t("teacher.marking.returnHint")}
      </span>
      <textarea
        ref={fieldRef}
        id={`${id}-feedback`}
        dir="auto"
        required
        aria-required="true"
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        aria-describedby={`${id}-hint ${id}-count${problem ? ` ${id}-error` : ""}`}
        aria-invalid={problem ? true : undefined}
        style={textareaStyle}
      />
      <Counter id={`${id}-count`} text={feedback} max={FEEDBACK_MAX} t={t} />
      {problem ? (
        <span id={`${id}-error`} role="alert" style={errorText}>
          {t(problem)}
        </span>
      ) : null}
      <div ref={errorRef} tabIndex={-1}>
        {error ? <FormError message={t(error)} /> : null}
      </div>
      <div>
        <Button type="submit" variant="ghost" label={t("teacher.marking.returnSubmit")} loading={busy} />
      </div>
    </form>
  );
}

// ---- safeguarding ------------------------------------------------------------------------------------

export function ConcernAction({ row, t }: Pick<SubmissionCardProps, "row" | "t">) {
  const id = useId();
  const [stage, setStage] = useState<"closed" | "confirm" | "sent">("closed");
  const [category, setCategory] = useState<Category | null>(null);
  const [note, setNote] = useState("");
  const [problem, setProblem] = useState<MessageKey | null>(null);
  const [error, setError] = useState<MessageKey | null>(null);
  const [busy, setBusy] = useState(false);
  const openRef = useRef<HTMLButtonElement | null>(null);
  const confirmHeading = useRef<HTMLHeadingElement | null>(null);
  const doneRef = useRef<HTMLDivElement | null>(null);
  const firstCategory = useRef<HTMLInputElement | null>(null);

  function open() {
    setStage("confirm");
    setError(null);
    setProblem(null);
    requestAnimationFrame(() => confirmHeading.current?.focus());
  }

  function cancel() {
    setStage("closed");
    setCategory(null);
    setNote("");
    setProblem(null);
    setError(null);
    requestAnimationFrame(() => openRef.current?.focus());
  }

  async function send(event: FormEvent) {
    event.preventDefault();
    setError(null);
    const built = concernBody({ category, note });
    if (!built.ok) {
      setProblem(built.problem);
      firstCategory.current?.focus();
      return;
    }
    setProblem(null);
    setBusy(true);
    try {
      await markingApi.raiseConcern(row.submissionId, built.body);
      setStage("sent");
      requestAnimationFrame(() => doneRef.current?.focus());
    } catch (e) {
      setError(concernErrorKey(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      aria-labelledby={`${id}-title`}
      data-concern={stage}
      style={{
        display: "grid",
        gap: "var(--space-2)",
        marginTop: "var(--space-2)",
        paddingTop: "var(--space-3)",
        borderTop: "2px dashed var(--color-danger)",
      }}
    >
      <h4 id={`${id}-title`} className="visually-hidden">
        {t("teacher.marking.concern.open")}
      </h4>
      {stage === "closed" ? (
        <div>
          <button
            ref={openRef}
            type="button"
            onClick={open}
            style={{
              minHeight: "var(--size-touch-min)",
              padding: "var(--space-2) var(--space-3)",
              background: "transparent",
              color: "var(--color-danger)",
              border: "2px solid var(--color-danger)",
              borderRadius: "var(--radius-md)",
              font: "inherit",
              cursor: "pointer",
              textAlign: "start",
            }}
          >
            <span aria-hidden="true">🛡 </span>
            {t("teacher.marking.concern.open")}
          </button>
        </div>
      ) : null}

      {stage === "confirm" ? (
        <form onSubmit={send} noValidate style={{ display: "grid", gap: "var(--space-2)" }}>
          <h5 ref={confirmHeading} tabIndex={-1} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
            {t("teacher.marking.concern.confirmTitle")}
          </h5>
          <p style={{ margin: 0 }}>{t("teacher.marking.concern.intro")}</p>
          <fieldset style={fieldsetStyle} aria-describedby={problem ? `${id}-problem` : undefined}>
            <legend style={{ padding: 0, marginBottom: "var(--space-1)" }}>{t("teacher.marking.concern.categoryLegend")}</legend>
            {CATEGORIES.map((c, i) => (
              <label key={c} style={radioLabel}>
                <input
                  ref={i === 0 ? firstCategory : undefined}
                  type="radio"
                  name={`${id}-category`}
                  value={c}
                  checked={category === c}
                  onChange={() => setCategory(c)}
                />
                <span>{t(`teacher.marking.concern.categories.${c}`)}</span>
              </label>
            ))}
          </fieldset>
          <label htmlFor={`${id}-note`}>{t("teacher.marking.concern.noteLabel")}</label>
          <span id={`${id}-note-hint`} style={{ fontSize: "var(--font-size-body-min)" }}>
            {t("teacher.marking.concern.noteHint")}
          </span>
          <textarea
            id={`${id}-note`}
            dir="auto"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            aria-describedby={`${id}-note-hint ${id}-note-count`}
            style={textareaStyle}
          />
          <Counter id={`${id}-note-count`} text={note} max={CONCERN_NOTE_MAX} t={t} />
          {problem ? (
            <span id={`${id}-problem`} role="alert" style={errorText}>
              {t(problem)}
            </span>
          ) : null}
          {error ? <FormError message={t(error)} /> : null}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
            <Button type="submit" variant="danger" label={t("teacher.marking.concern.confirm")} loading={busy} />
            <Button type="button" variant="ghost" label={t("teacher.marking.concern.cancel")} onClick={cancel} disabled={busy} />
          </div>
        </form>
      ) : null}

      {stage === "sent" ? (
        <div ref={doneRef} tabIndex={-1}>
          <FormNotice message={t("teacher.marking.concern.done")} />
        </div>
      ) : null}
    </section>
  );
}

// ---- the card ----------------------------------------------------------------------------------------

export function SubmissionCard(props: SubmissionCardProps) {
  const { row, t, locale } = props;
  const headingId = useId();
  const rubric = row.rubric;
  const hasGuide = !!(rubric || row.sampleAnswer || row.guidance);

  return (
    <article aria-labelledby={headingId} data-submission={row.submissionId} style={card}>
      <header style={{ display: "grid", gap: "var(--space-1)" }}>
        <h3 id={headingId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
          {row.learnerName ? <bdi>{row.learnerName}</bdi> : t("teacher.marking.unnamed")}
        </h3>
        <span>
          {t("teacher.marking.lessonLabel")}:{" "}
          {row.lessonTitle ? (
            <Authored value={row.lessonTitle} as="span" />
          ) : (
            <bdi dir="ltr" style={{ fontFamily: "var(--font-latin)" }}>
              {row.objectiveCode}
            </bdi>
          )}
        </span>
        <span style={{ fontSize: "var(--font-size-body-min)" }}>
          {t("teacher.marking.itemLabel")}:{" "}
          <bdi dir="ltr" style={{ fontFamily: "var(--font-latin)" }}>
            {row.itemRef}
          </bdi>
        </span>
        <time dateTime={isoDateTime(row.submittedAt)} style={{ fontSize: "var(--font-size-body-min)" }}>
          {t("teacher.marking.submittedAt", { date: formatDateTime(row.submittedAt, locale) })}
        </time>
      </header>

      {row.prompt ? (
        <Block title={t("teacher.marking.promptLabel")}>
          <Authored value={row.prompt} />
        </Block>
      ) : null}

      <Block title={t("teacher.marking.answerLabel")}>
        <p
          dir="auto"
          style={{
            margin: 0,
            padding: "var(--space-3)",
            background: "var(--color-bg-canvas)",
            border: "1px solid var(--color-focus-ring)",
            borderRadius: "var(--radius-md)",
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
          }}
        >
          {row.text}
        </p>
      </Block>

      {hasGuide ? (
        <details>
          <summary style={{ minHeight: "var(--size-touch-min)", display: "flex", alignItems: "center", cursor: "pointer" }}>
            {rubric ? t("teacher.marking.rubricTitle") : row.sampleAnswer ? t("teacher.marking.sampleAnswer") : t("teacher.marking.guidance")}
          </summary>
          <div style={{ display: "grid", gap: "var(--space-3)", paddingTop: "var(--space-2)" }}>
            {rubric ? (
              <Block title={t("teacher.marking.rubricMax", { max: rubric.maxScore })}>
                {rubric.criteria.length > 0 ? (
                  <>
                    <span>{t("teacher.marking.criteriaTitle")}</span>
                    <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
                      {rubric.criteria.map((c, i) => (
                        <li key={i}>
                          <Authored value={c} as="span" />
                        </li>
                      ))}
                    </ul>
                  </>
                ) : null}
                <dl style={{ margin: 0, display: "grid", gap: "var(--space-1)" }}>
                  {rubric.levels
                    .filter((l) => l.label || l.descriptor)
                    .map((l) => (
                      <div key={l.score} style={{ display: "grid", gap: "var(--space-1)" }}>
                        <dt style={{ fontWeight: 700 }}>
                          {t("teacher.marking.scoreOption", { score: l.score })}
                          {l.label ? (
                            <>
                              {" — "}
                              <Authored value={l.label} as="span" />
                            </>
                          ) : null}
                        </dt>
                        {l.descriptor ? (
                          <dd style={{ margin: 0, paddingInlineStart: "var(--space-3)" }}>
                            <Authored value={l.descriptor} as="span" />
                          </dd>
                        ) : null}
                      </div>
                    ))}
                </dl>
              </Block>
            ) : null}
            {row.sampleAnswer ? (
              <Block title={t("teacher.marking.sampleAnswer")}>
                <Authored value={row.sampleAnswer} />
              </Block>
            ) : null}
            {row.guidance ? (
              <Block title={t("teacher.marking.guidance")}>
                <Authored value={row.guidance} />
              </Block>
            ) : null}
          </div>
        </details>
      ) : (
        <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("teacher.marking.noGuide")}</p>
      )}

      {row.state === "submitted" ? (
        <>
          <MarkForm {...props} />
          <ReturnForm {...props} />
        </>
      ) : (
        <div style={{ display: "grid", gap: "var(--space-1)" }}>
          {row.decidedAt ? (
            <time dateTime={isoDateTime(row.decidedAt)} style={{ fontSize: "var(--font-size-body-min)" }}>
              {t("teacher.marking.decidedAt", { date: formatDateTime(row.decidedAt, locale) })}
            </time>
          ) : null}
          {row.state === "marked" && row.outcome ? (
            <strong>{t(row.outcome === "met" ? "teacher.marking.decided.met" : "teacher.marking.decided.notYet")}</strong>
          ) : null}
          {row.state === "marked" && rubric && row.score !== null ? (
            <span>{t("teacher.marking.decided.score", { score: row.score, max: rubric.maxScore })}</span>
          ) : null}
          {row.feedback ? (
            <Block title={t(row.state === "returned" ? "teacher.marking.decided.returnNote" : "teacher.marking.decided.feedback")}>
              <p dir="auto" style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
                {row.feedback}
              </p>
            </Block>
          ) : null}
        </div>
      )}

      <ConcernAction row={row} t={t} />
    </article>
  );
}
