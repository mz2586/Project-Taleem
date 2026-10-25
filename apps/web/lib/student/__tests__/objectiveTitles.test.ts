// Learners and guardians see a lesson's title, never its objective code ("ETH-G4-HON-01" means
// nothing to a nine-year-old). Today, the offline library and the guardian's child view all name an
// objective by the title the server sent (cohort-filtered there), in the title's own language.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { ObjectiveName } from "@/components/student/ObjectiveName";
import { TodayIdeas } from "@/components/student/TodayIdeas";

import { createTranslator } from "../../i18n/translate";
import type { OfflineContent, PackageManifest, StoredPackage } from "../../offline/types";
import { todayModel } from "../journey";
import { libraryModel } from "../offlineLibrary";
import { mergeTitles, objectiveName } from "../objectiveName";
import type { KnowledgeView, TodayView } from "../types";

const HONESTY = { ur: "[DEMO · unreviewed AI draft] ایمانداری", en: "[DEMO · unreviewed AI draft] Honesty" };
const CITY = { ur: "", en: "My city" };

describe("objectiveName", () => {
  it("prefers the Urdu title, then English, and keeps the authored locale", () => {
    expect(objectiveName("ETH-G4-HON-01", { "ETH-G4-HON-01": HONESTY })).toEqual({
      kind: "title",
      text: HONESTY.ur,
      locale: "ur",
      code: "ETH-G4-HON-01",
    });
    expect(objectiveName("SOC-G4-CTY-02", { "SOC-G4-CTY-02": CITY })).toMatchObject({ kind: "title", text: "My city", locale: "en" });
  });
  it("falls back to the code only when no title was sent", () => {
    expect(objectiveName("X-1", {})).toEqual({ kind: "code", text: "X-1", code: "X-1" });
    expect(objectiveName("X-1", { "X-1": { ur: " ", en: "" } })).toMatchObject({ kind: "code" });
    expect(objectiveName("X-1", undefined)).toMatchObject({ kind: "code" });
  });
  it("merges maps, skipping empty titles", () => {
    expect(mergeTitles({ A: HONESTY, B: { en: "" } }, { C: CITY })).toEqual({ A: HONESTY, C: CITY });
  });
});

describe("ObjectiveName", () => {
  it("renders the title with its own lang/dir and never the code as visible text", () => {
    const html = renderToStaticMarkup(createElement(ObjectiveName, { name: objectiveName("ETH-G4-HON-01", { "ETH-G4-HON-01": HONESTY }) }));
    expect(html).toContain(HONESTY.ur);
    expect(html).toContain('lang="ur"');
    expect(html).toContain('dir="rtl"');
    expect(html.replace(/data-objective="[^"]*"/, "")).not.toContain("ETH-G4-HON-01");
  });
});

describe("Today", () => {
  const knowledge: KnowledgeView = {
    student_ref: "s",
    objectives: {
      "ETH-G4-HON-01": { mastery: 0.9, uncertainty: 0.1, state: "mastered" },
      "SOC-G4-CTY-02": { mastery: 0.4, uncertainty: 0.3, state: "in_progress" },
    },
  };
  const today: TodayView = {
    next_action: { objective_code: "SOC-G4-CTY-02", reason: "learn", title: CITY },
    mastery_summary: { mastered: 1, in_progress: 1, total: 2 },
    revision_due_count: 0,
    objective_titles: { "ETH-G4-HON-01": HONESTY },
  };

  it("carries the server's titles, including the next action's", () => {
    const model = todayModel({ today, knowledge, progress: null });
    expect(model.titles).toEqual({ "ETH-G4-HON-01": HONESTY, "SOC-G4-CTY-02": CITY });
    expect(todayModel({ today: null, knowledge, progress: null }).titles).toEqual({});
  });

  it("lists the learner's ideas by title, not by code", () => {
    const model = todayModel({ today, knowledge, progress: null });
    const t = createTranslator("en");
    const html = renderToStaticMarkup(
      createElement(TodayIdeas, { objectives: model.objectives, titles: model.titles, label: "Your ideas", t: (k) => t(k) }),
    );
    expect(html).toContain(HONESTY.ur);
    expect(html).toContain("My city");
    expect(html.replace(/data-objective="[^"]*"/g, "")).not.toMatch(/ETH-G4-HON-01|SOC-G4-CTY-02/);
  });
});

describe("offline library", () => {
  const manifest = (lessonId: string, title?: Record<string, string>): PackageManifest => ({
    package_id: `pkg/${lessonId}`,
    lesson_id: lessonId,
    objective_code: "ETH-G4-HON-01",
    ...(title ? { title } : {}),
    version: "h1",
    content_hash: "h1",
    assets: [],
    total_bytes: 10,
    created_at_ms: 0,
  });
  const stored: StoredPackage = {
    package_id: "pkg/L1",
    lesson_id: "L1",
    content_hash: "h1",
    version: "h1",
    state: "ready",
    total_bytes: 10,
    installed_at: 0,
    last_used_at: 0,
  };

  it("names a lesson from the index title before it is downloaded", () => {
    const model = libraryModel({ list: { status: "ok", manifests: [manifest("L1", HONESTY)] }, installed: [], titles: {}, downloads: {} });
    expect(model.kind === "list" && model.entries[0]?.title).toEqual({ text: HONESTY.ur, locale: "ur" });
  });

  it("prefers the installed (verified) content's title over the index", () => {
    const content: OfflineContent["title"] = { ur: "", en: "Installed honesty" };
    const model = libraryModel({
      list: { status: "ok", manifests: [manifest("L1", HONESTY)] },
      installed: [stored],
      titles: { L1: content },
      downloads: {},
    });
    expect(model.kind === "list" && model.entries[0]?.title).toEqual({ text: "Installed honesty", locale: "en" });
  });

  it("has no title only when the index from an older server sent none", () => {
    const model = libraryModel({ list: { status: "ok", manifests: [manifest("L1")] }, installed: [], titles: {}, downloads: {} });
    expect(model.kind === "list" && model.entries[0]?.title).toBeNull();
  });
});
