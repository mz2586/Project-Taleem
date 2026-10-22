// Every interface catalog, keyed by locale. Adding a locale means adding it to SUPPORTED_LOCALES and
// here; the `Record<Locale, Messages>` type makes forgetting either a compile error.
import type { Locale } from "../config";
import { en } from "./en";
import type { Messages } from "./types";
import { ur } from "./ur";

export const CATALOGS: Record<Locale, Messages> = { ur, en };

export type { MessageKey, Messages } from "./types";
