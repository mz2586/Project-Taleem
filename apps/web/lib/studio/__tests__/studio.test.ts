import { describe, expect, it } from "vitest";

import { initialPlayerState, isLastStep, playerReducer, presentationSteps } from "../../student/lessonPlayer";
import { translate } from "../../i18n/translate";
import type { LessonView, ValidationResult } from "../../studio-api";
import { diffBodies, flatten, leafLocale } from "../diff";
import { draftErrors, EMPTY_DRAFT, packLocales, parseOutcomes, toDraftIn } from "../draft";
import { buildPatch, editableFields, editErrors } from "../edit";
import { itemHints, hasContent, learnerPreview, lessonLocales, localizedRows, versionRows } from "../preview";
import { parseStudioToken, STUDIO_ROLES, type StudioActor, type StudioRole } from "../session";
import {
  ALL_GATES,
  authorSubjects,
  availableActions,
  DEFAULT_FILTERS,
  facets,
  filterQueue,
  gateLabelKey,
  gateRows,
  gateSummary,
  homeStage,
  importedFrom,
  isProvisional,
  noteError,
  QUEUE_STAGES,
  REVIEW_CHAIN,
  STAGE_GATES,
  STAGE_ROLE,
  stageCounts,
  stageLabelKey,
} from "../workflow";

const actor = (role: StudioRole, subject = "staff-1"): StudioActor => ({ role, subject, expiresAt: null });

function lesson(over: Partial<LessonView> = {}): LessonView {
  return {
    lesson_id: "G4-MATH-001",
    title: { ur: "کسور", en: "Fractions" },
    grade: "G4",
    subject: "math",
    curriculum_pack: "PK-NCP",
    instructional_locales: ["ur"],
    state: "draft",
    version: 0,
    learning_outcomes: ["MATH-G4-N-01"],
    gates: [],
    ...over,
  };
}

const allGreen = ALL_GATES.map((gate) => ({ gate, passed: true, mode: "human" }));

// ---- workflow mirrors the backend ------------------------------------------------------------------

describe("workflow constants mirror the backend", () => {
  it("has the 5-stage chain with one reviewer role each, and 9 gates", () => {
    expect(REVIEW_CHAIN).toEqual(["subject_expert", "educational_qa", "accessibility", "language", "ai_safety"]);
    expect(Object.values(STAGE_ROLE)).toEqual([
      "subject_expert",
      "instructional_designer",
      "a11y_specialist",
      "language_editor",
      "safety_officer",
    ]);
    expect(ALL_GATES).toHaveLength(9);
    // Every human-certified gate is certified by exactly one stage.
    const certified = Object.values(STAGE_GATES).flat();
    expect(new Set(certified).size).toBe(certified.length);
  });

  it("lands each role on its own stage", () => {
    expect(homeStage("subject_author")).toBe("draft");
    expect(homeStage("curriculum_architect")).toBe("approved");
    expect(homeStage("language_editor")).toBe("language");
    expect(homeStage("safety_officer")).toBe("ai_safety");
  });

  it("labels every stage and gate in both locales", () => {
    for (const s of QUEUE_STAGES) {
      const key = stageLabelKey(s)!;
      expect(translate("en", key)).not.toBe(key);
      expect(translate("ur", key)).not.toBe(key);
    }
    for (const g of ALL_GATES) expect(translate("en", gateLabelKey(g)!)).not.toBe(g);
    expect(gateLabelKey("unknown")).toBeNull();
    for (const r of STUDIO_ROLES) expect(translate("ur", `studio.roles.${r}`)).not.toBe(`studio.roles.${r}`);
  });
});

