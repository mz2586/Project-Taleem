// IndexedDB key-value abstraction (Phase 6.2A).
//
// A tiny store interface (`KVStore`) that all offline logic depends on, plus two implementations:
//   - IdbStore    — real IndexedDB (browser), one DB `taleem-offline` with versioned object stores.
//   - MemoryStore — in-memory, for tests + SSR safety.
//
// Keeping logic behind `KVStore` makes the download manager / progress / checkpoint / read-cache
// modules fully unit-testable (with fake-indexeddb or MemoryStore) without a real browser.

export const DB_NAME = "taleem-offline";
export const DB_VERSION = 1;

// Object stores (OFFLINE_STORAGE_SPEC.md §1). Durable stores are never evicted before sync.
export const STORES = {
  packages: "packages",
  content: "content",
  readCache: "read_cache",
  progress: "progress_local",
  checkpoints: "checkpoints",
  syncMeta: "sync_meta",
  prefs: "prefs",
} as const;

export type StoreName = (typeof STORES)[keyof typeof STORES];

export interface KVStore {
  get<T>(store: StoreName, key: string): Promise<T | undefined>;
  put<T>(store: StoreName, key: string, value: T): Promise<void>;
  getAll<T>(store: StoreName): Promise<T[]>;
  delete(store: StoreName, key: string): Promise<void>;
  clear(store: StoreName): Promise<void>;
}

// ---------------------------------------------------------------- in-memory (tests / SSR)

export class MemoryStore implements KVStore {
  private readonly data = new Map<string, Map<string, unknown>>();

  private bucket(store: StoreName): Map<string, unknown> {
    let b = this.data.get(store);
    if (!b) {
      b = new Map<string, unknown>();
      this.data.set(store, b);
    }
    return b;
  }

  async get<T>(store: StoreName, key: string): Promise<T | undefined> {
    return this.bucket(store).get(key) as T | undefined;
  }

  async put<T>(store: StoreName, key: string, value: T): Promise<void> {
    this.bucket(store).set(key, value);
  }

  async getAll<T>(store: StoreName): Promise<T[]> {
    return Array.from(this.bucket(store).values()) as T[];
  }

  async delete(store: StoreName, key: string): Promise<void> {
    this.bucket(store).delete(key);
  }

  async clear(store: StoreName): Promise<void> {
    this.bucket(store).clear();
  }
}

// ---------------------------------------------------------------- IndexedDB (browser)

function openDb(indexedDBImpl: IDBFactory): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDBImpl.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      for (const store of Object.values(STORES)) {
        if (!db.objectStoreNames.contains(store)) {
          db.createObjectStore(store);
        }
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error("indexedDB open failed"));
  });
}

export class IdbStore implements KVStore {
  private dbPromise: Promise<IDBDatabase> | null = null;

  constructor(private readonly factory: IDBFactory) {}

  private db(): Promise<IDBDatabase> {
    if (!this.dbPromise) this.dbPromise = openDb(this.factory);
    return this.dbPromise;
  }

  private async run<T>(
    store: StoreName,
    mode: IDBTransactionMode,
    fn: (s: IDBObjectStore) => IDBRequest,
  ): Promise<T> {
    const db = await this.db();
    return new Promise<T>((resolve, reject) => {
      const tx = db.transaction(store, mode);
      const req = fn(tx.objectStore(store));
      req.onsuccess = () => resolve(req.result as T);
      req.onerror = () => reject(req.error ?? new Error("indexedDB request failed"));
    });
  }

  get<T>(store: StoreName, key: string): Promise<T | undefined> {
    return this.run<T | undefined>(store, "readonly", (s) => s.get(key));
  }

  async put<T>(store: StoreName, key: string, value: T): Promise<void> {
    await this.run(store, "readwrite", (s) => s.put(value, key));
  }

  getAll<T>(store: StoreName): Promise<T[]> {
    return this.run<T[]>(store, "readonly", (s) => s.getAll());
  }

  async delete(store: StoreName, key: string): Promise<void> {
    await this.run(store, "readwrite", (s) => s.delete(key));
  }

  async clear(store: StoreName): Promise<void> {
    await this.run(store, "readwrite", (s) => s.clear());
  }
}

// Returns an IndexedDB-backed store in the browser, else an in-memory store (SSR / no IDB).
export function createStore(): KVStore {
  if (typeof indexedDB !== "undefined") {
    return new IdbStore(indexedDB);
  }
  return new MemoryStore();
}
