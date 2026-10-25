// Small shared pieces for the path, unit-check and record screens. No hooks: server-safe, so the
// node suite renders them with react-dom/server.
import type { ReactNode } from "react";

import { contentAttrs, type LocalizedText } from "@/lib/i18n/content";
import type { Badge } from "@/lib/progression/view";

/** Curriculum text keeps its own language and direction, whatever the interface language is. */
export function LocalText({ value, as = "span" }: { value: LocalizedText; as?: "span" | "strong" }) {
  const attrs = contentAttrs({ locale: value.locale || null, text: value.text });
  const Tag = as;
  return (
    <Tag lang={attrs.lang} dir={attrs.dir}>
      {value.text}
    </Tag>
  );
}

const TONE: Record<string, string> = {
  mastered: "var(--color-brand)",
  completed: "var(--color-brand)",
  practised: "var(--color-text-primary)",
  ready_for_check: "var(--color-action-primary)",
  in_progress: "var(--color-action-primary)",
  not_started: "var(--color-text-primary)",
};

/**
 * A state: a decorative shape plus the words. Colour is only a third cue — "Practice done" (✓,
 * plain border) and "Mastered" (★, filled) differ in symbol, words and outline.
 */
export function StateMark({ badge }: { badge: Badge }) {
  const filled = badge.state === "mastered" || badge.state === "completed";
  return (
    <span
      data-state={badge.state}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-1)",
        padding: "0 var(--space-2)",
        borderRadius: "var(--radius-md)",
        border: filled ? "2px solid var(--color-brand)" : "1px dashed var(--color-focus-ring)",
        fontWeight: filled ? 700 : 400,
        color: TONE[badge.state] ?? "var(--color-text-primary)",
        whiteSpace: "normal",
      }}
    >
      <span aria-hidden="true">{badge.symbol}</span>
      <span>{badge.label}</span>
    </span>
  );
}

export function Notice({ children, role = "status" }: { children: ReactNode; role?: "status" | "note" }) {
  return (
    <p
      role={role}
      style={{
        margin: 0,
        padding: "var(--space-3)",
        border: "2px solid var(--color-action-primary)",
        borderRadius: "var(--radius-md)",
      }}
    >
      {children}
    </p>
  );
}

/** "Taleem unit check — not a certificate", always visible wherever a check or result appears. */
export function ClaimLine({ text }: { text: string }) {
  return (
    <p data-claim="" style={{ margin: 0, fontSize: "var(--font-size-body-min)" }}>
      <span aria-hidden="true">ⓘ </span>
      {text}
    </p>
  );
}
