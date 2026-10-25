"use client";
// One written homework item (HOMEWORK_AND_MARKING_CONTRACT.md §2, §6): the prompt (with read-aloud),
// its state in symbol + words, the marker's note, and — while the item is open — a labelled answer
// box with a visible character counter and a Send button whose reason for being disabled sits beside it.
//
// Honesty rules: "Sent" / "Saved" is shown only after the server accepted the answer. Offline, Send
// queues the answer for offline sync (when the page passes `queue`) and says only "Saved on this
// phone — will send when online"; `sync` then shows the server's own result once it arrives, or a
// gentle conflict message. What the child types is kept on this phone (lib/homework/drafts.ts) until
// the server confirms it. A marked answer is read-only. §6: a self-paced item never
// uses teacher wording; "Checked by Taleem" only when the server says `reviewed_by: "auto"`; a
// self-check answer is "saved", never "marked", and its comparison appears only after it was sent.
// The rules are pure and unit-tested in lib/homework/student.ts.
import { useEffect, useId, useRef, useState, type FormEvent } from "react";

import { Button } from "@/design-system/Button";
import { contentAttrs } from "@/lib/i18n/content";
import type { Translator } from "@/lib/i18n/translate";
import type { DraftStore } from "@/lib/homework/drafts";
import type { HomeworkSyncView } from "@/lib/homework/offlineQueue";
import {
  afterSent,
  compareView,
  initialText,
  itemCopy,
  isOpen,
  sendLabelKey,
  sendHomework,
  sendOutcomeKey,
  stateBadge,
  submitGate,
  syncMessageKey,
  type HomeworkItemView,
  type SendOutcome,
} from "@/lib/homework/student";
import type { LearnerSubmissionWire, SubmitBody } from "@/lib/homework/types";

import { ReadAloud } from "./ReadAloud";

export interface HomeworkItemCardProps {
  item: HomeworkItemView;
  /** 1-based position within its assignment, for the heading. */
  position: number;
  t: Translator;
  formatNumber: (value: number) => string;
  online: boolean;
  draftKey: string;
  drafts: DraftStore;
  send: (body: SubmitBody) => Promise<LearnerSubmissionWire | undefined>;
  /** Called after an accepted send, with the item's new state (the parent owns the list). */
  onSent: (item: HomeworkItemView) => void;
  /** Locale order for the self-check comparison text the server returns on submit. */
  contentPreference?: readonly string[];
  /** Queue the answer for offline sync when there is no connection (absent: offline only keeps it). */
  queue?: (body: SubmitBody) => Promise<void>;
  /** Where this item's offline answer stands (queued / confirmed / conflict), from the sync queue. */
  sync?: HomeworkSyncView | null;
}

const box = {
  display: "grid",
  gap: "var(--space-2)",
  padding: "var(--space-3)",
  border: "1px solid var(--color-focus-ring)",
  borderRadius: "var(--radius-md)",
} as const;

const textareaStyle = {
  width: "100%",
  boxSizing: "border-box" as const,
  minHeight: "8rem",
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-focus-ring)",
  background: "var(--color-bg-canvas)",
  color: "var(--color-text-primary)",
  font: "inherit",
  fontSize: "var(--font-size-body-min-urdu)",
  resize: "vertical" as const,
};

