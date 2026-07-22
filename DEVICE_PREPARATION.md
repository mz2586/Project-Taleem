# Device Preparation Guide

Status: **Phase 9 — Pilot Operations.** How to prepare the devices for the first supervised pilot
(Pilot 1: on provided, MDM-managed devices, at a community learning centre, on guaranteed on-site
Wi-Fi — per [PILOT_PLAN.md](PILOT_PLAN.md)). Companion to [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md),
[INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md). Reuses the existing PWA + offline platform; no new
architecture.

---

## 1. Device profile (Pilot 1)

| Attribute | Requirement |
| --- | --- |
| Ownership | **Provided** devices (operator-owned), not personal/home devices |
| Class | Representative **low-end Android** (the pilot target) + a few mid/desktop for facilitators |
| Management | **MDM-enrolled** — enforces full-disk encryption, app allow-list, remote wipe |
| Browser | Chromium-based (PWA + Service Worker + Background Sync + WebCrypto Ed25519) |
| Network | Guaranteed on-site Wi-Fi (the offline-safety compensating control is on-site supervision) |
| Storage | Provisioned with headroom for the day's signed lesson packages + audio |
| Audio | Working speaker/headphones (audio-first is required for non-readers) |

---

## 2. Preparation checklist (per device, before Pilot 0 dry run)

- [ ] **MDM enrolment** complete; **full-disk encryption** on (the primary at-rest control; app-level
      C2 encryption is the 6.2C/at-home item — managed OS encryption covers Pilot 1).
- [ ] App allow-list restricts the device to the Taleem PWA + required system apps (no browsing, no
      app store, no cameras/mic per the `Permissions-Policy` already set in `next.config.mjs`).
- [ ] **Taleem PWA installed** and opens; the **service worker registers** and precaches the app shell
      (offline shell verified — open with Wi-Fi off after first load).
- [ ] **Signing key pinned:** the client is configured with the server's Ed25519 **public** signing key
      (from `GET /v1/offline/signing-keys`, or bundled) so offline packages verify (6.2C-1).
- [ ] **Persistent storage** requested (`navigator.storage.persist`) so the offline queue/checkpoints
      resist eviction.
- [ ] **Day's packages downloaded + verified:** the current lesson set installs, **signature + content
      hash verify**, and each lesson **renders offline** end-to-end (turn Wi-Fi off and complete one
      session).
- [ ] **Sync verified:** an offline attempt queues and **syncs with no double-count** on reconnect
      (6.2B), and the sync status UI shows a clean drain.
- [ ] **Kill-switch + rollback** reachable from the operator console; tested on this device.
- [ ] **Time + locale** correct; Urdu-first RTL renders; Eastern-Arabic numerals correct (FD-15).
- [ ] **Accessibility** pass: audio plays, captions show, touch targets usable, screen-reader operable.
- [ ] **No child data** provisioned yet — devices carry only C0 curriculum + app; child sessions start
      only after M-Gov (consent) at Pilot 1.

---

## 3. Offline package deployment (per device)

1. Build + **sign** each published lesson's offline package server-side (6.2A builder + 6.2C-1 Ed25519).
2. On the device, download the day's packages (`GET /v1/offline/packages/{lessonId}`).
3. The client **verifies the signature** against the pinned key, then the **content hash**, then
   installs atomically (a tampered/truncated/unsigned package is rejected — never rendered to a child).
4. Confirm offline render + audio for every package (turn Wi-Fi off).
5. Confirm the app degrades gracefully if a media asset is missing ("audio not available", never a
   crash).

## 4. Shared-device hygiene

- **Per-profile namespacing:** each learner's cached view is namespaced; **switching learner clears the
  prior cached view** (6.2A/6.2C-1) — no cross-child leakage.
- **De-enrolment:** on consent withdrawal, the purge mechanism clears that learner's C2 data at next
  connect (6.2C-1).
- **End-of-day:** confirm queues drained (no pending-to-sync); MDM can remote-wipe a lost device.

## 5. Fleet operations

- Keep a **spare-device pool** (swap on hardware failure without interrupting a learner).
- Track per-device: OS/browser version, storage headroom, last package version, last successful sync.
- Re-run this checklist whenever the app version, package version, or signing key rotates.

## 6. Pass criteria (device is pilot-ready)

A device is pilot-ready when: it is MDM-managed + encrypted + locked-down; the PWA + SW + offline
packages install and **verify**; a full lesson **runs offline** with audio; an offline attempt
**syncs with no double-count**; the kill-switch works; accessibility passes; and **no child data** is
present until consent. This is part of the **Pilot 0** exit (see [PILOT_RUNBOOK.md](PILOT_RUNBOOK.md)).
