// Background synchronization triggers (Phase 6.2B).
//
// Drains the queue automatically when connectivity returns:
//   - registers a Background Sync tag (where supported) so the service worker can wake and ask the
//     page to drain even if it was backgrounded;
//   - falls back to draining on the `online` event and on tab `visibilitychange` (foreground).
// The actual drain runs in the page (it needs the auth'd fetch + IndexedDB); the SW only nudges.
// No offline auth here — the drain uses the app's existing bearer.

export const SYNC_TAG = "taleem-sync";

export interface BackgroundSyncDeps {
  drain: () => Promise<unknown>;
  target?: Pick<EventTarget, "addEventListener" | "removeEventListener">;
  document?: Pick<Document, "addEventListener" | "removeEventListener" | "visibilityState">;
  isOnLine?: () => boolean;
}

// Best-effort Background Sync registration (no-op where unsupported).
export async function registerBackgroundSync(tag = SYNC_TAG): Promise<boolean> {
  if (typeof navigator === "undefined" || !("serviceWorker" in navigator)) return false;
  try {
    const reg = (await navigator.serviceWorker.ready) as ServiceWorkerRegistration & {
      sync?: { register: (t: string) => Promise<void> };
    };
    if (reg.sync) {
      await reg.sync.register(tag);
      return true;
    }
  } catch {
    // registration unsupported / denied — the foreground fallback still covers reconnect.
  }
  return false;
}

// Start draining automatically on reconnect + when the tab becomes visible online. Returns cleanup.
export function startAutoDrain(deps: BackgroundSyncDeps): () => void {
  const target = deps.target ?? (typeof window !== "undefined" ? window : undefined);
  const doc = deps.document ?? (typeof document !== "undefined" ? document : undefined);
  const isOnLine = deps.isOnLine ?? (() => (typeof navigator !== "undefined" ? navigator.onLine : true));

  const kick = () => {
    if (isOnLine()) void deps.drain();
  };
  const onVisible = () => {
    if (doc && doc.visibilityState === "visible") kick();
  };
  const onSwMessage = (event: MessageEvent) => {
    if (event.data && (event.data as { type?: string }).type === "SYNC_NOW") kick();
  };

  target?.addEventListener("online", kick as EventListener);
  doc?.addEventListener("visibilitychange", onVisible as EventListener);
  if (typeof navigator !== "undefined" && navigator.serviceWorker) {
    navigator.serviceWorker.addEventListener("message", onSwMessage as EventListener);
  }

  // Kick once on start in case we came online before subscribing.
  kick();

  return () => {
    target?.removeEventListener("online", kick as EventListener);
    doc?.removeEventListener("visibilitychange", onVisible as EventListener);
    if (typeof navigator !== "undefined" && navigator.serviceWorker) {
      navigator.serviceWorker.removeEventListener("message", onSwMessage as EventListener);
    }
  };
}
