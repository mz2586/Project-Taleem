import { describe, expect, it } from "vitest";

import { translate } from "../../i18n/translate";
import { ApiError } from "../../student/types";
import { identityErrorKey } from "../errors";
import { formatDate, formatDateTime, formatList } from "../format";
import { gradeBandFor, gradeOption, nameProblem, pinProblem, sanitizePin } from "../learners";

const v = (detail: string) => new ApiError(422, { code: "VALIDATION_FAILED", detail });

describe("identityErrorKey", () => {
  it("network, rate limit, and non-API failures are the same everywhere", () => {
    expect(identityErrorKey(new ApiError(0, {}), "enrol")).toBe("auth.errors.offline");
    expect(identityErrorKey(new ApiError(429, {}), "learner-sign-in")).toBe("auth.errors.tooMany");
    expect(identityErrorKey(new Error("boom"), "consent")).toBe("auth.errors.generic");
  });

  it("never tells a stranger whether an email is registered at sign-in", () => {
    expect(identityErrorKey(new ApiError(401, {}), "guardian-sign-in")).toBe("auth.errors.guardianCredentials");
  });

  it("explains a consent-blocked child sign-in separately from a wrong PIN", () => {
    expect(identityErrorKey(new ApiError(403, { code: "CONSENT_REQUIRED" }), "learner-sign-in")).toBe("auth.errors.consentNeeded");
    expect(identityErrorKey(new ApiError(401, {}), "learner-sign-in")).toBe("auth.errors.learnerCredentials");
    expect(identityErrorKey(new ApiError(503, { code: "SERVICE_HALTED" }), "roster")).toBe("auth.errors.paused");
  });

  it("maps the server's English validation details to the guardian's language", () => {
    expect(identityErrorKey(v("a learner with this name already exists in your family"), "enrol")).toBe("auth.errors.duplicateName");
    expect(identityErrorKey(v("a guardian may enrol at most 12 learners"), "enrol")).toBe("auth.errors.familyFull");
    expect(identityErrorKey(v("PIN is too easily guessed; choose another"), "pin-reset")).toBe("auth.errors.pinTooEasy");
    expect(identityErrorKey(v("PIN must be 4 to 6 digits"), "enrol")).toBe("auth.errors.pinFormat");
    expect(identityErrorKey(v("passphrase must be at least 10 characters"), "register")).toBe("auth.errors.passphraseShort");
    expect(identityErrorKey(v("something new"), "register")).toBe("auth.errors.checkDetails");
    expect(identityErrorKey(new ApiError(409, {}), "register")).toBe("auth.errors.emailTaken");
  });

  it("every key it can return exists in both catalogs", () => {
    const keys = [
      identityErrorKey(v("x"), "enrol"),
      identityErrorKey(new ApiError(404, {}), "pin-reset"),
      identityErrorKey(new ApiError(403, {}), "consent"),
      identityErrorKey(new ApiError(401, {}), "load"),
    ];
    for (const key of keys) {
      expect(translate("en", key)).not.toBe(key);
      expect(translate("ur", key)).not.toBe(key);
    }
  });
});

describe("learner rules", () => {
  it("derives the API grade band from the grade", () => {
    expect([0, 2, 3, 5, 6, 12].map(gradeBandFor)).toEqual(["early", "early", "middle", "middle", "senior", "senior"]);
  });
  it("labels kindergarten and grades", () => {
    expect(translate("en", gradeOption(0).key)).toBe("Kindergarten");
    const g = gradeOption(4);
    expect(translate("en", g.key, g.params)).toBe("Grade 4");
  });
  it("checks PINs and names before a round trip", () => {
    expect(pinProblem("")).toBe("empty");
    expect(pinProblem("12")).toBe("format");
    expect(pinProblem("4821")).toBeNull();
    expect(sanitizePin("12a3-4567")).toBe("123456");
    expect(nameProblem("  ")).toBe("empty");
    expect(nameProblem("x".repeat(61))).toBe("long");
    expect(nameProblem("Ali")).toBeNull();
  });
});

describe("guardian date and list formatting", () => {
  const AT = 1_761_134_400; // 2025-10-22 12:00 UTC
  it("formats dates in the interface locale", () => {
    expect(formatDate(AT, "en", { timeZone: "UTC" })).toBe("Oct 22, 2025");
    expect(formatDateTime(AT, "en", { timeZone: "UTC" })).toMatch(/Oct 22, 2025.*12:00/);
    expect(formatDate(AT, "ur", { timeZone: "UTC", digits: "native" })).toContain("۲۰۲۵");
    expect(formatDate(Number.NaN, "en")).toBe("");
  });
  it("joins lists the way the language does", () => {
    expect(formatList(["A", "B", "C"], "en")).toBe("A, B, and C");
  });
});
