// The fixed, tap-to-choose concern categories (server: contexts/safeguarding/domain/model.py).
//
// Each carries a picture for a child who cannot read yet, and two wordings: the child's own ("Someone
// made me feel unsafe") and an adult's ("Someone made my child feel unsafe"). The tier is the
// server's; it is mirrored here only so the console can explain it, never to decide anything.

import type { MessageKey } from "../i18n/messages";

export const CATEGORIES = ["felt_unsafe", "very_sad", "bullying", "upsetting_lesson", "other"] as const;
export type Category = (typeof CATEGORIES)[number];

export const PRIORITIES = ["T1", "T2", "T3"] as const;
export type Priority = (typeof PRIORITIES)[number];

export interface CategoryOption {
  value: Category;
  /** Decorative; always shown next to the words, never instead of them. */
  symbol: string;
  childKey: MessageKey;
  adultKey: MessageKey;
  priority: Priority;
}

export const CATEGORY_OPTIONS: readonly CategoryOption[] = [
  {
    value: "felt_unsafe",
    symbol: "🛑",
    childKey: "safeguarding.categories.child.felt_unsafe",
    adultKey: "safeguarding.categories.adult.felt_unsafe",
    priority: "T1",
  },
  {
    value: "very_sad",
    symbol: "😢",
    childKey: "safeguarding.categories.child.very_sad",
    adultKey: "safeguarding.categories.adult.very_sad",
    priority: "T1",
  },
  {
    value: "bullying",
    symbol: "😠",
    childKey: "safeguarding.categories.child.bullying",
    adultKey: "safeguarding.categories.adult.bullying",
    priority: "T2",
  },
  {
    value: "upsetting_lesson",
    symbol: "📖",
    childKey: "safeguarding.categories.child.upsetting_lesson",
    adultKey: "safeguarding.categories.adult.upsetting_lesson",
    priority: "T2",
  },
  {
    value: "other",
    symbol: "💬",
    childKey: "safeguarding.categories.child.other",
    adultKey: "safeguarding.categories.adult.other",
    priority: "T3",
  },
];

export function isCategory(value: unknown): value is Category {
  return typeof value === "string" && (CATEGORIES as readonly string[]).includes(value);
}

export function categoryOption(value: string): CategoryOption | null {
  return CATEGORY_OPTIONS.find((o) => o.value === value) ?? null;
}

/** Same bound as the server (characters after trimming). */
export const MAX_TEXT = 500;

/** Trimmed text, or null when empty. Over-long text is reported, never silently cut. */
export function cleanText(raw: string): { ok: true; text: string | null } | { ok: false; reason: "too-long" } {
  const text = raw.trim();
  if (!text) return { ok: true, text: null };
  if ([...text].length > MAX_TEXT) return { ok: false, reason: "too-long" };
  return { ok: true, text };
}
