"use client";
// React binding: the current interface locale plus `t()` and formatters bound to it.
//
// Resolution order (see `resolveUiLocale`): this device's explicit choice -> the signed-in account's
// locale (learner or guardian, from the existing session API) -> NEXT_PUBLIC_DEFAULT_LOCALE -> "ur".
// Lesson content is NOT an input: the interface language never follows what is being taught.
//
// The first render (server and client alike) has no session and no stored choice, so it renders the
// deployment default — the same markup on both sides, no hydration mismatch.
import { useEffect, useMemo, useState } from "react";

import { useSession } from "../session/useSession";
import { defaultLocale, directionOf, resolveUiLocale, type Direction, type Locale } from "./config";
import { formatNumber, formatPercent, type DigitStyle, type NumberFormatOptions } from "./format";
import { readUiLocalePreference, subscribeUiLocalePreference, writeUiLocalePreference } from "./preference";
import { createTranslator, type Translator } from "./translate";

export interface LocaleHandle {
  locale: Locale;
  dir: Direction;
  t: Translator;
  formatNumber: (value: number, options?: NumberFormatOptions) => string;
  formatPercent: (ratio: number) => string;
  /** Set this device's interface locale; null returns to the account/default locale. */
  setLocale: (locale: Locale | null) => void;
}

export function useLocale(digits: DigitStyle = "western"): LocaleHandle {
  const { session } = useSession();
  const [preference, setPreference] = useState<Locale | null>(null);

  useEffect(() => {
    setPreference(readUiLocalePreference());
    return subscribeUiLocalePreference(setPreference);
  }, []);

  const account = session?.learner?.locale ?? session?.guardian?.locale ?? null;
  const locale = resolveUiLocale({ preference, account, fallback: defaultLocale() });

  return useMemo<LocaleHandle>(
    () => ({
      locale,
      dir: directionOf(locale),
      t: createTranslator(locale, digits),
      formatNumber: (value, options) => formatNumber(value, locale, { digits, ...options }),
      formatPercent: (ratio) => formatPercent(ratio, locale, { digits }),
      setLocale: writeUiLocalePreference,
    }),
    [locale, digits],
  );
}

/** Shorthand when a component only needs `t`. */
export function useT(): Translator {
  return useLocale().t;
}
