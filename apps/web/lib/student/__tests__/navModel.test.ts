import { describe, expect, it } from "vitest";

import { EARLY_NAV, FULL_NAV, isActive, navItemsFor } from "../navModel";

describe("navItemsFor", () => {
  it("gives the early band a reduced destination set", () => {
    const early = navItemsFor("early");
    expect(early).toBe(EARLY_NAV);
    expect(early.map((i) => i.label)).toEqual(["Today", "Progress", "Profile"]);
  });

  it("gives middle and senior bands the full set", () => {
    expect(navItemsFor("middle")).toBe(FULL_NAV);
    expect(navItemsFor("senior")).toBe(FULL_NAV);
    expect(FULL_NAV).toHaveLength(5);
  });

  it("keeps early labels in sync with the full set (shared objects)", () => {
    // Early items are the same references as their FULL counterparts, so a label change propagates.
    expect(EARLY_NAV[0]).toBe(FULL_NAV[0]);
    expect(EARLY_NAV[1]).toBe(FULL_NAV[3]);
    expect(EARLY_NAV[2]).toBe(FULL_NAV[4]);
  });
});

describe("isActive", () => {
  it("matches an exact path", () => {
    expect(isActive("/student/today", "/student/today")).toBe(true);
  });

  it("matches a nested path by prefix", () => {
    expect(isActive("/student/today/detail", "/student/today")).toBe(true);
  });

  it("does not match a different destination", () => {
    expect(isActive("/student/progress", "/student/today")).toBe(false);
  });

  it("is false for a null/undefined pathname", () => {
    expect(isActive(null, "/student/today")).toBe(false);
    expect(isActive(undefined, "/student/today")).toBe(false);
  });
});
