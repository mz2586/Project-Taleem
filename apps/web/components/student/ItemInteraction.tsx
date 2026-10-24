"use client";
// Renderers for the answerable item kinds beyond "choose" (ITEM_INTERACTION_CONTRACT.md): fill,
// order, match and sort. Shared by the online lesson player and the offline player.
//
// Rules every renderer keeps (docs/19-component-library.md, WCAG 2.2 AA):
// - Tap first, and keyboard / screen reader equal: every interaction is a real <button> (or a real
//   <input>), toggles carry aria-pressed, and each tap is announced in a polite status line. There is
//   no drag-only interaction anywhere.
// - State is shown by text and shape, never colour alone: a position number, a pair number, a
//   "→ group" line, plus the same state as visually-hidden text on the button itself.
// - Focus moves to where the next tap belongs (a match after choosing an item, the next free item
//   after pairing, the submit button once the answer is complete) and is never stranded on a
//   button that just became disabled.
// - Lesson text keeps its own lang/dir (contentAttrs); the chrome follows the interface direction,
//   so the two columns of match/sort mirror in Urdu with no extra code.
// - Submit stays disabled until the answer is complete, with the reason shown beside it.
// The interaction rules themselves live, pure and tested, in lib/student/itemAnswer.ts.
import { useId, useRef, useState, type CSSProperties, type FormEvent, type Ref } from "react";

import { Button, buttonStyle } from "@/design-system/Button";
import { contentAttrs } from "@/lib/i18n/content";
import type { Translator } from "@/lib/i18n/translate";
import {
  emptyPairDraft,
  fillAnswer,
  FILL_MAX_LENGTH,
  isRenderable,
  itemKind,
  leftFor,
  leftsIn,
  nextUnpaired,
  orderAnswer,
  orderTap,
  orderUndo,
  pairedCount,
  pairsAnswer,
  splitPoint,
  tapLeft,
  tapRight,
  type AnswerBody,
  type InteractiveItem,
  type PairDraft,
  type PairEvent,
  type PairMode,
} from "@/lib/student/itemAnswer";

export interface ItemInteractionProps {
  item: InteractiveItem & { item_ref: string };
  t: Translator;
  /** Numbers in the interface locale (position and pair markers). */
  formatNumber: (value: number) => string;
  /** No interaction at all (feedback on screen, or an answer being saved). */
  disabled?: boolean;
  /** The submit button's label: "Check my answer" online, "Save my answer" offline. */
  submitLabel: string;
  onSubmit: (answer: AnswerBody) => void;
  /**
   * Move past an item this phone cannot render, without answering it. When absent, the notice is
   * shown alone (the page offers its own way out).
   */
  onSkip?: () => void;
}

/** The answer area for a fill / order / match / sort item. Choose items stay with their page. */
export function ItemInteraction(props: ItemInteractionProps) {
  const { item, t, onSkip, disabled } = props;
  if (!isRenderable(item)) {
    return (
      <div style={{ display: "grid", gap: "var(--space-2)", justifyItems: "start" }}>
        <p role="alert" style={{ margin: 0 }}>
          {t("student.session.items.unavailable")}
        </p>
        {onSkip ? (
          <Button variant="brand" label={t("student.session.items.skip")} icon={<span aria-hidden="true">⏭</span>} disabled={disabled} onClick={onSkip} />
        ) : null}
      </div>
    );
  }
  const kind = itemKind(item);
  if (kind === "fill") return <FillItem {...props} />;
  if (kind === "order") return <OrderItem {...props} />;
  if (kind === "match" || kind === "sort") return <PairItem {...props} mode={kind} />;
  return null;
}

// ---- shared pieces ------------------------------------------------------------------------------------

const tileBase: CSSProperties = {
  ...buttonStyle("ghost"),
  width: "100%",
  minHeight: "56px", // above the 44px minimum: these are the main targets for small fingers
  justifyContent: "space-between",
  textAlign: "start",
  fontSize: "var(--font-size-body-min-urdu)",
};

function tileStyle(state: "idle" | "selected" | "done", disabled: boolean): CSSProperties {
  return {
    ...tileBase,
    // Selection is shown by a thicker border AND the "●" marker AND aria-pressed; a placed tile by
    // its number/line. Colour is only ever a third cue.
    border:
      state === "selected"
        ? "4px solid var(--color-action-primary)"
        : state === "done"
          ? "2px solid var(--color-brand)"
          : "1px solid var(--color-focus-ring)",
    cursor: disabled ? "not-allowed" : "pointer",
    opacity: disabled ? 0.6 : 1,
  };
}

