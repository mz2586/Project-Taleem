// The "Demo account" badge (DEMO_COHORT_CONTRACT §2): shown only for a token whose informational
// `cohort` claim is "demo", in Urdu and English. The claim is decoded for display only.
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DemoAccountBadgeView } from "@/components/session/DemoAccountBadge";

import { createTranslator } from "../../i18n/translate";
import { isDemoToken, tokenCohort } from "../cohort";

function b64url(value: string): string {
  return Buffer.from(value, "utf8").toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function jwt(claims: Record<string, unknown>): string {
  return `${b64url(JSON.stringify({ alg: "EdDSA", typ: "JWT" }))}.${b64url(JSON.stringify(claims))}.sig`;
}

describe("tokenCohort", () => {
  it("reads the demo claim", () => {
    const token = jwt({ sub: "stu_1", role: "student", cohort: "demo" });
    expect(tokenCohort(token)).toBe("demo");
    expect(isDemoToken(token)).toBe(true);
  });

  it("is empty for a real account's token", () => {
    expect(tokenCohort(jwt({ sub: "gdn_1", role: "guardian" }))).toBe("");
    expect(isDemoToken(jwt({ sub: "gdn_1", role: "guardian" }))).toBe(false);
  });

  it("never throws on malformed input", () => {
    for (const bad of [undefined, null, "", "abc", "a.b", "a.!!!.c", `x.${b64url("not json")}.y`]) {
      expect(isDemoToken(bad)).toBe(false);
    }
    expect(isDemoToken(jwt({ cohort: 7 }))).toBe(false);
    expect(isDemoToken(jwt({ cohort: "DEMO" }))).toBe(false);
  });
});

describe("DemoAccountBadgeView", () => {
  it("labels the badge in English", () => {
    const html = renderToStaticMarkup(createElement(DemoAccountBadgeView, { t: createTranslator("en") }));
    expect(html).toContain("Demo account");
    expect(html).toContain("data-demo-badge");
    expect(html).toContain("not a real child");
  });

  it("labels the badge in Urdu", () => {
    const html = renderToStaticMarkup(createElement(DemoAccountBadgeView, { t: createTranslator("ur") }));
    expect(html).toContain("ڈیمو اکاؤنٹ");
    expect(html).not.toContain("Demo account");
  });
});
