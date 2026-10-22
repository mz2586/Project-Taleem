import { afterEach, describe, expect, it } from "vitest";

import {
  BUILTIN_DEFAULT_LOCALE,
  defaultLocale,
  directionOf,
  matchLocale,
  resolveLocale,
  resolveUiLocale,
  SUPPORTED_LOCALES,
} from "../config";
import { contentAttrs, opposesInterface, pickLocalized, scriptDirection } from "../content";
import { formatNumber, formatPercent, intlLocale } from "../format";
import { CATALOGS } from "../messages";
import { readUiLocalePreference, subscribeUiLocalePreference, writeUiLocalePreference } from "../preference";
import { createTranslator, translate } from "../translate";

type Tree = { [key: string]: string | Tree };

/** Every leaf path of a catalog, e.g. "student.today.start". Empty namespaces appear as "ns.". */
function leafPaths(tree: Tree, prefix = ""): string[] {
  const entries = Object.entries(tree);
  if (entries.length === 0) return [`${prefix}`];
  return entries.flatMap(([key, value]) =>
    typeof value === "string" ? [`${prefix}${key}`] : leafPaths(value, `${prefix}${key}.`),
  );
}

function leaves(tree: Tree): string[] {
  return Object.values(tree).flatMap((v) => (typeof v === "string" ? [v] : leaves(v)));
}

function placeholders(text: string): string[] {
  return [...text.matchAll(/\{(\w+)\}/g)].map((m) => m[1]!).sort();
}

function valueAt(tree: Tree, path: string): string {
  return path.split(".").reduce<string | Tree>((node, part) => (node as Tree)[part]!, tree) as string;
}

describe("catalog parity", () => {
  const reference = leafPaths(CATALOGS.en as unknown as Tree).sort();

  it("has a catalog for every supported locale and nothing else", () => {
    expect(Object.keys(CATALOGS).sort()).toEqual([...SUPPORTED_LOCALES].sort());
  });

  it.each(SUPPORTED_LOCALES)("%s has exactly the same keys as en", (locale) => {
    expect(leafPaths(CATALOGS[locale] as unknown as Tree).sort()).toEqual(reference);
  });

  it.each(SUPPORTED_LOCALES)("%s has no empty strings", (locale) => {
    for (const text of leaves(CATALOGS[locale] as unknown as Tree)) expect(text.trim()).not.toBe("");
  });

  it.each(SUPPORTED_LOCALES)("%s uses the same placeholders as en for every key", (locale) => {
    for (const path of reference.filter((p) => !p.endsWith("."))) {
      const ours = valueAt(CATALOGS[locale] as unknown as Tree, path);
      const theirs = valueAt(CATALOGS.en as unknown as Tree, path);
      expect({ path, vars: placeholders(ours) }).toEqual({ path, vars: placeholders(theirs) });
    }
  });

  it("reserves extensible namespaces, including guardian and auth", () => {
    for (const locale of SUPPORTED_LOCALES) {
      expect(Object.keys(CATALOGS[locale])).toEqual(["common", "home", "student", "guardian", "auth"]);
    }
  });
});

describe("direction mapping", () => {
  it("maps the catalogued locales", () => {
    expect(directionOf("ur")).toBe("rtl");
    expect(directionOf("en")).toBe("ltr");
  });

  it("maps region-tagged and uncatalogued tags by their base language", () => {
    expect(directionOf("ur-PK")).toBe("rtl");
    expect(directionOf("en-GB")).toBe("ltr");
    expect(directionOf("ar-EG")).toBe("rtl");
    expect(directionOf("fa")).toBe("rtl");
    expect(directionOf("fr")).toBe("ltr");
  });

  it("treats empty or missing as ltr", () => {
    expect(directionOf("")).toBe("ltr");
    expect(directionOf(undefined)).toBe("ltr");
  });
});

describe("locale resolution and fallback", () => {
  it("matches exact, then base language", () => {
    expect(matchLocale("en")).toBe("en");
    expect(matchLocale("EN-us")).toBe("en");
    expect(matchLocale("ur_PK")).toBe("ur");
    expect(matchLocale("fr")).toBeNull();
    expect(matchLocale(null)).toBeNull();
  });

  it("falls back for an unknown locale", () => {
    expect(resolveLocale("fr", "en")).toBe("en");
    expect(resolveLocale("", "ur")).toBe("ur");
    expect(resolveLocale("de-DE")).toBe(defaultLocale());
  });

  it("reads the configured default, ignoring an unsupported value", () => {
    expect(defaultLocale("en")).toBe("en");
    expect(defaultLocale("xx")).toBe(BUILTIN_DEFAULT_LOCALE);
    expect(defaultLocale(undefined)).toBe(BUILTIN_DEFAULT_LOCALE);
    expect(BUILTIN_DEFAULT_LOCALE).toBe("ur");
  });

  it("prefers the device choice, then the account, then the default", () => {
    expect(resolveUiLocale({ preference: "en", account: "ur", fallback: "ur" })).toBe("en");
    expect(resolveUiLocale({ preference: null, account: "en-GB", fallback: "ur" })).toBe("en");
    expect(resolveUiLocale({ preference: "fr", account: "xx", fallback: "en" })).toBe("en");
    expect(resolveUiLocale({})).toBe(defaultLocale());
  });
});