function Badge({ children }: { children: string }) {
  return (
    <span
      aria-hidden="true"
      style={{
        minWidth: "2em",
        padding: "0 var(--space-1)",
        borderRadius: "var(--radius-md)",
        background: "var(--color-brand)",
        color: "var(--color-on-brand)",
        textAlign: "center",
        fontWeight: 700,
      }}
    >
      {children}
    </span>
  );
}

function Hidden({ text }: { text: string | null }) {
  return text ? <span className="visually-hidden">{`, ${text}`}</span> : null;
}

function Submit({
  t,
  label,
  answer,
  disabled,
  onSubmit,
  buttonRef,
}: {
  t: Translator;
  label: string;
  answer: AnswerBody | null;
  disabled?: boolean;
  onSubmit: (answer: AnswerBody) => void;
  buttonRef?: Ref<HTMLButtonElement>;
}) {
  const reasonId = useId();
  return (
    <div style={{ display: "grid", gap: "var(--space-1)", justifyItems: "start" }}>
      <button
        ref={buttonRef}
        type="button"
        disabled={disabled || answer === null}
        aria-describedby={answer === null ? reasonId : undefined}
        onClick={() => {
          if (answer && !disabled) onSubmit(answer);
        }}
        style={buttonStyle("brand", disabled || answer === null)}
      >
        <span>{label}</span>
      </button>
      {answer === null ? (
        <p id={reasonId} style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
          {t("student.session.items.incomplete")}
        </p>
      ) : null}
    </div>
  );
}

function Status({ text }: { text: string }) {
  // Always rendered, so the live region exists before its first announcement.
  return (
    <p role="status" aria-live="polite" className="visually-hidden">
      {text}
    </p>
  );
}

const focusSoon = (el: HTMLElement | null | undefined) => {
  // After React commits the new state (a just-enabled button cannot take focus before that).
  if (el) requestAnimationFrame(() => el.focus());
};

// ---- fill ---------------------------------------------------------------------------------------------

function FillItem({ item, t, disabled, submitLabel, onSubmit }: ItemInteractionProps) {
  const [text, setText] = useState("");
  const inputId = useId();
  const helpId = useId();
  const answer = fillAnswer(text);
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (answer && !disabled) onSubmit(answer);
  };
  return (
    <form onSubmit={submit} style={{ display: "grid", gap: "var(--space-2)" }} data-item-kind="fill" data-item-ref={item.item_ref}>
      <label htmlFor={inputId} style={{ fontWeight: 700 }}>
        {t("student.session.items.fillLabel")}
      </label>
      <input
        id={inputId}
        type="text"
        // Urdu, English and digits alike: no numeric keyboard, and the direction follows what is typed.
        inputMode="text"
        dir="auto"
        autoComplete="off"
        autoCorrect="off"
        autoCapitalize="none"
        spellCheck={false}
        enterKeyHint="done"
        maxLength={FILL_MAX_LENGTH}
        value={text}
        disabled={disabled}
        aria-describedby={helpId}
        onChange={(e) => setText(e.target.value)}
        style={{
          minHeight: "56px",
          width: "100%",
          boxSizing: "border-box",
          padding: "var(--space-2) var(--space-3)",
          font: "inherit",
          fontSize: "var(--font-size-body-min-urdu)",
          border: "2px solid var(--color-focus-ring)",
          borderRadius: "var(--radius-md)",
          background: "var(--color-bg-canvas)",
          color: "var(--color-text-primary)",
        }}
      />
      <p id={helpId} style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
        {t("student.session.items.fillHelp")}
      </p>
      <Submit t={t} label={submitLabel} answer={answer} disabled={disabled} onSubmit={onSubmit} />
    </form>
  );
}

// ---- order --------------------------------------------------------------------------------------------

