// Connectivity detection (Phase 6.2A).
//
// `navigator.onLine` is unreliable (it reports link state, not real reachability), so this combines
// the online/offline events with an optional active reachability probe against a cheap endpoint.
// No background sync here (6.2B) — this only reports status to the UI (the OfflineBadge).

export type ConnectivityListener = (online: boolean) => void;

export interface ConnectivityDeps {
  // Event target to attach online/offline listeners (window in the browser).
  target?: Pick<EventTarget, "addEventListener" | "removeEventListener">;
  // Initial + polled navigator.onLine reader.
  isOnLine?: () => boolean;
  // Optional active probe (e.g. GET /health) confirming real reachability.
  probe?: () => Promise<boolean>;
}

// Returns current best-effort online status.
export function currentlyOnline(isOnLine: () => boolean = defaultIsOnLine): boolean {
  return isOnLine();
}

function defaultIsOnLine(): boolean {
  return typeof navigator !== "undefined" ? navigator.onLine : true;
}

// Subscribe to connectivity changes. Returns an unsubscribe function.
export function watchConnectivity(
  listener: ConnectivityListener,
  deps: ConnectivityDeps = {},
): () => void {
  const target =
    deps.target ?? (typeof window !== "undefined" ? window : undefined);
  const isOnLine = deps.isOnLine ?? defaultIsOnLine;

  const emit = () => listener(isOnLine());
  emit(); // report initial state immediately

  const onOnline = async () => {
    if (deps.probe) {
      listener(await deps.probe());
    } else {
      listener(true);
    }
  };
  const onOffline = () => listener(false);

  target?.addEventListener("online", onOnline as EventListener);
  target?.addEventListener("offline", onOffline as EventListener);

  return () => {
    target?.removeEventListener("online", onOnline as EventListener);
    target?.removeEventListener("offline", onOffline as EventListener);
  };
}

// A reachability probe factory: resolves true iff a cheap GET succeeds.
export function makeProbe(url: string, fetchImpl: typeof fetch = fetch): () => Promise<boolean> {
  return async () => {
    try {
      const res = await fetchImpl(url, { method: "GET", cache: "no-store" });
      return res.ok;
    } catch {
      return false;
    }
  };
}
