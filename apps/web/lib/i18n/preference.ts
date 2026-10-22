// The interface-locale choice made on THIS device ("show me the app in English").
//
// It is a per-device convenience, not account state: a shared family phone can be set to the
// language the child reads best without editing anyone's account. It lives in localStorage and is
// read only after mount (it does not exist during the server render). Unavailable storage means "no
// choice made", never a crash.
import { matchLocale, type Locale } from "./config";

const STORAGE_KEY = "taleem.uiLocale.v1";

type Listener = (locale: Locale | null) => void;
const listeners = new Set<Listener>();

export function readUiLocalePreference(): Locale | null {
  if (typeof window === "undefined") return null;
  try {
    return matchLocale(window.localStorage.getItem(STORAGE_KEY));
  } catch {
    return null;
  }
}

/** Set (or with null, clear) this device's interface locale and notify every mounted view. */
export function writeUiLocalePreference(locale: Locale | null): void {
  if (typeof window !== "undefined") {
    try {
      if (locale) window.localStorage.setItem(STORAGE_KEY, locale);
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      /* storage unavailable: the choice still applies for this page's lifetime */
    }
  }
  for (const listener of listeners) listener(locale);
}

export function subscribeUiLocalePreference(listener: Listener): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
