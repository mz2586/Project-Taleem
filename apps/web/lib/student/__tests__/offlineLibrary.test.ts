import { describe, expect, it } from "vitest";

import { MemoryStore, STORES } from "../../offline/kv";
import { IntegrityError, QuotaExceededError, SignatureError } from "../../offline/packages";
import type { PackageManifest, StoredPackage } from "../../offline/types";
import { translate } from "../../i18n/translate";
import {
  classifyDownloadError,
  configuredSigningKeys,
  createLibrary,
  DOWNLOAD_FAILURE_COPY,
  formatBytes,
  libraryModel,
  mergeSigningKeys,
} from "../offlineLibrary";
import { ApiError } from "../types";
import { signedFixture, syntheticContent } from "./offlineFixtures";

function manifest(lessonId: string, hash = "h1", bytes = 1000): PackageManifest {
  return {
    package_id: `pkg/${lessonId}`,
    lesson_id: lessonId,
    objective_code: `OBJ-${lessonId}`,
    version: hash.slice(0, 12),
    content_hash: hash,
    assets: [],
    total_bytes: bytes,
    created_at_ms: 0,
  };
}

function stored(lessonId: string, hash = "h1", bytes = 1000): StoredPackage {
  return {
    package_id: `pkg/${lessonId}`,
    lesson_id: lessonId,
    content_hash: hash,
    version: hash.slice(0, 12),
    state: "ready",
    total_bytes: bytes,
    installed_at: 1,
    last_used_at: 1,
    signature_ok: true,
  };
}

describe("libraryModel", () => {
  it("is loading until the list and the local registry are read", () => {
    expect(libraryModel({ list: { status: "pending" }, installed: [], titles: {}, downloads: {} }).kind).toBe("loading");
    expect(libraryModel({ list: { status: "ok", manifests: [] }, installed: null, titles: {}, downloads: {} }).kind).toBe("loading");
  });

  it("says plainly that nothing is published yet (today's reality)", () => {
    const model = libraryModel({ list: { status: "ok", manifests: [] }, installed: [], titles: {}, downloads: {} });
    expect(model).toEqual({ kind: "nothing-published" });
  });

  it("lists available, downloading, installed and updatable lessons", () => {
    const model = libraryModel({
      list: { status: "ok", manifests: [manifest("A"), manifest("B"), manifest("C", "new")] },
      installed: [stored("B"), stored("C", "old")],
      titles: { B: { ur: "کسر", en: "Fractions" } },
      downloads: { A: { kind: "downloading", fraction: 0.5 } },
    });
    if (model.kind !== "list") throw new Error(model.kind);
    expect(model.entries.map((e) => [e.lessonId, e.status])).toEqual([
      ["A", { kind: "downloading", fraction: 0.5 }],
      ["B", { kind: "installed", updateAvailable: false }],
      ["C", { kind: "installed", updateAvailable: true }],
    ]);
    expect(model.entries[1]!.title).toEqual({ text: "کسر", locale: "ur" });
    expect(model.installedBytes).toBe(2000);
  });

  it("offline: still shows what is on the phone", () => {
    const model = libraryModel({ list: { status: "error", error: new ApiError(0, {}) }, installed: [stored("B")], titles: {}, downloads: {} });
    expect(model).toMatchObject({ kind: "list", listUnavailable: true, entries: [{ lessonId: "B" }] });
  });

  it("keeps a failed download's reason, and whether a copy is still installed", () => {
    const model = libraryModel({
      list: { status: "ok", manifests: [manifest("A"), manifest("B")] },
      installed: [stored("B")],
      titles: {},
      downloads: { A: { kind: "failed", reason: "signature" }, B: { kind: "failed", reason: "offline" } },
    });
    if (model.kind !== "list") throw new Error(model.kind);
    expect(model.entries.map((e) => e.status)).toEqual([
      { kind: "failed", reason: "signature", installed: false },
      { kind: "failed", reason: "offline", installed: true },
    ]);
  });
});

