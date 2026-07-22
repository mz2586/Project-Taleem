import { describe, expect, it } from "vitest";

import { uuid7 } from "../ids";

describe("uuid7", () => {
  it("has the canonical shape and version/variant nibbles", () => {
    const id = uuid7(0x0123456789ab, new Uint8Array([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]));
    expect(id).toMatch(/^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
    // The 48-bit timestamp prefix is encoded big-endian at the front (across the first hyphen).
    expect(id.replace(/-/g, "").startsWith("0123456789ab")).toBe(true);
  });

  it("is time-ordered: a later timestamp sorts after an earlier one", () => {
    const rand = new Uint8Array(10);
    const early = uuid7(1000, rand);
    const late = uuid7(2000, rand);
    expect(early < late).toBe(true);
  });
});
