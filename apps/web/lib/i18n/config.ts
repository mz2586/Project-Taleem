// Interface-locale configuration. Pure — no React, no browser — so it is safe in server components
// and unit tests.
//
// Two ideas are kept apart on purpose:
//
// - The **interface locale** is the language of the app's own chrome (buttons, headings, messages).
//   It is a person's preference: chosen on this device, else the account's locale, else the
//   deployment default. Only locales with a full message catalog can be interface locales.
// - The **content locale** is the language a lesson was authored in. It comes from the content and is
//   never derived from the interface locale (or vice versa) — an English interface can show an Urdu
//   lesson, and that lesson keeps its own `lang` and `dir`. See `content.ts`.
//
// Urdu is the launch default, not an assumption baked into components: every direction decision
// below goes through `directionOf`, which works for any BCP 47 tag.

export const SUPPORTED_LOCALES = ["ur", "en"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];
export type Direction = "rtl" | "ltr";

export interface LocaleMeta {
  /** The language's name in its own language — what a switcher shows. */
  nativeName: string;
  dir: Direction;
}

export const LOCALE_META: Record<Locale, LocaleMeta> = {
  ur: { nativeName: "اردو", dir: "rtl" },
  en: { nativeName: "English", dir: "ltr" },
};

/** The SSR / last-resort default when nothing else names a locale. */
export const BUILTIN_DEFAULT_LOCALE: Locale = "ur";

// Languages written right-to-left (primary subtag). Used for *content* direction too, so it covers
// scripts we have no interface catalog for — a lesson can be in a language the chrome is not.
const RTL_LANGUAGES = new Set(["ar", "arc", "ckb", "dv", "fa", "he", "ks", "ku", "ps", "sd", "ug", "ur", "yi"]);

/** The primary language subtag, lower-cased: "ur-PK" -> "ur", "EN_gb" -> "en". */
export function baseLanguage(tag: string): string {
  return tag.trim().toLowerCase().split(/[-_]/)[0] ?? "";
}

export function isSupportedLocale(value: unknown): value is Locale {
  return typeof value === "string" && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

/**
 * Map any locale-ish string to a supported interface locale, or null if there is none.
 * Exact match first, then the base language ("en-GB" -> "en").
 */
export function matchLocale(value: string | null | undefined): Locale | null {
  if (!value) return null;
  if (isSupportedLocale(value)) return value;
  const base = baseLanguage(value);
  return isSupportedLocale(base) ? base : null;
}

/** Resolve to a supported locale, falling back (unknown or empty -> `fallback`). */
export function resolveLocale(value: string | null | undefined, fallback: Locale = defaultLocale()): Locale {
  return matchLocale(value) ?? fallback;
}

/** Writing direction of any BCP 47 tag, catalogued or not. Unknown/empty -> ltr. */
export function directionOf(tag: string | null | undefined): Direction {
  if (!tag) return "ltr";
  const supported = isSupportedLocale(tag) ? tag : null;
  if (supported) return LOCALE_META[supported].dir;
  return RTL_LANGUAGES.has(baseLanguage(tag)) ? "rtl" : "ltr";
}

/**
 * The deployment's default interface locale, from `NEXT_PUBLIC_DEFAULT_LOCALE` (inlined at build
 * time by Next), else Urdu. A misconfigured value falls back rather than breaking the app.
 */
export function defaultLocale(configured: string | undefined = process.env.NEXT_PUBLIC_DEFAULT_LOCALE): Locale {
  return matchLocale(configured) ?? BUILTIN_DEFAULT_LOCALE;
}

/**
 * The interface locale for a person, in priority order: an explicit choice made on this device, then
 * their account's locale, then the deployment default. Never lesson content or curriculum.
 */
export function resolveUiLocale(sources: {
  preference?: string | null;
  account?: string | null;
  fallback?: Locale;
}): Locale {
  return (
    matchLocale(sources.preference) ?? matchLocale(sources.account) ?? sources.fallback ?? defaultLocale()
  );
}
