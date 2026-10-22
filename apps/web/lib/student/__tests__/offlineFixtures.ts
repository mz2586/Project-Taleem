// Synthetic (C2-pattern) fixtures for the offline library/player tests: pseudonymous refs only,
// invented curriculum, a package signed by a key generated in the test. Never real child data.
import { contentHash } from "../../offline/sha256";
import { signingMessage } from "../../offline/signature";
import type { OfflineContent, OfflinePackage, SigningKey } from "../../offline/types";

export const SYNTHETIC_STUDENT = "stu_synthetic_offline_01";

export function syntheticContent(lessonId = "L-syn-frac"): OfflineContent {
  return {
    lesson_id: lessonId,
    objective_code: "SYN-G4-FR-01",
    title: { ur: "کسر کا تعارف", en: "Meet fractions" },
    explanation: { ur: "کسر ایک برابر حصہ ہے۔", en: "A fraction is an equal part." },
    worked_example_steps: ["Cut a roti into 4 equal parts.", "One part is 1/4."],
    practice_items: [
      { item_ref: "p1", objective_code: "SYN-G4-FR-01", prompt: { en: "Which is one half?" }, options: ["1/2", "1/3"], hints: ["Two equal parts.", "Look at the bottom number."] },
      { item_ref: "p2", objective_code: "SYN-G4-FR-01", prompt: { en: "Which is one quarter?" }, options: ["1/4", "4/1"], hints: [] },
    ],
    homework_items: [],
    assessment_formative: [
      { item_ref: "f1", objective_code: "SYN-G4-FR-01", prompt: { en: "Is 2/4 equal to 1/2?" }, options: ["Yes", "No"], hints: ["Draw it."] },
    ],
    summative_mentor_mediated: true,
  };
}

function hex(bytes: ArrayBuffer): string {
  return Array.from(new Uint8Array(bytes))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export interface SignedFixture {
  pkg: OfflinePackage;
  key: SigningKey;
  /** The same package with a signature made by a different key. */
  forged: OfflinePackage;
  unsigned: OfflinePackage;
}

export async function signedFixture(content: OfflineContent = syntheticContent(), keyId = "syn-key-1"): Promise<SignedFixture> {
  const sign = async () => (await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"])) as CryptoKeyPair;
  const pair = await sign();
  const other = await sign();
  const hash = await contentHash(content);
  const version = hash.slice(0, 12);
  const packageId = `pkg/${content.lesson_id}`;
  const msg = signingMessage(packageId, version, hash);
  const manifest = {
    package_id: packageId,
    lesson_id: content.lesson_id,
    objective_code: content.objective_code,
    version,
    content_hash: hash,
    assets: [{ ref: `${content.lesson_id}/content.json`, kind: "content", sha256: hash, bytes: 2048 }],
    total_bytes: 2048,
    created_at_ms: 0,
  };
  const signature = hex(await crypto.subtle.sign({ name: "Ed25519" }, pair.privateKey, msg));
  const forgedSignature = hex(await crypto.subtle.sign({ name: "Ed25519" }, other.privateKey, msg));
  const key: SigningKey = {
    key_id: keyId,
    algorithm: "Ed25519",
    public_key_hex: hex(await crypto.subtle.exportKey("raw", pair.publicKey)),
  };
  return {
    pkg: { manifest: { ...manifest, signature, signing_key_id: keyId }, content },
    forged: { manifest: { ...manifest, signature: forgedSignature, signing_key_id: keyId }, content },
    unsigned: { manifest, content },
    key,
  };
}
