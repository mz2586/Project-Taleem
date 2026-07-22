// SHA-256 over the canonical offline content, matching the backend
// (offline_package.py: json.dumps(sort_keys, separators=(",",":")) then sha256 hex).
// Used to VERIFY a downloaded package's content against its manifest before install (integrity).

import type { OfflineContent } from "./types";

// Deterministic JSON matching Python's json.dumps(sort_keys=True, separators=(",",":")).
export function canonicalJson(value: unknown): string {
  return stringify(value);
}

function stringify(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "number") return numberToken(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stringify).join(",")}]`;
  if (typeof value === "object") {
    const obj = value as Record<string, unknown>;
    const keys = Object.keys(obj).sort();
    const parts = keys.map((k) => `${JSON.stringify(k)}:${stringify(obj[k])}`);
    return `{${parts.join(",")}}`;
  }
  return "null";
}

function numberToken(n: number): string {
  // Integers only in our content model; JSON.stringify covers the range we use.
  return JSON.stringify(n);
}

async function sha256HexFrom(text: string, subtle: SubtleCrypto): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// Hash the canonical serialization of an offline content document.
export async function contentHash(
  content: OfflineContent,
  subtle: SubtleCrypto = globalThis.crypto.subtle,
): Promise<string> {
  return sha256HexFrom(canonicalJson(content), subtle);
}

// Verify a downloaded package's content matches the hash its manifest claims.
export async function verifyContent(
  content: OfflineContent,
  expectedHash: string,
  subtle: SubtleCrypto = globalThis.crypto.subtle,
): Promise<boolean> {
  const actual = await contentHash(content, subtle);
  return actual === expectedHash;
}