describe("availableActions — never offer what the role cannot do", () => {
  it("offers a draft's author only Submit", () => {
    expect(availableActions(lesson(), actor("subject_author")).map((o) => o.action)).toEqual(["submit"]);
    for (const role of STUDIO_ROLES.filter((r) => r !== "subject_author")) {
      expect(availableActions(lesson(), actor(role))).toEqual([]);
    }
  });

  it("disables Submit while automated validation is failing", () => {
    const failing: ValidationResult = { ok: false, structural: [], gates: [] };
    const [submit] = availableActions(lesson(), actor("subject_author"), failing);
    expect(submit).toMatchObject({ action: "submit", enabled: false, reason: "studio.actions.reason.validationFailing" });
  });

  it("offers approve / request changes only to the stage's own reviewer, both requiring a reason", () => {
    for (const stage of REVIEW_CHAIN) {
      const l = lesson({ state: stage });
      for (const role of STUDIO_ROLES) {
        const actions = availableActions(l, actor(role));
        if (role === STAGE_ROLE[stage]) {
          expect(actions.map((a) => a.action)).toEqual(["approve", "request_changes"]);
          expect(actions.every((a) => a.requiresNote && a.enabled)).toBe(true);
        } else {
          expect(actions).toEqual([]);
        }
      }
    }
  });

  it("blocks self-approval when the reviewer's role authored the lesson", () => {
    const l = lesson({ state: "language", metadata: { author_role: "language_editor" } });
    const actions = availableActions(l, actor("language_editor"));
    expect(actions.every((a) => !a.enabled && a.reason === "studio.actions.reason.selfApproval")).toBe(true);
  });

  it("blocks self-approval by person: the recorded author or any submitter, whatever their role", () => {
    const l = lesson({
      state: "subject_expert",
      metadata: { author_role: "subject_author", author_subject: "staff-a" },
      workflow: {
        state: "subject_expert",
        history: [{ from_state: "draft", to_state: "subject_expert", action: "submit", actor_role: "subject_author", actor_subject: "staff-b", at: 1 }],
      },
    });
    expect([...authorSubjects(l)].sort()).toEqual(["staff-a", "staff-b"]);
    for (const who of ["staff-a", "staff-b"]) {
      const actions = availableActions(l, actor("subject_expert", who));
      expect(actions.every((a) => !a.enabled && a.reason === "studio.actions.reason.selfApproval")).toBe(true);
    }
    expect(availableActions(l, actor("subject_expert", "staff-c")).every((a) => a.enabled)).toBe(true);
  });

  it("offers Publish only to the architect on an approved lesson, naming the blocking gates", () => {
    const missing = lesson({ state: "approved", gates: allGreen.filter((g) => g.gate !== "ai_safety" && g.gate !== "readability") });
    const publish = availableActions(missing, actor("curriculum_architect")).find((a) => a.action === "publish")!;
    expect(publish.enabled).toBe(false);
    expect(publish.blockingGates).toEqual(["ai_safety", "readability"]);
    expect(publish.reason).toBe("studio.actions.reason.gatesNotGreen");

    const ready = availableActions(lesson({ state: "approved", gates: allGreen }), actor("curriculum_architect"));
    expect(ready.find((a) => a.action === "publish")).toMatchObject({ enabled: true, blockingGates: [] });
    expect(availableActions(lesson({ state: "approved", gates: allGreen }), actor("safety_officer"))).toEqual([]);
  });

  it("treats a failed gate as blocking, not just a missing one", () => {
    const gates = allGreen.map((g) => (g.gate === "language" ? { ...g, passed: false } : g));
    const publish = availableActions(lesson({ state: "approved", gates }), actor("curriculum_architect")).find((a) => a.action === "publish")!;
    expect(publish.blockingGates).toEqual(["language"]);
  });

  it("offers rollback to the architect on approved or published lessons only", () => {
    expect(availableActions(lesson({ state: "published" }), actor("curriculum_architect")).map((a) => a.action)).toEqual(["rollback"]);
    expect(availableActions(lesson({ state: "draft" }), actor("curriculum_architect"))).toEqual([]);
  });

  it("requires a written reason for every human decision", () => {
    const [approve] = availableActions(lesson({ state: "subject_expert" }), actor("subject_expert"));
    expect(noteError(approve!, "")).toBe("studio.actions.noteRequired");
    expect(noteError(approve!, "  ok ")).toBe("studio.actions.noteRequired");
    expect(noteError(approve!, "Accurate and age-appropriate.")).toBeNull();
    const [submit] = availableActions(lesson(), actor("subject_author"));
    expect(noteError(submit!, "")).toBeNull();
  });
});