describe("translate", () => {
  it("looks up nested keys per locale", () => {
    expect(translate("en", "student.nav.today")).toBe("Today");
    expect(translate("ur", "student.nav.today")).toBe("آج");
  });

  it("interpolates and formats numbers for the locale", () => {
    const t = createTranslator("en");
    expect(t("student.session.stepOf", { current: 2, total: 5 })).toBe("Step 2 of 5");
    expect(t("student.today.greeting", { name: "Ayesha" })).toBe("Assalam-o-Alaikum, Ayesha");
    expect(createTranslator("ur", "native")("student.session.stepOf", { current: 2, total: 5 })).toBe(
      "مرحلہ ۲ از ۵",
    );
  });

  it("leaves an unsupplied placeholder visible rather than blank", () => {
    expect(translate("en", "student.session.stepOf", { current: 1 })).toBe("Step 1 of {total}");
  });

  it("falls back to the key for an unknown key at run time", () => {
    expect(translate("en", "no.such.key" as never)).toBe("no.such.key");
  });
});

describe("number formatting", () => {
  it("defaults to Western digits for every locale", () => {
    expect(formatNumber(1234, "en")).toBe("1,234");
    expect(formatNumber(1234, "ur")).toMatch(/^1.?234$/);
    expect(formatNumber(7, "ur")).toBe("7");
  });

  it("uses Extended Arabic-Indic digits for Urdu when native digits are asked for", () => {
    expect(formatNumber(1234567890, "ur", { digits: "native" })).toMatch(/^[۰-۹٬,]+$/);
    expect(formatNumber(42, "ur", { digits: "native" })).toBe("۴۲");
    expect(intlLocale("ur", "native")).toBe("ur-u-nu-arabext");
  });

  it("keeps Western digits for a locale without native ones", () => {
    expect(formatNumber(42, "en", { digits: "native" })).toBe("42");
    expect(intlLocale("en", "native")).toBe("en-u-nu-latn");
  });

  it("formats ratios as clamped whole percentages", () => {
    expect(formatPercent(0.756, "en")).toBe("76%");
    expect(formatPercent(1.4, "en")).toBe("100%");
    expect(formatPercent(Number.NaN, "en")).toBe("0%");
    expect(formatPercent(0.5, "ur", { digits: "native" })).toMatch(/۵۰/);
  });
});

describe("content language is independent of the interface", () => {
  it("picks content by the instructional preference, never by UI locale", () => {
    expect(pickLocalized({ en: "One", ur: "ایک" }, ["ur", "en"])).toEqual({ text: "ایک", locale: "ur" });
    expect(pickLocalized({ en: "One", ur: "" }, ["ur", "en"])).toEqual({ text: "One", locale: "en" });
    expect(pickLocalized({ ar: "واحد" }, ["ur", "en"])).toEqual({ text: "واحد", locale: "ar" });
    expect(pickLocalized({}, ["ur"])).toBeNull();
    expect(pickLocalized(undefined, ["ur"])).toBeNull();
  });

  it("detects direction from the first strong character", () => {
    expect(scriptDirection("کسر کیا ہے؟")).toBe("rtl");
    expect(scriptDirection("What is a fraction?")).toBe("ltr");
    expect(scriptDirection("12 + 3 = ؟ جمع")).toBe("rtl");
    expect(scriptDirection("12 + 3")).toBeNull();
  });

  it("marks an Urdu lesson block rtl inside an English (ltr) interface", () => {
    const uiDir = directionOf("en");
    const block = contentAttrs({ locale: "ur" });
    expect(uiDir).toBe("ltr");
    expect(block).toEqual({ lang: "ur", dir: "rtl" });
    expect(opposesInterface(uiDir, block)).toBe(true);
  });

  it("marks an English lesson block ltr inside an Urdu (rtl) interface", () => {
    const uiDir = directionOf("ur");
    const block = contentAttrs({ text: "Add the two numbers." });
    expect(block).toEqual({ dir: "ltr" });
    expect(opposesInterface(uiDir, block)).toBe(true);
  });

  it("does not flag content that matches the interface, nor neutral text", () => {
    expect(opposesInterface("rtl", contentAttrs({ locale: "ur-PK" }))).toBe(false);
    expect(contentAttrs({ text: "42" })).toEqual({ dir: "auto" });
    expect(opposesInterface("ltr", contentAttrs({ text: "42" }))).toBe(false);
  });
});

describe("device interface-locale preference", () => {
  afterEach(() => writeUiLocalePreference(null));

  it("round-trips, ignores junk, and notifies subscribers", () => {
    const seen: (string | null)[] = [];
    const off = subscribeUiLocalePreference((l) => seen.push(l));
    expect(readUiLocalePreference()).toBeNull();
    writeUiLocalePreference("en");
    expect(readUiLocalePreference()).toBe("en");
    window.localStorage.setItem("taleem.uiLocale.v1", "klingon");
    expect(readUiLocalePreference()).toBeNull();
    writeUiLocalePreference(null);
    off();
    writeUiLocalePreference("ur");
    expect(seen).toEqual(["en", null]);
  });
});