function OrderItem({ item, t, formatNumber, disabled, submitLabel, onSubmit }: ItemInteractionProps) {
  const [sequence, setSequence] = useState<number[]>([]);
  const [status, setStatus] = useState("");
  const helpId = useId();
  const choiceRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const submitRef = useRef<HTMLButtonElement | null>(null);
  const n = item.options.length;
  const answer = orderAnswer(sequence, n);
  const text = (i: number) => item.options[i] ?? "";

  const tap = (i: number) => {
    const next = orderTap(sequence, i);
    setSequence(next);
    if (next.length > sequence.length) {
      setStatus(t("student.session.items.orderAdded", { item: text(i), position: next.length }));
      if (orderAnswer(next, n)) focusSoon(submitRef.current);
    } else {
      setStatus(t("student.session.items.orderRemoved", { item: text(i) }));
    }
  };
  const undo = () => {
    const last = sequence[sequence.length - 1];
    if (last === undefined) return;
    const next = orderUndo(sequence);
    setSequence(next);
    setStatus(t("student.session.items.orderRemoved", { item: text(last) }));
    if (next.length === 0) focusSoon(choiceRefs.current[0]); // Undo is about to be disabled
  };
  const clear = () => {
    setSequence([]);
    setStatus(t("student.session.items.orderCleared"));
    focusSoon(choiceRefs.current[0]);
  };

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }} data-item-kind="order" data-item-ref={item.item_ref}>
      <p id={helpId} style={{ margin: 0 }}>
        {t("student.session.items.orderHelp")}
      </p>
      <section aria-label={t("student.session.items.orderSequence")} style={{ display: "grid", gap: "var(--space-1)" }}>
        <strong>{t("student.session.items.orderSequence")}</strong>
        {sequence.length === 0 ? (
          <p style={{ margin: 0 }}>{t("student.session.items.orderEmpty")}</p>
        ) : (
          <ol style={{ margin: 0, paddingInlineStart: "var(--space-6)", display: "grid", gap: "var(--space-1)" }}>
            {sequence.map((i) => (
              <li key={i}>
                <span {...contentAttrs({ text: text(i) })}>{text(i)}</span>
              </li>
            ))}
          </ol>
        )}
      </section>
      <div role="group" aria-label={t("student.session.items.orderChoices")} aria-describedby={helpId} style={{ display: "grid", gap: "var(--space-2)" }}>
        {item.options.map((opt, i) => {
          const position = sequence.indexOf(i);
          const placed = position >= 0;
          return (
            <button
              key={i}
              ref={(el) => {
                choiceRefs.current[i] = el;
              }}
              type="button"
              aria-pressed={placed}
              disabled={disabled}
              onClick={() => tap(i)}
              style={tileStyle(placed ? "done" : "idle", !!disabled)}
            >
              <span {...contentAttrs({ text: opt })}>{opt}</span>
              <Hidden text={placed ? t("student.session.items.orderPlaced", { position: position + 1 }) : null} />
              {placed ? <Badge>{formatNumber(position + 1)}</Badge> : null}
            </button>
          );
        })}
      </div>
      <p style={{ margin: 0 }}>{t("student.session.items.progress", { done: sequence.length, total: n })}</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
        <Button variant="ghost" label={t("student.session.items.undo")} icon={<span aria-hidden="true">↶</span>} disabled={disabled || sequence.length === 0} onClick={undo} />
        <Button variant="ghost" label={t("student.session.items.clear")} disabled={disabled || sequence.length === 0} onClick={clear} />
      </div>
      <Submit t={t} label={submitLabel} answer={answer} disabled={disabled} onSubmit={onSubmit} buttonRef={submitRef} />
      <Status text={status} />
    </div>
  );
}

// ---- match + sort -------------------------------------------------------------------------------------