describe("gates", () => {
  it("shows all 9 gates; unrecorded ones are 'not run', never passed", () => {
    const rows = gateRows([{ gate: "language", passed: true, mode: "human", reviewer_role: "language_editor" }]);
    expect(rows).toHaveLength(9);
    expect(rows.find((r) => r.gate === "language")).toMatchObject({ status: "passed", reviewerRole: "language_editor", certifiedAt: "language" });
    expect(rows.filter((r) => r.status === "not-run")).toHaveLength(8);
  });

  it("merges validation: a fresh failing check overrides a recorded pass and carries findings", () => {
    const validation: ValidationResult = {
      ok: false,
      structural: [],
      gates: [
        { gate: "readability", passed: false, findings: ["sentences too long"] },
        { gate: "performance", passed: true, findings: [] },
        { gate: "accessibility", passed: true, findings: [] },
      ],
    };
    const rows = gateRows([{ gate: "readability", passed: true }], validation);
    expect(rows.find((r) => r.gate === "readability")).toMatchObject({ status: "failed", findings: ["sentences too long"], mode: "auto" });
    expect(rows.find((r) => r.gate === "performance")!.status).toBe("passed");
    // Accessibility also needs a human: a passing pre-check alone is not a pass.
    expect(rows.find((r) => r.gate === "accessibility")).toMatchObject({ status: "not-run", mode: "auto+human" });
  });

  it("carries the certifying reviewer's identity and time", () => {
    const rows = gateRows([{ gate: "ai_safety", passed: true, mode: "human", reviewer_role: "safety_officer", reviewer_subject: "staff-9", at: 1700000000 }]);
    expect(rows.find((r) => r.gate === "ai_safety")).toMatchObject({ reviewerRole: "safety_officer", reviewerSubject: "staff-9", certifiedOn: 1700000000 });
    // The backend sends "" for an automated result: no identity is invented.
    const auto = gateRows([{ gate: "readability", passed: true, mode: "auto", reviewer_role: "", reviewer_subject: "" }]);
    expect(auto.find((r) => r.gate === "readability")).toMatchObject({ reviewerRole: null, reviewerSubject: null });
  });

  it("summarises", () => {
    expect(gateSummary(allGreen)).toEqual({ passed: 9, total: 9, allGreen: true });
    expect(gateSummary([{ gate: "language", passed: false }]).passed).toBe(0);
  });
});

describe("queue", () => {
  const provisional = { tags: ["provisional", "content-status:provisional-pending-review", "imported-from:G4 doc §2.1"] };
  const lessons = [
    lesson({ lesson_id: "B", state: "language", subject: "urdu", metadata: provisional }),
    lesson({ lesson_id: "A", state: "language", subject: "math", gates: allGreen }),
    lesson({ lesson_id: "C", state: "draft", curriculum_pack: "OTHER" }),
  ];

  it("filters by stage, subject, pack, provisional and gates, sorted by id", () => {
    const base = { ...DEFAULT_FILTERS, stage: "language" as const };
    expect(filterQueue(lessons, base).map((l) => l.lesson_id)).toEqual(["A", "B"]);
    expect(filterQueue(lessons, { ...base, subject: "urdu" }).map((l) => l.lesson_id)).toEqual(["B"]);
    expect(filterQueue(lessons, { ...base, provisional: "only" }).map((l) => l.lesson_id)).toEqual(["B"]);
    expect(filterQueue(lessons, { ...base, provisional: "exclude" }).map((l) => l.lesson_id)).toEqual(["A"]);
    expect(filterQueue(lessons, { ...base, gates: "all-green" }).map((l) => l.lesson_id)).toEqual(["A"]);
    expect(filterQueue(lessons, { ...base, gates: "not-green" }).map((l) => l.lesson_id)).toEqual(["B"]);
    expect(filterQueue(lessons, { ...DEFAULT_FILTERS, stage: "draft", pack: "OTHER" }).map((l) => l.lesson_id)).toEqual(["C"]);
    expect(filterQueue(lessons, { ...base, search: "کسور" })).toHaveLength(2);
    expect(filterQueue(lessons, { ...base, search: "math-g4" })).toHaveLength(2);
  });

  it("counts every stage and lists facets", () => {
    const counts = stageCounts(lessons);
    expect(counts.language).toBe(2);
    expect(counts.draft).toBe(1);
    expect(counts.published).toBe(0);
    expect(facets(lessons)).toEqual({ subjects: ["math", "urdu"], packs: ["OTHER", "PK-NCP"] });
  });

  it("recognises provisional imports and their sources", () => {
    expect(isProvisional(lessons[0]!)).toBe(true);
    expect(importedFrom(lessons[0]!)).toEqual(["G4 doc §2.1"]);
    expect(isProvisional(lessons[1]!)).toBe(false);
    // Without tags from the API, nothing is claimed provisional.
    expect(isProvisional(lesson())).toBe(false);
  });
});

