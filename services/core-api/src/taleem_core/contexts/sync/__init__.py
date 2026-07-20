"""Offline sync engine prototype (governance-safe).

Demonstrates the remediated offline conflict policy (docs/33-offline-architecture.md §6, audit
AR-H-28): deterministic, server-version-ordered, idempotent, append-only-by-union — with NO
dependence on client wall-clock and NO live child data (in-memory synthetic store only).
"""
