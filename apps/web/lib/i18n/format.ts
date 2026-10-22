// Locale-aware number formatting (Intl). Pure.
//
// Digits are a separate choice from language: Urdu is commonly written with Western digits on
// phones and in schoolbooks, and with Extended Arabic-Indic digits (۰۱۲۳) in print. Western is the
// default for every locale; "native" asks for the locale's own digit system where it has one.
import type { Locale } from "./config";

export type DigitStyle = "western" | "native";

// The Unicode numbering system a locale uses when "native" digits are requested. Locales absent
// here have no distinct native digits, so "native" is the same as "western" for them.
const NATIVE_NUMBERING: Partial<Record<Locale, string>> = { ur: "arabext" };

export interface NumberFormatOptions extends Intl.NumberFormatOptions {
  digits?: DigitStyle;
}

/** The BCP 47 tag Intl should use, with the numbering-system extension made explicit. */
export function intlLocale(locale: Locale, digits: DigitStyle = "western"): string {
  const nu = digits === "native" ? (NATIVE_NUMBERING[locale] ?? "latn") : "latn";
  return `${locale}-u-nu-${nu}`;
}

function formatter(locale: Locale, options: NumberFormatOptions): Intl.NumberFormat {
  const { digits, ...intl } = options;
  try {
    return new Intl.NumberFormat(intlLocale(locale, digits), intl);
  } catch {
    // A runtime without data for this locale still shows a number rather than throwing.
    return new Intl.NumberFormat("en-u-nu-latn", intl);
  }
}

export function formatNumber(value: number, locale: Locale, options: NumberFormatOptions = {}): string {
  return formatter(locale, options).format(value);
}

/** A 0..1 ratio as a whole-number percentage (0.756 -> "76%"), clamped to 0..100. */
export function formatPercent(
  ratio: number,
  locale: Locale,
  options: Omit<NumberFormatOptions, "style"> = {},
): string {
  const clamped = Number.isFinite(ratio) ? Math.max(0, Math.min(1, ratio)) : 0;
  return formatter(locale, { maximumFractionDigits: 0, ...options, style: "percent" }).format(clamped);
}

/**
 * The name of a language, written in the interface locale ("ur" in an English UI -> "Urdu"; in an
 * Urdu UI -> "اردو"). Falls back to the tag itself where the runtime has no display names.
 */
export function languageName(tag: string, uiLocale: Locale): string {
  try {
    return new Intl.DisplayNames([uiLocale], { type: "language" }).of(tag) ?? tag;
  } catch {
    return tag;
  }
}
