"""Offline lesson packages (pure, framework-free) — Phase 6.2A.

Turns a published ``LessonView`` into a self-contained, content-hashed package a client can cache
and render fully offline. Design per OFFLINE_ARCHITECTURE.md §3 and OFFLINE_STORAGE_SPEC.md.

Two deliberate 6.2A properties:

  1. **No answer keys on the device.** The offline content ships the teaching + attempt surface
     (title, explanation, worked steps, item prompts, options, authored hints) but NEVER
     ``correct_option`` / ``option_misconceptions`` / corrections. Grading stays server-side
     (Option A offline-lite; server-side grading arrives with sync in 6.2B). A device therefore
     cannot reveal an answer offline — a safety property, not an omission.
  2. **Content-hash versioning.** ``content_hash`` = SHA-256 over the canonical offline content;
     ``version`` is its short prefix. A change in content changes the hash → the client treats the
     cached package as stale (automatic cache versioning / invalidation). No Ed25519 signing here
     (that is 6.2C hardening); the hash gives integrity + versioning for offline-lite.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Protocol

from .curriculum_view import ItemView, LessonView

CONTENT_ASSET_KIND = "content"
VERSION_LEN = 12


def _item_offline_dict(item: ItemView) -> dict[str, object]:
    """Child-safe projection of an item: prompt, options, hints — NO answer key."""
    return {
        "item_ref": item.item_ref,
        "objective_code": item.objective_code,
        "prompt": dict(item.prompt),
        "options": list(item.options),
        "hints": list(item.hints),
    }


def lesson_offline_content(view: LessonView) -> dict[str, object]:
    """Project a LessonView into the child-safe offline content document (no answer keys)."""
    return {
        "lesson_id": view.lesson_id,
        "objective_code": view.objective_code,
        "title": dict(view.title),
        "explanation": dict(view.explanation),
        "worked_example_steps": list(view.worked_example_steps),
        "practice_items": [_item_offline_dict(i) for i in view.practice_items],
        "homework_items": [_item_offline_dict(i) for i in view.homework_items],
        "assessment_formative": [_item_offline_dict(i) for i in view.assessment_formative],
        "summative_mentor_mediated": view.summative_mentor_mediated,
    }


def canonical_json(content: dict[str, object]) -> str:
    """Deterministic serialization — sorted keys, compact separators (stable across runs)."""
    return json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(content: dict[str, object]) -> str:
    """SHA-256 hex over the canonical content (drives versioning + integrity)."""
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PackageAsset:
    ref: str
    kind: str
    sha256: str
    bytes: int

    def to_dict(self) -> dict[str, object]:
        return {"ref": self.ref, "kind": self.kind, "sha256": self.sha256, "bytes": self.bytes}


class PackageSigner(Protocol):
    """Port for signing a manifest payload (implemented by an Ed25519 adapter). Server-side only."""

    @property
    def key_id(self) -> str: ...

    @property
    def public_key_hex(self) -> str: ...

    def sign(self, payload: bytes) -> str: ...


def signing_payload(package_id: str, version: str, content_hash: str) -> bytes:
    """The canonicalization-free bytes that get signed (binds pointer + version + content).

    Using newline-joined fields (not JSON) keeps Python↔WebCrypto interop independent of key
    ordering. Binding ``version`` + ``package_id`` (not just the hash) also prevents downgrade/
    pointer-swap of a validly-signed older package.
    """
    return f"{package_id}\n{version}\n{content_hash}".encode()


@dataclass(frozen=True)
class OfflinePackageManifest:
    """The verifiable descriptor a client fetches before/with a package (no child data)."""

    package_id: str  # stable pointer, e.g. "pkg/math-g4-intro-fractions"
    lesson_id: str
    objective_code: str
    version: str  # short prefix of content_hash — changes iff content changes
    content_hash: str
    assets: tuple[PackageAsset, ...]
    total_bytes: int
    created_at_ms: int
    signature: str = ""  # hex Ed25519 signature over signing_payload (empty = unsigned)
    signing_key_id: str = ""  # id of the key that produced `signature` (empty = unsigned)

    def to_dict(self) -> dict[str, object]:
        return {
            "package_id": self.package_id,
            "lesson_id": self.lesson_id,
            "objective_code": self.objective_code,
            "version": self.version,
            "content_hash": self.content_hash,
            "assets": [a.to_dict() for a in self.assets],
            "total_bytes": self.total_bytes,
            "created_at_ms": self.created_at_ms,
            "signature": self.signature,
            "signing_key_id": self.signing_key_id,
        }


def build_manifest(
    view: LessonView,
    *,
    now_ms: int,
    package_pointer: str | None = None,
    signer: PackageSigner | None = None,
) -> OfflinePackageManifest:
    """Build a deterministic manifest for a lesson's offline package.

    ``now_ms`` is injected (never wall-clocked here) so builds are reproducible in tests. If a
    ``signer`` is provided, the manifest is Ed25519-signed (Phase 6.2C-1); otherwise it is unsigned
    (backward-compatible with 6.2A/6.2B — empty signature fields).
    """
    content = lesson_offline_content(view)
    chash = content_hash(content)
    size = len(canonical_json(content).encode("utf-8"))
    asset = PackageAsset(
        ref=f"{view.lesson_id}/content.json", kind=CONTENT_ASSET_KIND, sha256=chash, bytes=size
    )
    pointer = package_pointer or f"pkg/{view.lesson_id}"
    version = chash[:VERSION_LEN]
    signature = ""
    key_id = ""
    if signer is not None:
        signature = signer.sign(signing_payload(pointer, version, chash))
        key_id = signer.key_id
    return OfflinePackageManifest(
        package_id=pointer,
        lesson_id=view.lesson_id,
        objective_code=view.objective_code,
        version=version,
        content_hash=chash,
        assets=(asset,),
        total_bytes=size,
        created_at_ms=now_ms,
        signature=signature,
        signing_key_id=key_id,
    )


@dataclass(frozen=True)
class OfflinePackage:
    """A manifest plus its verifiable content document (what the client stores + renders)."""

    manifest: OfflinePackageManifest
    content: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {"manifest": self.manifest.to_dict(), "content": self.content}


def build_package(
    view: LessonView,
    *,
    now_ms: int,
    package_pointer: str | None = None,
    signer: PackageSigner | None = None,
) -> OfflinePackage:
    """Build the full package (manifest + child-safe content) for a lesson."""
    return OfflinePackage(
        manifest=build_manifest(
            view, now_ms=now_ms, package_pointer=package_pointer, signer=signer
        ),
        content=lesson_offline_content(view),
    )


def fits_in_quota(total_bytes: int, *, available_bytes: int, headroom_bytes: int = 0) -> bool:
    """Pure storage pre-flight: does a download of ``total_bytes`` fit within available storage?

    ``headroom_bytes`` reserves space so a device is never filled to the brim (the download
    manager refuses otherwise — OFFLINE_ARCHITECTURE.md §7).
    """
    if total_bytes < 0 or available_bytes < 0 or headroom_bytes < 0:
        raise ValueError("byte counts must be non-negative")
    return total_bytes + headroom_bytes <= available_bytes
