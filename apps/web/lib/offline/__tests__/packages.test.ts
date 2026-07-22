import { describe, expect, it } from "vitest";

import { MemoryStore } from "../kv";
import {
  DownloadManager,
  fitsInQuota,
  IntegrityError,
  QuotaExceededError,
} from "../packages";
import { contentHash } from "../sha256";
import type { OfflineContent, OfflinePackage, StorageEstimate } from "../types";

function offlineContent(overrides: Partial<OfflineContent> = {}): OfflineContent {
  return {
    lesson_id: "L1",
    objective_code: "MATH-G4-FR-01",
    title: { ur: "کسر", en: "Fractions" },
    explanation: { ur: "حصہ", en: "A fraction is an equal part." },
    worked_example_steps: ["one"],
    practice_items: [
      { item_ref: "p1", objective_code: "MATH-G4-FR-01", prompt: { en: "?" }, options: ["a", "b"], hints: ["h"] },
    ],
    homework_items: [],
    assessment_formative: [],
    summative_mentor_mediated: true,
    ...overrides,
  };
}

async function makePackage(content: OfflineContent, hashOverride?: string): Promise<OfflinePackage> {
  const hash = hashOverride ?? (await contentHash(content));
  return {
    manifest: {
      package_id: "pkg/L1",
      lesson_id: content.lesson_id,
      objective_code: content.objective_code,
      version: hash.slice(0, 12),
      content_hash: hash,
      assets: [{ ref: "L1/content.json", kind: "content", sha256: hash, bytes: 100 }],
      total_bytes: 100,
      created_at_ms: 0,
    },
    content,
  };
}

describe("storage pre-flight", () => {
  it("fits within available space, respecting headroom", () => {
    const est: StorageEstimate = { usage: 800, quota: 1000 }; // 200 available
    expect(fitsInQuota(150, est)).toBe(true);
    expect(fitsInQuota(200, est)).toBe(true);
    expect(fitsInQuota(201, est)).toBe(false);
    expect(fitsInQuota(150, est, 100)).toBe(false); // 100 reserved
  });
});

describe("download manager", () => {
  it("downloads, verifies, and installs a package; then renders it offline", async () => {
    const store = new MemoryStore();
    const pkg = await makePackage(offlineContent());
    const progress: number[] = [];
    const mgr = new DownloadManager({
      store,
      fetchPackage: async () => pkg,
      now: () => 123,
    });

    const rec = await mgr.download("L1", (f) => progress.push(f));
    expect(rec.state).toBe("ready");
    expect(rec.content_hash).toBe(pkg.manifest.content_hash);
    expect(progress[0]).toBe(0);
    expect(progress.at(-1)).toBe(1);

    // Offline render: the cached lesson is available without any network.
    const lesson = await mgr.getLesson("L1");
    expect(lesson?.lesson_id).toBe("L1");
    expect(await mgr.isCurrent(pkg.manifest)).toBe(true);
    // Safety: no answer keys were stored on the device.
    expect(JSON.stringify(lesson)).not.toContain("correct_option");
  });

  it("rejects a tampered package (integrity) and installs nothing", async () => {
    const store = new MemoryStore();
    // Manifest claims a hash that does not match the (tampered) content.
    const pkg = await makePackage(offlineContent(), "deadbeef".repeat(8));
    const mgr = new DownloadManager({ store, fetchPackage: async () => pkg, now: () => 0 });

    await expect(mgr.download("L1")).rejects.toBeInstanceOf(IntegrityError);
    expect(await mgr.getLesson("L1")).toBeUndefined();
    expect(await mgr.installed("L1")).toBeUndefined();
  });

  it("refuses a download that would exceed storage (quota) and installs nothing", async () => {
    const store = new MemoryStore();
    const pkg = await makePackage(offlineContent());
    const mgr = new DownloadManager({
      store,
      fetchPackage: async () => pkg,
      now: () => 0,
      estimate: async () => ({ usage: 950, quota: 1000 }), // only 50 free, pack needs 100
    });

    await expect(mgr.download("L1")).rejects.toBeInstanceOf(QuotaExceededError);
    expect(await mgr.installed("L1")).toBeUndefined();
  });

  it("removes a cached package (disposable eviction)", async () => {
    const store = new MemoryStore();
    const pkg = await makePackage(offlineContent());
    const mgr = new DownloadManager({ store, fetchPackage: async () => pkg, now: () => 0 });
    await mgr.download("L1");
    await mgr.remove("L1");
    expect(await mgr.getLesson("L1")).toBeUndefined();
    expect(await mgr.installedPackages()).toHaveLength(0);
  });
});
