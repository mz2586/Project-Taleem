"""Project Taleem — Core API.

M1 walking skeleton. GOVERNANCE-SAFE SCAFFOLDING ONLY.

This package deliberately implements *only* work with zero dependency on unresolved
governance decisions (see FOUNDER_DECISIONS.md). It does NOT implement student enrolment,
child accounts, live student data, payments, production AI, or safeguarding workflows.

Architecture: Clean/Hexagonal + DDD (see docs/08-system-architecture.md and
docs/47-folder-structure.md). The `domain` and `platform` layers are pure-stdlib and
framework-free; framework adapters (FastAPI, providers) live at the edges.
"""

__version__ = "0.1.0"
