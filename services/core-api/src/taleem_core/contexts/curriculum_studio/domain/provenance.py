"""Provenance & the original-content gate (pure-stdlib).

Enforces the non-negotiable rule: never copy copyrighted textbooks. Every lesson carries a
Provenance record; validation rejects prohibited sources or unlicensed ingestion.
See docs/10-curriculum-studio/CURRICULUM_ARCHITECTURE.md §6 and curriculum-research/04.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Derivation(StrEnum):
    AUTHORED_ORIGINAL = "authored-original"  # our own content aligned to public SLOs (default)
    INGESTED = "ingested"  # only permitted: open-licensed OR under NCC/MoFEPT MoU


# Sources that must NEVER be ingested (copyrighted textbooks / unofficial scans).
PROHIBITED_SOURCE_MARKERS = (
    "textbook",
    "scan",
    "taleem360",
    "ustad360",
    "nbf.org.pk",
    "pctb.punjab.gov.pk/e-books",
    "ebooks.stbb",
)


@dataclass
class Provenance:
    derivation: Derivation = Derivation.AUTHORED_ORIGINAL
    source: str = "authored"  # "authored" | an aligned-to URL | an open-license URI
    license: str = "authored-original"  # authored-original | MoU-... | CC-BY-4.0 ...
    aligned_slo_codes: list[str] = field(default_factory=list)
    permission_ref: str | None = None
    prohibited_source: bool = False


class ProvenanceError(ValueError):
    """Raised when content violates the original-content / licensing rule."""


def check_provenance(p: Provenance) -> list[str]:
    """Return a list of blocking findings (empty = clean)."""
    findings: list[str] = []
    if p.prohibited_source:
        findings.append("provenance marks a prohibited source")
    lowered = f"{p.source} {p.license}".lower()
    if any(marker in lowered for marker in PROHIBITED_SOURCE_MARKERS):
        findings.append(f"source/license references a prohibited textbook source: {p.source}")
    if p.derivation is Derivation.INGESTED:
        # Ingested content requires either an open license or a written permission reference.
        has_open_license = p.license.upper().startswith(("CC-", "ODBL", "ODC-", "PDDL"))
        if not (has_open_license or (p.permission_ref and p.permission_ref.strip())):
            findings.append("ingested content lacks an open license or a permission_ref (MoU)")
    if p.derivation is Derivation.AUTHORED_ORIGINAL and not p.aligned_slo_codes:
        findings.append("authored content must align to at least one public SLO (standard_code)")
    return findings


def assert_admissible(p: Provenance) -> None:
    """Raise ProvenanceError if the content may not enter the pipeline."""
    findings = check_provenance(p)
    if findings:
        raise ProvenanceError("; ".join(findings))