describe("download failures", () => {
  it("classifies each failure and explains it in both languages", () => {
    expect(classifyDownloadError(new SignatureError("L", "k"))).toBe("signature");
    expect(classifyDownloadError(new IntegrityError("L"))).toBe("integrity");
    expect(classifyDownloadError(new QuotaExceededError(10, 1))).toBe("storage");
    expect(classifyDownloadError(new ApiError(0, {}))).toBe("offline");
    expect(classifyDownloadError(new ApiError(404, {}))).toBe("gone");
    expect(classifyDownloadError(new Error("x"))).toBe("error");
    for (const key of Object.values(DOWNLOAD_FAILURE_COPY)) {
      expect(translate("en", key)).not.toBe(key);
      expect(translate("ur", key)).not.toBe(key);
    }
    expect(translate("en", DOWNLOAD_FAILURE_COPY.signature)).toMatch(/not saved/);
  });
});

describe("mergeSigningKeys (trust on first use)", () => {
  it("remembers a key the first time it is seen", () => {
    const merged = mergeSigningKeys({ configured: {}, remembered: {}, fetched: [{ key_id: "k1", algorithm: "Ed25519", public_key_hex: "AA" }] });
    expect(merged.keys).toEqual({ k1: "aa" });
    expect(merged.remember).toEqual({ k1: "aa" });
  });

  it("refuses a changed key for a known key id", () => {
    const merged = mergeSigningKeys({ configured: {}, remembered: { k1: "aa" }, fetched: [{ key_id: "k1", algorithm: "Ed25519", public_key_hex: "bb" }] });
    expect(merged.conflicts).toEqual(["k1"]);
    expect(merged.keys).toEqual({});
    expect(merged.remember).toEqual({ k1: "aa" });
  });

  it("lets build-time keys win and ignores non-Ed25519 keys", () => {
    const merged = mergeSigningKeys({
      configured: { k1: "cc" },
      remembered: {},
      fetched: [
        { key_id: "k1", algorithm: "Ed25519", public_key_hex: "dd" },
        { key_id: "k2", algorithm: "RSA", public_key_hex: "ee" },
      ],
    });
    expect(merged.keys).toEqual({ k1: "cc" });
  });

  it("parses configured keys defensively", () => {
    expect(configuredSigningKeys('{"k1":"aa","bad":3}')).toEqual({ k1: "aa" });
    expect(configuredSigningKeys("not json")).toEqual({});
    expect(configuredSigningKeys(undefined)).toEqual({});
  });
});

describe("createLibrary — install only verified packages", () => {
  async function setup(serve: "signed" | "forged" | "unsigned") {
    const fx = await signedFixture();
    const store = new MemoryStore();
    const library = createLibrary({
      store,
      listPackages: async () => ({ packages: [fx.pkg.manifest] }),
      fetchPackage: async () => (serve === "signed" ? fx.pkg : serve === "forged" ? fx.forged : fx.unsigned),
      signingKeys: async () => ({ keys: [fx.key] }),
    });
    return { fx, store, library };
  }

  it("installs a correctly signed package", async () => {
    const { library } = await setup("signed");
    const progress: number[] = [];
    const rec = await library.install("L-syn-frac", (f) => progress.push(f));
    expect(rec).toMatchObject({ state: "ready", signature_ok: true });
    expect(progress.at(-1)).toBe(1);
    expect((await library.installed()).map((p) => p.lesson_id)).toEqual(["L-syn-frac"]);
    expect(await library.titles(["L-syn-frac"])).toEqual({ "L-syn-frac": syntheticContent().title });
  });

  it("refuses a package signed by another key and writes nothing", async () => {
    const { library, store } = await setup("forged");
    await expect(library.install("L-syn-frac")).rejects.toBeInstanceOf(SignatureError);
    expect(await library.installed()).toEqual([]);
    expect(await store.get(STORES.content, "L-syn-frac")).toBeUndefined();
  });

  it("refuses an unsigned package (never installs unverified)", async () => {
    const { library } = await setup("unsigned");
    await expect(library.install("L-syn-frac")).rejects.toBeInstanceOf(SignatureError);
    expect(await library.installed()).toEqual([]);
  });

  it("removes a lesson", async () => {
    const { library } = await setup("signed");
    await library.install("L-syn-frac");
    await library.remove("L-syn-frac");
    expect(await library.installed()).toEqual([]);
  });
});

describe("formatBytes", () => {
  it("formats sizes in the interface locale", () => {
    expect(formatBytes(2048, "en")).toMatch(/^2 kB$/);
    expect(formatBytes(1_500_000, "en")).toMatch(/^1\.5 MB$/);
    expect(formatBytes(0, "en")).toMatch(/^0\s/);
  });
});
