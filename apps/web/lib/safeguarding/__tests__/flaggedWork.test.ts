// "What the child wrote" on the safeguarding lead's concern view: the pure view-model and the static
// markup (react-dom/server; no jsdom). Checked: only a concern naming a submission offers it; it is a
// button, never auto-loaded; the audit note is visible before the read; the loaded answer shows the
// lesson, question, time, the child's words (dir="auto") and the matched phrase entries; ur + en.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { FlaggedWork, FlaggedWorkBody } from "@/app/safeguarding/concerns/[concernId]/FlaggedWork";

import { SUPPORTED_LOCALES } from "../../i18n/config";
import { createTranslator, translate } from "../../i18n/translate";
import {
  flaggedWorkErrorKey,
  flaggedWorkView,
  hasFlaggedWork,
  pickLocalised,
  type ConcernContextWire,
} from "../triage";

const WORDS = "My uncle hits me when nobody is home.";

function wire(over: Partial<ConcernContextWire> = {}): ConcernContextWire {
  return {
    concern_id: "sgc_1",
    submission: {
      submission_id: "sub_1",
      source: "self_paced",
      objective_code: "M4.FR.01",
      item_ref: "hw-short",
      text: WORDS,
      attempt: 1,
      submitted_at: 1_760_000_000,
      item_prompt: { ur: "اپنے گھر کے بارے میں لکھیں", en: "Write about your home" },
      lesson_title: { ur: "کسور", en: "Fractions" },
    },
    matched_phrases: [{ phrase_id: "en-01", lang: "en", category: "felt_unsafe", phrase: "hits me" }],
    resubmitted_since_raised: false,
    read_recorded: true,
    ...over,
  };
}

const never = () => Promise.reject(new Error("must not be called while rendering"));

describe("flagged work view-model", () => {
  it("is offered only for a concern that names a submission", () => {
    expect(hasFlaggedWork({ context: { screen: "learner/homework", lesson_id: null, submission_id: "sub_1" } })).toBe(true);
    expect(hasFlaggedWork({ context: { screen: "learner/homework", lesson_id: null, submission_id: null } })).toBe(false);
    expect(hasFlaggedWork({ context: { screen: "learner/today", lesson_id: null } })).toBe(false);
    expect(hasFlaggedWork({ context: { screen: "x", lesson_id: null, submission_id: "" } })).toBe(false);
  });

  it("picks the reader's locale, then Urdu, then English, then anything", () => {
    expect(pickLocalised({ ur: "کسور", en: "Fractions" }, "en")).toBe("Fractions");
    expect(pickLocalised({ ur: "کسور", en: "Fractions" }, "ur")).toBe("کسور");
    expect(pickLocalised({ en: "Fractions" }, "ur")).toBe("Fractions");
    expect(pickLocalised({ ar: "x" }, "ur")).toBe("x");
    expect(pickLocalised({}, "ur")).toBeNull();
    expect(pickLocalised(undefined, "ur")).toBeNull();
  });

  it("arranges the wire without changing the child's words", () => {
    const v = flaggedWorkView(wire(), "en");
    expect(v).toEqual({
      text: WORDS,
      lessonTitle: "Fractions",
      prompt: "Write about your home",
      submittedAt: 1_760_000_000,
      attempt: 1,
      matched: [{ id: "en-01", phrase: "hits me", lang: "en" }],
      resubmitted: false,
    });
  });

  it("maps a 404 to 'nothing to read' and other failures to the console errors", () => {
    expect(flaggedWorkErrorKey({ status: 404 })).toBe("safeguarding.console.detail.flagged.gone");
    expect(flaggedWorkErrorKey({ status: 403 })).toBe("safeguarding.console.denied");
    expect(flaggedWorkErrorKey({ status: 0 })).toBe("safeguarding.console.offline");
  });

  it("has every string in both locales", () => {
    const keys = [
      "heading", "intro", "recorded", "show", "loading", "lesson", "prompt", "submittedAt", "attempt",
      "answer", "matched", "noMatch", "resubmitted", "readRecorded", "unknown", "gone",
    ] as const;
    for (const locale of SUPPORTED_LOCALES) {
      for (const k of keys) {
        const key = `safeguarding.console.detail.flagged.${k}` as const;
        expect(translate(locale, key)).not.toBe(key);
      }
      expect(translate(locale, "safeguarding.console.raisedBy.system")).not.toBe("safeguarding.console.raisedBy.system");
      expect(translate(locale, "safeguarding.console.raisedBy.teacher")).not.toBe("safeguarding.console.raisedBy.teacher");
    }
    expect(translate("ur", "safeguarding.console.detail.flagged.heading")).not.toBe(
      translate("en", "safeguarding.console.detail.flagged.heading"),
    );
  });
});

describe("FlaggedWork markup", () => {
  for (const locale of ["ur", "en"] as const) {
    it(`is a labelled section with a button and the audit note, nothing loaded (${locale})`, () => {
      const t = createTranslator(locale);
      const html = renderToStaticMarkup(createElement(FlaggedWork, { concernId: "sgc_1", t, locale, read: never }));
      expect(html).toMatch(/<section[^>]*aria-labelledby="([^"]+)"/);
      const labelledBy = /aria-labelledby="([^"]+)"/.exec(html)?.[1] ?? "";
      expect(html).toContain(`<h2 id="${labelledBy}"`);
      expect(html).toContain(t("safeguarding.console.detail.flagged.heading"));
      expect(html).toContain(t("safeguarding.console.detail.flagged.recorded"));
      expect(html).toMatch(/<button[^>]*>.*?<\/button>/s);
      expect(html).toContain(t("safeguarding.console.detail.flagged.show"));
      expect(html).not.toContain(WORDS); // never auto-loaded
    });
  }

  it("shows the lesson, question, time, the words and the matched entries once loaded", () => {
    const t = createTranslator("ur");
    const html = renderToStaticMarkup(createElement(FlaggedWorkBody, { view: flaggedWorkView(wire(), "ur"), t, locale: "ur" }));
    expect(html).toContain("کسور");
    expect(html).toContain("اپنے گھر کے بارے میں لکھیں");
    expect(html).toMatch(/<blockquote dir="auto"[^>]*>My uncle hits me when nobody is home\.<\/blockquote>/);
    expect(html).toContain("en-01");
    expect(html).toContain('lang="en"');
    expect(html).toContain(t("safeguarding.console.detail.flagged.readRecorded"));
    expect(html).not.toContain(t("safeguarding.console.detail.flagged.resubmitted"));
  });

  it("warns when the child changed the answer after it was flagged, and says when nothing matches now", () => {
    const t = createTranslator("en");
    const view = flaggedWorkView(
      wire({ resubmitted_since_raised: true, matched_phrases: [], submission: { ...wire().submission, item_prompt: {}, attempt: 2 } }),
      "en",
    );
    const html = renderToStaticMarkup(createElement(FlaggedWorkBody, { view, t, locale: "en" }));
    expect(html).toContain(t("safeguarding.console.detail.flagged.resubmitted"));
    expect(html).toContain(t("safeguarding.console.detail.flagged.noMatch"));
    expect(html).toContain(t("safeguarding.console.detail.flagged.unknown"));
    expect(html).toContain(t("safeguarding.console.detail.flagged.attempt", { n: 2 }));
  });
});
