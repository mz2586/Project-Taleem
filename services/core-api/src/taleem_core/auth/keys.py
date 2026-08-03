"""JWT signing / verification key material (asymmetric, rotating — FD-14, docs/03 §11 §7, §13).

Production token signing is **asymmetric** (Ed25519 / EdDSA): the Identity service holds the private
seed and signs; every resource server verifies with the *public* key only, published as a JWKS. Keys
are **kid-addressed** and a verifier holds a *set* of them, so rotation is an overlap (publish the
new public key, switch signing to the new kid, retire the old key later) — never a flag-day.

Pure-stdlib: reuses ``platform.ed25519`` (the same primitive that signs offline packages). No shared
secret leaves the signer; resource servers never hold signing material.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from ..platform import ed25519


def _b64url_decode(segment: str) -> bytes:
    return base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4))


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@dataclass(frozen=True)
class VerifyKey:
    """A public Ed25519 verification key, addressed by ``kid``."""

    kid: str
    public_key: bytes  # 32 raw bytes

    def __post_init__(self) -> None:
        if len(self.public_key) != 32:
            raise ValueError("Ed25519 public key must be 32 bytes")

    def jwk(self) -> dict[str, str]:
        """This key as a public JWK (RFC 8037 OKP / Ed25519)."""
        return {
            "kty": "OKP",
            "crv": "Ed25519",
            "kid": self.kid,
            "use": "sig",
            "alg": "EdDSA",
            "x": _b64url_encode(self.public_key),
        }


@dataclass(frozen=True)
class SigningKey:
    """A private Ed25519 signing key (Identity service only). Never leaves the signer."""

    kid: str
    seed: bytes  # 32 raw bytes

    def __post_init__(self) -> None:
        if len(self.seed) != 32:
            raise ValueError("Ed25519 seed must be 32 bytes")

    @property
    def public_key(self) -> bytes:
        return ed25519.public_key(self.seed)

    def verify_key(self) -> VerifyKey:
        return VerifyKey(self.kid, self.public_key)


@dataclass(frozen=True)
class KeySet:
    """A verifier's set of public keys, indexed by ``kid`` (supports rotation / overlap)."""

    keys: tuple[VerifyKey, ...]

    def by_kid(self, kid: str) -> VerifyKey | None:
        for k in self.keys:
            if k.kid == kid:
                return k
        return None

    def jwks(self) -> dict[str, list[dict[str, str]]]:
        """The public JWKS document (served at /.well-known/jwks.json)."""
        return {"keys": [k.jwk() for k in self.keys]}

    def with_key(self, key: VerifyKey) -> KeySet:
        others = tuple(k for k in self.keys if k.kid != key.kid)
        return KeySet((*others, key))


def parse_verify_keys(spec: str) -> tuple[VerifyKey, ...]:
    """Parse extra verification keys from ``"kid1:hexpub1,kid2:hexpub2"`` (rotation overlap).

    Public keys only — a resource server that is not the signer holds exactly these. Blank ⇒ none.
    """
    out: list[VerifyKey] = []
    for item in (s.strip() for s in spec.split(",")):
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"malformed verification key entry (want kid:hexpub): {item!r}")
        kid, hexpub = item.split(":", 1)
        out.append(VerifyKey(kid.strip(), bytes.fromhex(hexpub.strip())))
    return tuple(out)
