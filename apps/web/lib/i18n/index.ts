// Pure i18n surface (server-safe). The React hook lives in `./useLocale` and is imported directly by
// client components, so a server component importing this barrel never pulls in client code.
export * from "./config";
export * from "./content";
export * from "./format";
export * from "./translate";
export type { MessageKey, Messages } from "./messages";