// ---- preview ---------------------------------------------------------------------------------------

const RICH = lesson({
  student_explanation: { text: { ur: "کسر پورے کا حصہ ہے۔", en: "A fraction is part of a whole." } },
  worked_examples: [{ prompt: { text: { ur: "مثال", en: "Example" } }, steps: [{ text: { ur: "قدم ۱", en: "" } }] }],
  practice_questions: [
    {
      item_id: "q1",
      stem: { text: { ur: "آدھا کیا ہے؟", en: "What is a half?" } },
      options: [{ text: { ur: "۱/۲", en: "1/2" } }, { text: { ur: "۱/۳", en: "1/3" } }],
      hints: [{ hint: { text: { ur: "دو برابر حصے", en: "Two equal parts" } } }, { hint: { text: { ur: "ایک حصہ", en: "One part" } } }],
    },
  ],
});

describe("learner preview reuses the lesson player", () => {
  it("reports whether the API returned content", () => {
    expect(hasContent(lesson())).toBe(false);
    expect(hasContent(RICH)).toBe(true);
  });

  it("paces the lesson through the player's own reducer and step rules", () => {
    const teach = learnerPreview(RICH, "ur");
    const s = playerReducer(initialPlayerState, { type: "taught", objective: RICH.lesson_id, teach });
    expect(s.phase).toBe("presenting");
    expect(presentationSteps(s).map((u) => u.text)).toEqual(["کسور", "کسر پورے کا حصہ ہے۔", "مثال", "قدم ۱"]);
    const last = [1, 2, 3].reduce((acc) => playerReducer(acc, { type: "nextStep" }), s);
    expect(isLastStep(last)).toBe(true);
  });

  it("drops a missing translation from the steps exactly as a child would see it", () => {
    const teach = learnerPreview(RICH, "en");
    const s = playerReducer(initialPlayerState, { type: "taught", objective: "x", teach });
    expect(presentationSteps(s).map((u) => u.text)).toEqual(["Fractions", "A fraction is part of a whole.", "Example"]);
  });

  it("maps items with options and the authored hint count, and lists the ladder in order", () => {
    const teach = learnerPreview(RICH, "ur");
    expect(teach.items).toEqual([{ item_ref: "q1", prompt: { ur: "آدھا کیا ہے؟" }, options: ["۱/۲", "۱/۳"], hint_count: 2 }]);
    expect(itemHints(RICH, "q1", "en")).toEqual(["Two equal parts", "One part"]);
  });
});

describe("localized fields side by side", () => {
  it("uses declared instructional locales, else the pack's, plus any carried locale", () => {
    expect(lessonLocales(lesson({ instructional_locales: ["ur"] }))).toEqual(["ur", "en"]);
    const pack = { pack_id: "X", version: "1", country: "PK", education_system: "x", language_of_instruction: "ur", instructional_locales: ["ur", "en"], locales: [] };
    expect(lessonLocales(lesson({ instructional_locales: [], title: { ur: "a" } }), pack)).toEqual(["ur", "en"]);
  });

  it("flags every missing translation", () => {
    const rows = localizedRows(RICH, ["ur", "en"]);
    const step = rows.find((r) => r.field === "worked_examples[0].steps[0]")!;
    expect(step.incomplete).toBe(true);
    expect(step.values).toEqual([
      { locale: "ur", text: "قدم ۱", missing: false },
      { locale: "en", text: "", missing: true },
    ]);
    expect(rows.find((r) => r.field === "q1.hints[1]")!.incomplete).toBe(false);
    expect(localizedRows(lesson(), ["ur", "en"]).map((r) => r.field)).toEqual(["title"]);
  });
});

