// The item renderers' markup, rendered to static HTML in the node suite (react-dom/server; no jsdom).
// What is checked here is what a screen reader and a small screen get: real buttons, aria-pressed,
// labelled groups and input, lesson text keeping its own lang/dir in an Urdu (RTL) and an English
// (LTR) interface, and a submit that starts disabled with its reason. The tap rules behind the
// markup are covered in itemAnswer.test.ts.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ItemInteraction, type ItemInteractionProps } from "@/components/student/ItemInteraction";

import { formatNumber } from "../../i18n/format";
import { createTranslator } from "../../i18n/translate";
import type { InteractiveItem } from "../itemAnswer";

type Locale = "ur" | "en";

function render(item: InteractiveItem, locale: Locale = "ur", extra: Partial<ItemInteractionProps> = {}): string {
  const t = createTranslator(locale);
  const html = renderToStaticMarkup(
    createElement(ItemInteraction, {
      item: { item_ref: "it-1", ...item },
      t,
      formatNumber: (n: number) => formatNumber(n, locale),
      submitLabel: t("student.session.items.check"),
      onSubmit: () => undefined,
      ...extra,
    }),
  );
  // As the app renders it: inside the interface's <html dir>.
  return `<div dir="${locale === "ur" ? "rtl" : "ltr"}">${html}</div>`;
}

const count = (html: string, needle: string) => html.split(needle).length - 1;

function submitButton(html: string): string {
  const label = /<button[^>]*>(?:(?!<\/button>).)*?(میرا جواب جانچیں|Check my answer)(?:(?!<\/button>).)*?<\/button>/s.exec(html);
  expect(label, "submit button").not.toBeNull();
  return label![0];
}

describe("fill renderer", () => {
  it("is a labelled text input that accepts any script, with submit disabled until something is typed", () => {
    const html = render({ kind: "fill", options: [] });
    expect(html).toContain('data-item-kind="fill"');
    expect(html).toMatch(/<label for="([^"]+)"[^>]*>آپ کا جواب<\/label><input id="\1"/);
    expect(html).toContain('type="text"');
    expect(html).toContain('inputMode="text"');
    expect(html).toContain('dir="auto"');
    expect(html).toContain('maxLength="200"');
    expect(html).toContain("اردو یا انگریزی میں لکھیں");
    const submit = submitButton(html);
    expect(submit).toContain("disabled");
    expect(submit).toContain("aria-describedby");
    expect(html).toContain("پہلے اپنا جواب مکمل کریں۔");
  });
});

describe("order renderer", () => {
  const item = { kind: "order", options: ["دوسرا", "پہلا", "Third"] };

  it("renders every item as a real toggle button, nothing placed, and undo/clear/submit disabled", () => {
    const html = render(item);
    expect(html).toContain('data-item-kind="order"');
    expect(count(html, 'aria-pressed="false"')).toBe(3);
    expect(html).not.toContain('aria-pressed="true"');
    expect(html).toContain('aria-label="چیزیں"');
    expect(html).toContain("ابھی کچھ نہیں چنا گیا۔");
    expect(html).toMatch(/<button disabled=""[^>]*aria-label="واپس لیں"/);
    expect(html).toMatch(/<button disabled=""[^>]*aria-label="دوبارہ شروع کریں"/);
    expect(submitButton(html)).toContain("disabled");
    // An always-present polite live region for the tap announcements.
    expect(html).toContain('role="status" aria-live="polite"');
  });

  it("keeps each item's own direction: Urdu items RTL, English items LTR", () => {
    expect(render(item)).toContain('<span dir="rtl">پہلا</span>');
    expect(render(item, "en")).toContain('<span dir="ltr">Third</span>');
  });

  it("uses large touch targets (above the 44px minimum)", () => {
    expect(render(item)).toContain("min-height:56px");
  });
});

describe("match renderer", () => {
  const item = { kind: "match", left_count: 2, options: ["گائے", "Cat", "دودھ", "Meow"] };

  it("splits the options at left_count into two labelled groups of real buttons", () => {
    const html = render(item, "en");
    expect(html).toContain('data-item-kind="match"');
    expect(html).toContain('role="group" aria-label="Items"');
    expect(html).toContain('role="group" aria-label="Matches"');
    // Items are toggles (selected or not); matches are plain buttons.
    expect(count(html, "aria-pressed=")).toBe(2);
    expect(count(html, "<button")).toBe(2 + 2 + 1 + 1); // items + matches + clear + submit
    expect(html).toContain("Tap an item, then tap its match.");
    expect(submitButton(html)).toContain("disabled");
  });

  it("renders in an RTL (Urdu) interface with Urdu copy and RTL lesson text", () => {
    const html = render(item, "ur");
    expect(html.startsWith('<div dir="rtl">')).toBe(true);
    expect(html).toContain('aria-label="جوڑ"');
    expect(html).toContain('<span dir="rtl" style="overflow-wrap:anywhere">گائے</span>');
    expect(html).toContain('<span dir="ltr" style="overflow-wrap:anywhere">Meow</span>');
    // Two equal columns that fit a 360px screen (they never overflow: minmax(0, 1fr)).
    expect(html).toContain("grid-template-columns:repeat(2, minmax(0, 1fr))");
  });

  it("disables every control while an answer is being saved or checked", () => {
    const html = render(item, "ur", { disabled: true });
    expect(count(html, "<button")).toBe(count(html, 'disabled=""'));
  });
});

describe("sort renderer", () => {
  it("shows cards and groups, each group with its card count", () => {
    const html = render({ kind: "sort", left_count: 3, options: ["2", "3", "4", "جفت", "طاق"] }, "ur");
    expect(html).toContain('data-item-kind="sort"');
    expect(html).toContain('aria-label="کارڈ"');
    expect(html).toContain('aria-label="گروہ"');
    expect(count(html, 'aria-pressed="false"')).toBe(3);
    expect(count(html, "0 کارڈ")).toBe(2);
    expect(html).toContain("ایک کارڈ ٹیپ کریں");
    expect(submitButton(html)).toContain("disabled");
  });
});

describe("unrenderable items", () => {
  it("a match/sort without a usable left_count says so instead of rendering a broken question", () => {
    const html = render({ kind: "match", options: ["a", "b"] }, "en");
    expect(html).toContain('role="alert"');
    expect(html).toContain("can&#x27;t be shown");
    expect(html).not.toContain("<button");
  });
});