export function HomeworkItemCard({
  item,
  position,
  t,
  formatNumber,
  online,
  draftKey,
  drafts,
  send,
  onSent,
  contentPreference,
  queue,
  sync = null,
}: HomeworkItemCardProps) {
  const id = useId();
  // The server render and first client render start from the sent text; a kept draft is read after
  // mount (storage does not exist on the server), so both renders match.
  const [text, setText] = useState(() => initialText(item, null));
  const [sending, setSending] = useState(false);
  const [outcome, setOutcome] = useState<SendOutcome | null>(null);
  const statusRef = useRef<HTMLParagraphElement | null>(null);

  const itemRef = useRef(item);
  itemRef.current = item;
  useEffect(() => {
    const draft = drafts.read(draftKey);
    if (draft) setText(initialText(itemRef.current, draft));
  }, [draftKey, drafts]);

  // A new sync answer (sent / checked / conflict) replaces the last local message. "Saved on this
  // phone" stays while the answer waits; a result or conflict hides once the child types again.
  const syncId = sync ? `${sync.kind}:${sync.clientEventId}` : null;
  const [dismissedSync, setDismissedSync] = useState<string | null>(null);
  useEffect(() => {
    if (syncId && !syncId.startsWith("queued:")) setOutcome(null);
  }, [syncId]);
  const syncKey = sync && (sync.kind === "queued" || syncId !== dismissedSync) ? syncMessageKey(sync, item) : null;

  const open = isOpen(item.state, item.canRetry);
  const badge = stateBadge(item);
  const copy = itemCopy(item);
  const compare = compareView(item);
  const gate = submitGate({
    text,
    maxChars: item.maxChars,
    state: item.state,
    sending,
    online,
    canRetry: item.canRetry,
    finalReason: copy.final,
    canQueue: queue !== undefined,
  });
  const prompt = item.prompt;
  const promptAttrs = prompt ? contentAttrs({ locale: prompt.locale || null, text: prompt.text }) : null;

  const headingId = `${id}-h`;
  const fieldId = `${id}-answer`;
  const hintId = `${id}-hint`;
  const counterId = `${id}-count`;
  const reasonId = `${id}-reason`;
  const compareId = `${id}-compare`;

  function change(value: string) {
    setText(value);
    setOutcome(null);
    setDismissedSync(syncId);
    // Kept as typed, so a dropped connection never loses the child's writing.
    drafts.write(draftKey, value);
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!gate.canSend) return;
    setSending(true);
    const result = await sendHomework({
      online,
      text,
      maxChars: item.maxChars,
      state: item.state,
      canRetry: item.canRetry,
      draftKey,
      drafts,
      send,
      ...(queue ? { queue } : {}),
    });
    setSending(false);
    setOutcome(result);
    if (result.kind === "sent") {
      setText(result.text);
      onSent(afterSent(item, result, contentPreference));
    }
    // The result line is where the child's attention belongs next (Send may now be disabled).
    requestAnimationFrame(() => statusRef.current?.focus());
  }

  return (
    <article aria-labelledby={headingId} data-state={item.state} style={box}>
      <h3 id={headingId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
        {t("student.homework.question", { number: formatNumber(position) })}
      </h3>

      {prompt && promptAttrs ? (
        <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
          <p lang={promptAttrs.lang} dir={promptAttrs.dir} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
            {prompt.text}
          </p>
          <ReadAloud text={prompt.text} lang={prompt.locale || null} label={t("student.homework.questionAudio")} />
        </div>
      ) : null}

      {item.hints.length > 0 && open ? (
        <details>
          <summary style={{ minHeight: "var(--size-touch-min)", display: "flex", alignItems: "center", cursor: "pointer" }}>
            {t("student.homework.hintsTitle")}
          </summary>
          <ul style={{ margin: 0, paddingInlineStart: "var(--space-4)" }}>
            {item.hints.map((hint) => (
              <li key={hint} dir="auto">
                {hint}
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      <p data-badge={badge.state} style={{ margin: 0, display: "inline-flex", gap: "var(--space-1)", alignItems: "center", fontWeight: 700 }}>
        <span aria-hidden="true">{badge.symbol}</span>
        <span>{t(badge.labelKey)}</span>
      </p>

      {badge.note ? (
        <div style={{ display: "grid", gap: "var(--space-1)", paddingInlineStart: "var(--space-3)", borderInlineStart: "4px solid var(--color-action-primary)" }}>
          <strong>{t(badge.noteKey)}</strong>
          <p dir="auto" style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {badge.note}
          </p>
        </div>
      ) : null}

      {compare ? (
        <section
          aria-labelledby={compareId}
          data-compare=""
          style={{ display: "grid", gap: "var(--space-2)", padding: "var(--space-3)", borderRadius: "var(--radius-md)", border: "2px dashed var(--color-focus-ring)" }}
        >
          <h4 id={compareId} style={{ margin: 0, fontSize: "var(--font-size-body-min-urdu)" }}>
            {t("student.homework.compare.title")}
          </h4>
          <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t("student.homework.compare.notMarked")}</p>
          {compare.sample ? <CompareText label={t("student.homework.compare.sample")} text={compare.sample} /> : null}
          {compare.guidance ? <CompareText label={t("student.homework.compare.guidance")} text={compare.guidance} /> : null}
        </section>
      ) : null}

      {!open ? (
        item.sentText ? (
          <div style={{ display: "grid", gap: "var(--space-1)" }}>
            <strong>{t(item.source === "self_paced" ? "student.homework.whatYouWrote" : "student.homework.whatYouSent")}</strong>
            <p dir="auto" style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
              {item.sentText}
            </p>
          </div>
        ) : null
      ) : (
        <form onSubmit={submit} noValidate style={{ display: "grid", gap: "var(--space-2)" }}>
          <label htmlFor={fieldId} style={{ fontSize: "var(--font-size-body-min-urdu)" }}>
            {t("student.homework.answerLabel")}
          </label>
          <span id={hintId} style={{ fontSize: "var(--font-size-body-min)" }}>
            {t("student.homework.answerHint")}
          </span>
          <textarea
            id={fieldId}
            dir="auto"
            value={text}
            rows={item.maxChars > 200 ? 6 : 3}
            onChange={(e) => change(e.target.value)}
            aria-describedby={`${hintId} ${counterId}`}
            aria-invalid={gate.over ? true : undefined}
            disabled={sending}
            style={textareaStyle}
          />
          <p
            id={counterId}
            data-over={gate.over || undefined}
            style={{ margin: 0, fontSize: "var(--font-size-body-min)", color: gate.over ? "var(--color-danger)" : undefined, fontWeight: gate.over ? 700 : 400 }}
          >
            {gate.over ? <span aria-hidden="true">⚠ </span> : null}
            {t("student.homework.counter", { count: formatNumber(gate.count), max: formatNumber(item.maxChars) })}
          </p>
          {item.state === "submitted" || item.state === "returned" ? (
            <p style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>{t(copy.resendNote)}</p>
          ) : null}
          <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", alignItems: "center" }}>
            <Button
              type="submit"
              variant="brand"
              label={t(sendLabelKey(item, copy))}
              loading={sending}
              disabled={!gate.canSend}
              aria-describedby={gate.reason ? reasonId : undefined}
            />
          </div>
          {gate.reason ? (
            <p id={reasonId} style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
              {t(gate.reason)}
            </p>
          ) : null}
          {gate.note ? (
            <p data-note="offline-queue" style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
              {t(gate.note)}
            </p>
          ) : null}
        </form>
      )}

      <p
        ref={statusRef}
        tabIndex={-1}
        role="status"
        aria-live="polite"
        data-outcome={outcome?.kind}
        data-sync={!outcome && syncKey ? sync?.kind : undefined}
        style={{ margin: 0 }}
      >
        {outcome ? t(sendOutcomeKey(outcome, item)) : syncKey ? t(syncKey) : ""}
      </p>
    </article>
  );
}

function CompareText({ label, text }: { label: string; text: { text: string; locale: string } }) {
  const attrs = contentAttrs({ locale: text.locale || null, text: text.text });
  return (
    <div style={{ display: "grid", gap: "var(--space-1)" }}>
      <strong>{label}</strong>
      <p lang={attrs.lang} dir={attrs.dir} style={{ margin: 0, whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
        {text.text}
      </p>
    </div>
  );
}
