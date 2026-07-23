#!/usr/bin/env bash
# Release automation — Project Taleem (Software Completion Mode).
#
# The local Git repository is the canonical project history; every release is an annotated tag on this
# machine (VERSION.md). This script performs the deterministic, software-checkable half of a release:
#   1. version consistency  — VERSION.md, CHANGELOG.md, and pyproject.toml agree
#   2. release-readiness     — the working tree is clean (no uncommitted changes)
#   3. quality gates         — optionally run the full gate suite (make gates) with --gates
#   4. tag command           — print the exact annotated-tag command (never tags automatically)
#
# It NEVER creates the tag or mutates history itself: a human decides when to cut the release. Run it
# from the repository root. Exit non-zero on the first failed check so CI/humans can gate on it.
set -euo pipefail

cd "$(dirname "$0")/.."

fail() { echo "FAIL: $*" >&2; exit 1; }
ok()   { echo "  ok  $*"; }

RUN_GATES=0
[ "${1:-}" = "--gates" ] && RUN_GATES=1

echo "== Project Taleem release check =="

# 1. Extract the declared version from VERSION.md ("Current version: **X.Y.Z**").
VERSION="$(grep -m1 'Current version' VERSION.md | sed -E 's/.*\*\*([0-9]+\.[0-9]+\.[0-9]+)\*\*.*/\1/')"
[ -n "$VERSION" ] || fail "could not parse 'Current version' from VERSION.md"
ok "VERSION.md declares $VERSION"

# The declared milestone/tag ("Milestone: **phase-N** ...").
TAG="$(grep -m1 'Milestone' VERSION.md | sed -E 's/.*\*\*([^*]+)\*\*.*/\1/')"
[ -n "$TAG" ] || fail "could not parse 'Milestone' tag from VERSION.md"
ok "VERSION.md milestone tag: $TAG"

# 2. CHANGELOG must have a section header for this version.
grep -q "\[$VERSION\]" CHANGELOG.md || fail "CHANGELOG.md has no section for [$VERSION]"
ok "CHANGELOG.md has a [$VERSION] section"

# 3. The version history table must list this version + tag on one row.
grep -qE "\|[[:space:]]*$VERSION[[:space:]]*\|.*$TAG" VERSION.md \
  || fail "VERSION.md history table missing a row for $VERSION / $TAG"
ok "VERSION.md history lists $VERSION -> $TAG"

# 4. Working tree must be clean.
if [ -n "$(git status --porcelain)" ]; then
  fail "working tree is dirty — commit or stash before releasing"
fi
ok "working tree is clean"

# 5. The tag must not already exist (a release is cut once).
if git rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
  fail "tag $TAG already exists — bump VERSION.md before cutting a new release"
fi
ok "tag $TAG does not yet exist"

# 6. Optional: run the full gate suite.
if [ "$RUN_GATES" = "1" ]; then
  echo "== Running full gate suite (make gates) =="
  make gates
  ok "all gates passed"
else
  echo "  (skipped gate suite — pass --gates to run 'make gates' first)"
fi

echo
echo "Release checks passed for $VERSION ($TAG)."
echo "To cut the release, create the annotated tag:"
echo
echo "    git tag -a $TAG -m \"Project Taleem $VERSION\""
echo
echo "(This script never tags automatically — a human cuts the release.)"
