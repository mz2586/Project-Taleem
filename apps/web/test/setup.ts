// A minimal browser shim for the node-environment unit suite.
//
// The offline and session modules are written to run in a browser but degrade cleanly without one —
// they all guard on `typeof window === "undefined"`. Testing them therefore needs just enough of a
// browser to exercise the *present* branch, not a full DOM. A jsdom dependency would add several
// megabytes and a second runtime to CI for a Map with four methods.

class MemoryStorage implements Storage {
  private store = new Map<string, string>();

  get length(): number {
    return this.store.size;
  }
  key(index: number): string | null {
    return Array.from(this.store.keys())[index] ?? null;
  }
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, String(value));
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  clear(): void {
    this.store.clear();
  }
}

const globals = globalThis as unknown as { window?: unknown; localStorage?: Storage };

if (typeof globals.window === "undefined") {
  globals.localStorage = new MemoryStorage();
  // `window` is globalThis itself, not a separate object. `fake-indexeddb/auto` installs onto
  // `window` when one exists, so a standalone stub would hide `indexedDB` from every module that
  // reads it as a bare global — which is how the offline suite reads it.
  globals.window = globalThis;
}
