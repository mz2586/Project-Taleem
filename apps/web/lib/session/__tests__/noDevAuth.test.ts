// A regression guard, not a unit test.
//
// The two development auth stubs (`NEXT_PUBLIC_DEV_STUDENT_TOKEN`, `NEXT_PUBLIC_DEV_GUARDIAN_TOKEN`
// and the synthetic learner behind them) were the reason this app could not be shown to a real
// child: both config files said so in their own comments. They are gone, and this test exists so
// they cannot come back by accident — a reintroduced stub would ship a hand-minted bearer token to
// every browser that loads the bundle.

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = join(__dirname, "..", "..", "..");
const SEARCHED = ["app", "components", "lib", "design-system"];
const BANNED = [
  "NEXT_PUBLIC_DEV_STUDENT_TOKEN",
  "NEXT_PUBLIC_DEV_GUARDIAN_TOKEN",
  "NEXT_PUBLIC_DEV_STUDENT_REF",
  "NEXT_PUBLIC_DEV_GUARDIAN_REF",
  "DEV_LEARNER",
  "SYNTHETIC_STUDENT_REF",
];

function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules" || entry === ".next") continue;
      out.push(...sourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry) && !full.includes("__tests__")) {
      out.push(full);
    }
  }
  return out;
}

describe("no development auth stubs remain", () => {
  const files = SEARCHED.flatMap((dir) => sourceFiles(join(ROOT, dir)));

  it("finds source files to check", () => {
    expect(files.length).toBeGreaterThan(20);
  });

  it.each(BANNED)("does not reference %s anywhere", (symbol) => {
    const offenders = files.filter((file) => readFileSync(file, "utf8").includes(symbol));
    expect(offenders).toEqual([]);
  });
});
