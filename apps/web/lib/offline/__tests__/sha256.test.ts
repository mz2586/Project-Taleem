import { describe, expect, it } from "vitest";

import { canonicalJson, contentHash, verifyContent } from "../sha256";
import type { OfflineContent } from "../types";

function content(explanationEn: string): OfflineContent {
  return {
    lesson_id: "L1",
    objective_code: "MATH-G4-FR-01",
    title: { ur: "کسر", en: "Fractions" },
    explanation: { ur: "حصہ", en: explanationEn },
    worked_example_steps: ["one", "two"],
    practice_items: [
      { item_ref: "p1", objective_code: "MATH-G4-FR-01", prompt: { en: "?" }, options: ["a"], hints: [] },
    ],
    homework_items: [],
    assessment_formative: [],
    summative_mentor_mediated: true,
  };
}

describe("canonical json + sha256", () => {
  it("sorts keys and uses compact separators (parity with Python json.dumps)", () => {
    // Python: json.dumps({"b":[1,2],"a":1,"t":"کسر"}, sort_keys=True,
    //                     separators=(",",":"), ensure_ascii=False)
    expect(canonicalJson({ b: [1, 2], a: 1, t: "کسر" })).toBe('{"a":1,"b":[1,2],"t":"کسر"}');
  });

  it("computes a stable hex digest", async () => {
    const h = await contentHash(content("A fraction is an equal part."));
    expect(h).toMatch(/^[0-9a-f]{64}$/);
    const again = await contentHash(content("A fraction is an equal part."));
    expect(again).toBe(h);
  });

  it("changes the hash when content changes (cache invalidation)", async () => {
    const a = await contentHash(content("A fraction is an equal part."));
    const b = await contentHash(content("A fraction is one equal part of a whole."));
    expect(a).not.toBe(b);
  });

  it("verifies matching content and rejects tampered content (integrity)", async () => {
    const c = content("A fraction is an equal part.");
    const good = await contentHash(c);
    expect(await verifyContent(c, good)).toBe(true);
    const tampered = content("tampered");
    expect(await verifyContent(tampered, good)).toBe(false);
  });
});
