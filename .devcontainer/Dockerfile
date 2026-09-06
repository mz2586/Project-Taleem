# Base image for the Project Taleem dev container.
#
# The stock python:1-3.12-bookworm image ships an apt source for dl.yarnpkg.com whose signing key is
# not present. Any devcontainer Feature whose install script runs `apt-get update` therefore aborts:
#
#   W: GPG error: https://dl.yarnpkg.com/debian stable InRelease: NO_PUBKEY 62D54FD4003F6525
#   ERROR: Feature "..." failed to install!   (exit code 100)
#
# That broke Codespace creation twice — first via docker-in-docker, then via sshd — and each failure
# silently fell back to a recovery container with no Python venv, no Node and no dependencies.
# Dropping the offending source lets Features install normally.

FROM mcr.microsoft.com/devcontainers/python:1-3.12-bookworm

RUN set -eux; \
    for f in /etc/apt/sources.list.d/*; do \
        [ -e "$f" ] || continue; \
        if grep -qs 'yarnpkg' "$f"; then echo "removing broken apt source: $f"; rm -f "$f"; fi; \
    done; \
    apt-get update; \
    rm -rf /var/lib/apt/lists/*
