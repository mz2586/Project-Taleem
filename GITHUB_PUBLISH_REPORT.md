# GitHub Publish Report

Project Taleem RC1 was published to GitHub. All branches and tags are pushed and verified on the
remote.

- **Date:** 2026-07-31
- **Repository URL:** <https://github.com/mz2586/Project-Taleem>
- **Remote:** `https://github.com/mz2586/Project-Taleem.git` (HTTPS)
- **Default branch / visibility:** `main` · **public**

## Authentication method used

Auto-detected per the priority order:

1. Existing authenticated `gh` — none (not logged in).
2. Existing SSH key — present (`id_ed25519`) but **not registered** on the GitHub account
   (`Permission denied (publickey)`).
3. Create a new SSH key — skipped (a key already existed).
4. **GitHub CLI device/browser flow (`gh auth login --web`)** — used.

Authenticated as **`mz2586`** over HTTPS. Because the repository contains `.github/workflows/`, the
login was (re)issued with the **`workflow`** scope in addition to `repo`; final token scopes:
`gist, read:org, repo, workflow`. Git was configured to use the gh credential helper
(`gh auth setup-git`).

No password was used or stored (GitHub does not accept passwords for git; the plaintext password
shared in chat should be rotated).

## Pre-flight verification

- ✅ Correct repository — README + RC1 markers confirm Project Taleem RC1.
- ✅ Working tree clean — 0 uncommitted changes at push time.
- ✅ RC1 tag + release branch created — annotated tag **`rc1`** and branch **`release/rc1`** at the
  clean `main` HEAD (`70a41ad`).
- ✅ Remote configured — `origin` → the target repo over HTTPS.

## Branches pushed

| Branch | Remote result |
| --- | --- |
| `main` | ✅ new branch (tracking) |
| `release/rc1` | ✅ new branch (tracking) |
| `wip-safeguard-20260721` | ✅ new branch |

## Tags pushed

`rc1` (RC1 release) plus the full milestone history:
`phase-4.1, phase-4.2, phase-5.5, phase-6-docs, phase-6.2A, phase-6.2B, phase-6.2C-1, phase-7,
phase-8, phase-9, phase-10, phase-11` — **13 tags total**, all present on the remote.

## Latest commit

- **`70a41adc29`** — `docs: SiteGround deployment report — incompatible platform, not deployed`
- On the remote `main`: `70a41adc29` ✅ (matches local HEAD `70a41ad`).
- Tag `rc1` resolves to `70a41adc29` ✅ (the RC1 release point).

## Verification results (queried via the GitHub API after push)

| Check | Result |
| --- | --- |
| Repository reachable | ✅ `mz2586/Project-Taleem`, default `main`, public |
| Remote branches | ✅ `main`, `release/rc1`, `wip-safeguard-20260721` |
| Release branch exists | ✅ `release/rc1` |
| Remote tags | ✅ 13 tags incl. `rc1` |
| `rc1` tag exists remotely | ✅ → `70a41adc29` |
| Latest RC1 commit exists remotely | ✅ `70a41adc29` on `main` (= local HEAD) |
| Repository contents | ✅ 536 tree entries; key paths present (`README.md`, `RC1_CHECKLIST.md`, `services/core-api/pyproject.toml` + `requirements.lock`, `apps/web/package.json`, `packages/contracts/guardian.openapi.yaml`, `.github/workflows/ci.yml`) |

## Notes

- The initial branch push over HTTPS hit a transient `HTTP 408` on the large first pack upload; the
  tag push uploaded all objects, after which the branch refs pushed cleanly. All refs are present.
- The repository is **public** and the code `LICENSE` states the license is an undecided
  founding-team decision ("no rights granted until ratified"). Consider whether the repo should be
  private until the license is ratified (Settings → General → Change visibility). This is your call.

**Status: Published and verified.**
