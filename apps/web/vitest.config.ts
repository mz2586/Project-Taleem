import { defineConfig } from "vitest/config";

// Node-environment unit tests: the offline-lite sync engine plus pure lib logic (nav model, etc.).
// IndexedDB is provided per-test via `fake-indexeddb` (real browser storage semantics, no browser).
// The include covers every `lib/**/__tests__` suite so new pure-logic tests are gated in CI too.
export default defineConfig({
  test: {
    environment: "node",
    // A tiny in-memory `window.localStorage`, so the session and offline modules can be exercised
    // on their browser branch without pulling jsdom into CI.
    setupFiles: ["./test/setup.ts"],
    include: ["lib/**/__tests__/**/*.test.ts"],
  },
});
