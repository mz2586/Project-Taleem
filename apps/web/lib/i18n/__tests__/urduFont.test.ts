// Regression guard for the self-hosted Urdu font: the CSS points at a file that exists, is a real
// WOFF2, ships with its licence, is precached for offline use, and is scoped to Urdu.
import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const WEB = join(__dirname, "..", "..", "..");
const FONT_URL = "/fonts/NotoNastaliqUrdu-Regular.arabic.woff2";
const css = readFileSync(join(WEB, "design-system", "fonts.css"), "utf8");

describe("self-hosted Urdu font", () => {
  it("is a WOFF2 under 80 KB (2G budget)", () => {
    const file = join(WEB, "public", FONT_URL);
    const head = readFileSync(file).subarray(0, 4).toString("latin1");
    expect(head).toBe("wOF2");
    expect(statSync(file).size).toBeLessThan(80 * 1024);
  });

  it("ships the SIL OFL 1.1 licence and its provenance", () => {
    expect(readFileSync(join(WEB, "public", "fonts", "OFL.txt"), "utf8")).toContain("SIL Open Font License, Version 1.1");
    expect(readFileSync(join(WEB, "public", "fonts", "FONTS.txt"), "utf8")).toContain("NotoNastaliqUrdu-v4.000");
  });

  it("is declared with swap, local() first, an Arabic-script unicode-range, and applied to :lang(ur)", () => {
    expect(css).toContain(`url("${FONT_URL}")`);
    expect(css).toContain("font-display: swap");
    expect(css.indexOf('local("Noto Nastaliq Urdu")')).toBeLessThan(css.indexOf(FONT_URL));
    expect(css).toMatch(/unicode-range:[^;]*U\+0600-06FF/);
    expect(css).not.toMatch(/unicode-range:[^;]*U\+0041/); // no Latin letters
    expect(css).toMatch(/:lang\(ur\)\s*\{[^}]*font-family: var\(--font-urdu\)/);
  });

  it("is precached by the service worker so Urdu renders offline", () => {
    const sw = readFileSync(join(WEB, "public", "sw.js"), "utf8");
    expect(sw).toContain(`"${FONT_URL}"`);
    expect(sw).toMatch(/APP_SHELL = \[[^\]]*URDU_FONT/);
  });

  it("is loaded by the root layout", () => {
    expect(readFileSync(join(WEB, "app", "layout.tsx"), "utf8")).toContain('import "../design-system/fonts.css"');
  });
});
