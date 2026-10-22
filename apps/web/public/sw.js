/*
 * Service worker — Phase 6.2A offline-lite (docs/33-offline-architecture.md §3,
 * OFFLINE_ARCHITECTURE.md §4/§6).
 *
 * Responsibilities (6.2A only):
 *   - Precache + serve the app shell (cache-first), so the app opens offline.
 *   - Runtime-cache GET reads (offline packages + derived student read models) network-first with a
 *     cache fallback — this is the offline dashboard + offline lesson-loading layer.
 *   - Automatic cache versioning: caches are version-named; old versions are purged on activate.
 *
 * NOT here (deferred): background sync, sync batching, conflict resolution, offline auth, telemetry
 * upload. NO generative AI offline, ever (audit AR-C-06). NO writes are cached, NO auth tokens are
 * cached, and NO child data is persisted by the service worker (structured offline data lives in
 * IndexedDB, written by the app, not the SW).
 */

// v2: precaches the self-hosted Urdu font, so Urdu renders in Nastaliq offline too.
const SHELL_VERSION = "v2";
const SHELL_CACHE = `taleem-shell-${SHELL_VERSION}`;
const RUNTIME_CACHE = `taleem-runtime-${SHELL_VERSION}`;
// The Urdu font is part of the shell: without it an offline device falls back to a face with
// disconnected letters (design-system/fonts.css). Static, licence-cleared (public/fonts/OFL.txt).
const URDU_FONT = "/fonts/NotoNastaliqUrdu-Regular.arabic.woff2";
const APP_SHELL = ["/", "/manifest.webmanifest", URDU_FONT];
// Offline lessons (R1): the library and the player must open with the network off. Precached
// best-effort (a missing route never fails the install), and refreshed under their OWN URL on every
// online visit, so offline they render themselves rather than the root shell.
const OFFLINE_ROUTES = ["/student/offline", "/student/offline/play"];

function isOfflineRoute(url) {
  return OFFLINE_ROUTES.includes(url.pathname);
}

// Read routes safe to cache for offline rendering (GET, no child mutation).
function isCacheableRead(url) {
  return url.pathname.startsWith("/v1/offline/") || url.pathname.startsWith("/v1/learning/students/");
}

function isOwnedCache(name) {
  return name === SHELL_CACHE || name === RUNTIME_CACHE;
}

self.addEventListener("install", (event) => {
  // Take over promptly so a corrected SW replaces a previously-installed one without waiting for
  // every tab to close (paired with clients.claim() on activate). No child data is touched.
  self.skipWaiting();
  event.waitUntil(
    caches.open(SHELL_CACHE).then((cache) =>
      cache
        .addAll(APP_SHELL)
        .then(() => Promise.all(OFFLINE_ROUTES.map((route) => cache.add(route).catch(() => undefined))))
    )
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((names) =>
        Promise.all(
          names.filter((n) => n.startsWith("taleem-") && !isOwnedCache(n)).map((n) => caches.delete(n))
        )
      )
      .then(() => self.clients.claim())
  );
});

// Let the app activate a waiting SW on an explicit user action (never mid-session silently).
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "SKIP_WAITING") {
    self.skipWaiting();
  }
});

// Background Sync (Phase 6.2B): when the platform wakes us on reconnect, nudge every open client to
// drain its durable queue. The drain runs in the page (it needs the auth'd fetch + IndexedDB); the
// SW only broadcasts. No child data is touched here.
self.addEventListener("sync", (event) => {
  if (event.tag === "taleem-sync") {
    event.waitUntil(
      self.clients.matchAll({ includeUncontrolled: true }).then((clients) => {
        for (const client of clients) client.postMessage({ type: "SYNC_NOW" });
      })
    );
  }
});

self.addEventListener("fetch", (event) => {
  const request = event.request;

  // Never touch non-GET (writes are queued by the app, never cached) or cross-origin.
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // App-shell navigations: NETWORK-FIRST with an offline fallback to the cached shell.
  // (Must NOT be cache-first: this is a multi-route Next.js app where every route has its own
  // server-rendered HTML + entry chunk. Serving the cached "/" shell for every navigation made
  // /guardian, /student/*, /studio all render the root landing page for SW-controlled clients.
  // Network-first serves the correct route online and still opens offline via the cached shell.)
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(SHELL_CACHE).then((cache) => cache.put("/", copy));
            if (isOfflineRoute(url)) {
              const own = response.clone();
              caches.open(SHELL_CACHE).then((cache) => cache.put(url.pathname, own));
            }
          }
          return response;
        })
        .catch(() =>
          caches
            .match(request)
            // The player is /student/offline/play?lesson=...: match its cached page whatever the query.
            .then((cached) => cached || (isOfflineRoute(url) ? caches.match(url.pathname) : undefined))
            .then((cached) => cached || caches.match("/"))
        )
    );
    return;
  }

  // Cacheable reads: network-first, fall back to cache when offline. Only cache 200s.
  if (isCacheableRead(url)) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(RUNTIME_CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // Everything else (static assets): cache-first with a network fill.
  event.respondWith(
    caches.match(request).then(
      (cached) =>
        cached ||
        fetch(request).then((response) => {
          if (response.ok) {
            const copy = response.clone();
            caches.open(SHELL_CACHE).then((cache) => cache.put(request, copy));
          }
          return response;
        })
    )
  );
});