function PairItem({ item, t, formatNumber, disabled, submitLabel, onSubmit, mode }: ItemInteractionProps & { mode: PairMode }) {
  const k = splitPoint(item) ?? 0;
  const [draft, setDraft] = useState<PairDraft>(emptyPairDraft);
  const [status, setStatus] = useState("");
  const helpId = useId();
  const leftRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const rightRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const submitRef = useRef<HTMLButtonElement | null>(null);
  const text = (i: number) => item.options[i] ?? "";
  const lefts = item.options.slice(0, k);
  const rights = item.options.slice(k);
  const answer = pairsAnswer(draft, k);
  const p = "student.session.items" as const;

  const announce = (event: PairEvent) => {
    switch (event.type) {
      case "selected":
        return t(`${p}.selected`, { item: text(event.left) });
      case "deselected":
        return t(`${p}.deselected`, { item: text(event.left) });
      case "paired":
        return t(`${p}.paired`, { item: text(event.left), other: text(event.right) });
      case "unpaired":
        return t(`${p}.unpaired`, { item: text(event.left) });
      case "needLeft":
        return t(`${p}.needLeft`);
    }
  };

  const apply = (step: { draft: PairDraft; event: PairEvent }) => {
    setDraft(step.draft);
    setStatus(announce(step.event));
    const { event } = step;
    if (event.type === "selected") {
      // Straight to the other column: the next tap belongs there.
      const firstFree = mode === "match" ? rights.findIndex((_, j) => leftFor(step.draft, k + j) === null) : 0;
      focusSoon(rightRefs.current[Math.max(0, firstFree)]);
    } else if (event.type === "paired") {
      if (pairsAnswer(step.draft, k)) focusSoon(submitRef.current);
      else focusSoon(leftRefs.current[nextUnpaired(step.draft, k, event.left) ?? 0]);
    } else if (event.type === "needLeft") {
      focusSoon(leftRefs.current[nextUnpaired(step.draft, k) ?? 0]);
    }
  };

  const clear = () => {
    setDraft(emptyPairDraft);
    setStatus(t(`${p}.cleared`));
    focusSoon(leftRefs.current[0]);
  };

  const anyPlaced = pairedCount(draft, k) > 0 || draft.selected !== null;
  const column: CSSProperties = { display: "grid", gap: "var(--space-2)", alignContent: "start", minWidth: 0 };

  return (
    <div style={{ display: "grid", gap: "var(--space-3)" }} data-item-kind={mode} data-item-ref={item.item_ref}>
      <p id={helpId} style={{ margin: 0 }}>
        {t(mode === "match" ? `${p}.matchHelp` : `${p}.sortHelp`)}
      </p>
      {/* Two columns even at 360px; in Urdu the first column is on the right, as it reads. */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "var(--space-3)" }}>
        <div role="group" aria-label={t(mode === "match" ? `${p}.matchItems` : `${p}.sortCards`)} aria-describedby={helpId} style={column}>
          {lefts.map((opt, l) => {
            const right = draft.pairs[l];
            const selected = draft.selected === l;
            const placedText =
              right === undefined
                ? null
                : mode === "match"
                  ? t(`${p}.matchedWith`, { other: text(right) })
                  : t(`${p}.inGroup`, { group: text(right) });
            return (
              <button
                key={l}
                ref={(el) => {
                  leftRefs.current[l] = el;
                }}
                type="button"
                aria-pressed={selected}
                disabled={disabled}
                onClick={() => apply(tapLeft(draft, l, mode))}
                style={{ ...tileStyle(selected ? "selected" : right !== undefined ? "done" : "idle", !!disabled), flexDirection: "column", alignItems: "stretch" }}
              >
                <span style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-1)", alignItems: "center" }}>
                  <span {...contentAttrs({ text: opt })} style={{ overflowWrap: "anywhere" }}>
                    {opt}
                  </span>
                  {mode === "match" ? <Badge>{formatNumber(l + 1)}</Badge> : null}
                  {selected ? <span aria-hidden="true">●</span> : null}
                </span>
                {right !== undefined ? (
                  <span aria-hidden="true" style={{ fontSize: "var(--font-size-body-min)" }}>
                    {mode === "match" ? "↔ " : "→ "}
                    <span {...contentAttrs({ text: text(right) })}>{text(right)}</span>
                  </span>
                ) : null}
                <Hidden text={placedText} />
              </button>
            );
          })}
        </div>
        <div role="group" aria-label={t(mode === "match" ? `${p}.matchTargets` : `${p}.sortGroups`)} style={column}>
          {rights.map((opt, j) => {
            const r = k + j;
            const owner = mode === "match" ? leftFor(draft, r) : null;
            const members = mode === "sort" ? leftsIn(draft, r) : [];
            const placedText =
              mode === "match"
                ? owner === null
                  ? null
                  : t(`${p}.matchedWith`, { other: text(owner) })
                : t(`${p}.groupCount`, { count: members.length });
            return (
              <button
                key={r}
                ref={(el) => {
                  rightRefs.current[j] = el;
                }}
                type="button"
                disabled={disabled}
                onClick={() => apply(tapRight(draft, r, mode))}
                style={{ ...tileStyle(owner !== null ? "done" : "idle", !!disabled), flexDirection: "column", alignItems: "stretch" }}
              >
                <span style={{ display: "flex", justifyContent: "space-between", gap: "var(--space-1)", alignItems: "center" }}>
                  <span {...contentAttrs({ text: opt })} style={{ overflowWrap: "anywhere" }}>
                    {opt}
                  </span>
                  {owner !== null ? <Badge>{formatNumber(owner + 1)}</Badge> : null}
                  {mode === "sort" ? <Badge>{formatNumber(members.length)}</Badge> : null}
                </span>
                {mode === "sort" && members.length > 0 ? (
                  <span aria-hidden="true" style={{ display: "grid", fontSize: "var(--font-size-body-min)" }}>
                    {members.map((l) => (
                      <span key={l} {...contentAttrs({ text: text(l) })}>
                        {text(l)}
                      </span>
                    ))}
                  </span>
                ) : null}
                <Hidden text={placedText} />
              </button>
            );
          })}
        </div>
      </div>
      <p style={{ margin: 0 }}>{t(`${p}.progress`, { done: pairedCount(draft, k), total: k })}</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)" }}>
        <Button variant="ghost" label={t(`${p}.clear`)} disabled={disabled || !anyPlaced} onClick={clear} />
      </div>
      <Submit t={t} label={submitLabel} answer={answer} disabled={disabled} onSubmit={onSubmit} buttonRef={submitRef} />
      <Status text={status} />
    </div>
  );
}
