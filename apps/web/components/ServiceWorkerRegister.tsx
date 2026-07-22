"use client";
// Registers the offline-lite service worker on mount (Phase 6.2A). Client-only; renders nothing.
// Registration failure never breaks the app — offline simply won't be available.
import { useEffect } from "react";

import { registerServiceWorker } from "../lib/offline";

export function ServiceWorkerRegister() {
  useEffect(() => {
    void registerServiceWorker();
  }, []);
  return null;
}