describe("version history", () => {
  it("orders newest first and marks content changes by hash", () => {
    const rows = versionRows(
      [
        { version: 1, content_hash: "sha256:a", change_summary: "first", author_role: "curriculum_architect" },
        { version: 3, content_hash: "sha256:a", change_summary: "rollback", author_role: "curriculum_architect" },
        { version: 2, content_hash: "sha256:b", change_summary: "fix", author_role: "curriculum_architect" },
      ],
      3,
    );
    expect(rows.map((r) => [r.version, r.contentChanged, r.isCurrent])).toEqual([
      [3, true, true],
      [2, true, false],
      [1, true, false],
    ]);
    const same = versionRows(
      [
        { version: 1, content_hash: "h", change_summary: "", author_role: "a" },
        { version: 2, content_hash: "h", change_summary: "", author_role: "a" },
      ],
      2,
    );
    expect(same[0]!.contentChanged).toBe(false);
  });
});

// ---- draft form + session ---------------------------------------------------------------------------

describe("draft form", () => {
  const hierarchy = { grades: ["G4"], subjects_by_grade: { G4: ["math", "urdu"] } };

  it("requires the fields the create API needs", () => {
    expect(draftErrors(EMPTY_DRAFT, hierarchy)).toEqual({
      lessonId: "studio.draft.errors.lessonId",
      titles: "studio.draft.errors.title",
      grade: "studio.draft.errors.required",
      subject: "studio.draft.errors.required",
      outcomes: "studio.draft.errors.outcomes",
    });
  });

  it("checks grade and subject against the pack roster", () => {
    const form = { ...EMPTY_DRAFT, lessonId: "G4-1", titles: { ur: "a" }, grade: "G9", subject: "math", outcomes: "X" };
    expect(draftErrors(form, hierarchy).grade).toBe("studio.draft.errors.notInPack");
    expect(draftErrors({ ...form, grade: "G4", subject: "art" }, hierarchy).subject).toBe("studio.draft.errors.notInPack");
    expect(draftErrors({ ...form, grade: "G4" }, hierarchy)).toEqual({});
  });

  it("needs one title, in the pack's locales only; blank titles do not count", () => {
    const form = { ...EMPTY_DRAFT, lessonId: "G4-1", grade: "G4", subject: "math", outcomes: "X" };
    expect(draftErrors({ ...form, titles: { ur: "  ", en: "" } }, hierarchy).titles).toBe("studio.draft.errors.title");
    expect(draftErrors({ ...form, titles: { sd: "x" } }, hierarchy, ["ur", "en"]).titles).toBe("studio.draft.errors.locale");
    expect(draftErrors({ ...form, titles: { en: "Fractions" } }, hierarchy, ["ur", "en"]).titles).toBeUndefined();
  });

  it("offers the pack's declared locales", () => {
    const pack = {
      pack_id: "PK-NCP",
      version: "1",
      country: "PK",
      education_system: "NCP",
      language_of_instruction: "ur",
      instructional_locales: ["ur"],
      locales: [
        { tag: "ur", name: "Urdu", direction: "rtl" as const },
        { tag: "en", name: "English", direction: "ltr" as const },
      ],
    };
    expect(packLocales(pack).map((l) => l.tag)).toEqual(["ur", "en"]);
    expect(packLocales({ ...pack, locales: [] }).map((l) => l.tag)).toEqual(["ur"]);
    expect(packLocales(null)).toEqual([]);
  });

  it("parses outcomes and builds the contract body", () => {
    expect(parseOutcomes("A, B\nB  C")).toEqual(["A", "B", "C"]);
    const body = toDraftIn({ ...EMPTY_DRAFT, lessonId: " L1 ", titles: { ur: " ا ", en: "E", sd: " " }, pack: "PK-NCP", grade: "G4", subject: "math", outcomes: "A,B" });
    expect(body).toEqual({
      lesson_id: "L1",
      title: { ur: "ا", en: "E" },
      grade: "G4",
      subject: "math",
      curriculum_pack: "PK-NCP",
      learning_outcomes: ["A", "B"],
      provenance: { aligned_slo_codes: ["A", "B"] },
    });
  });
});

