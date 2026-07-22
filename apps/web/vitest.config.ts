import { defineConfig } from "vitest/config";

// Phase 6.2A offline-lite unit + offline-simulation tests. Node environment; IndexedDB is provided
// per-test via `fake-indexeddb` (real browser storage semantics without a browser).
export default defineConfig({
  test: {
    environment: "node",
    include: ["lib/offline/__tests__/**/*.test.ts"],
  },
});