describe("staff token parsing (display only)", () => {
  const b64 = (o: object) => Buffer.from(JSON.stringify(o)).toString("base64url");
  const token = (claims: object) => `${b64({ alg: "EdDSA" })}.${b64(claims)}.sig`;

  it("reads subject, role and expiry", () => {
    expect(parseStudioToken(token({ sub: "rev-7", role: "language_editor", exp: 2000 }), 1000)).toEqual({
      ok: true,
      actor: { subject: "rev-7", role: "language_editor", expiresAt: 2000 },
    });
  });

  it("refuses malformed, non-studio and expired tokens", () => {
    expect(parseStudioToken("nope", 0)).toEqual({ ok: false, reason: "malformed" });
    expect(parseStudioToken(token({ role: "subject_expert" }), 0)).toEqual({ ok: false, reason: "malformed" });
    expect(parseStudioToken(token({ sub: "g", role: "guardian" }), 0)).toEqual({ ok: false, reason: "not-studio-role" });
    expect(parseStudioToken(token({ sub: "s", role: "subject_expert", exp: 10 }), 10)).toEqual({ ok: false, reason: "expired" });
  });
});

// ---- draft editing ------------------------------------------------------------------------------------

describe("draft editing builds a minimal, locale-keyed PATCH", () => {
  const draft = lesson({
    title: { ur: "کسور", en: "Fractions" },
    student_explanation: { text: { ur: "کسر حصہ ہے۔" } },
    etag: '"abc"',
  });

  it("starts from the draft's current localized fields", () => {
    const f = editableFields(draft);
    expect(f.title).toEqual({ ur: "کسور", en: "Fractions" });
    expect(f.student_explanation).toEqual({ ur: "کسر حصہ ہے۔" });
    expect(f.summary).toEqual({});
  });

  it("sends nothing when nothing changed (whitespace-only edits included)", () => {
    const f = editableFields(draft);
    expect(buildPatch(f, { ...f, title: { ur: " کسور ", en: "Fractions" } })).toBeNull();
  });

  it("sends only the changed locales, and an empty string to remove one", () => {
    const f = editableFields(draft);
    const edited = {
      ...f,
      title: { ur: "کسور", en: "" },
      student_explanation: { ur: "کسر حصہ ہے۔", en: "A fraction is a part." },
    };
    expect(buildPatch(f, edited)).toEqual({
      title: { en: "" },
      student_explanation: { en: "A fraction is a part." },
    });
  });

  it("refuses to remove every title", () => {
    const f = editableFields(draft);
    expect(editErrors({ ...f, title: { ur: " ", en: "" } })).toBe("studio.edit.titleRequired");
    expect(editErrors(f)).toBeNull();
  });
});

describe("version diff from published bodies", () => {
  const v1 = {
    lesson_id: "L",
    title: { text: { ur: "کسور", en: "Fractions" }, audio_ref: {} },
    worked_examples: [{ prompt: { text: { ur: "مثال" } }, steps: [] }],
    workflow: { state: "published", history: [{ at: 1 }] },
    version: 1,
  };
  const v2 = {
    lesson_id: "L",
    title: { text: { ur: "کسور", en: "Fractions and parts" }, audio_ref: {} },
    worked_examples: [{ prompt: { text: { ur: "مثال", en: "Example" } }, steps: [{ text: { ur: "قدم" } }] }],
    workflow: { state: "published", history: [{ at: 1 }, { at: 2 }] },
    version: 2,
  };

  it("lists added, removed and changed content leaves, ignoring workflow and version bookkeeping", () => {
    expect(diffBodies(v1, v2)).toEqual([
      { path: "title.text.en", kind: "changed", before: "Fractions", after: "Fractions and parts" },
      { path: "worked_examples[0].prompt.text.en", kind: "added", before: undefined, after: "Example" },
      { path: "worked_examples[0].steps[0].text.ur", kind: "added", before: undefined, after: "قدم" },
    ]);
    expect(diffBodies(v2, v1).find((d) => d.path === "worked_examples[0].prompt.text.en")!.kind).toBe("removed");
    expect(diffBodies(v1, v1)).toEqual([]);
    expect([...flatten(v1).keys()].some((k) => k.startsWith("workflow"))).toBe(false);
  });

  it("knows which locale a leaf is in, for lang/dir", () => {
    expect(leafLocale("title.text.ur")).toBe("ur");
    expect(leafLocale("practice_questions[0].stem.text.en-GB")).toBe("en-GB");
    expect(leafLocale("lesson_id")).toBeNull();
  });
});
