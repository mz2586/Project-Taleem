import { describe, expect, it } from "vitest";

import { languageName } from "../../i18n/format";
import { translate } from "../../i18n/translate";
import {
  createSpeechChannel,
  normalizeTag,
  readAloudLabel,
  readAloudPlan,
  selectVoice,
  speechLang,
  statusFor,
  type SpeechEnd,
  type SpeechEngine,
  type UtteranceLike,
  type VoiceLike,
} from "../speech";

// A fake speechSynthesis: records what was spoken and cancelled, and lets a test finish or interrupt
// the current utterance the way a real engine does (cancel raises onerror "interrupted").
class FakeEngine implements SpeechEngine {
  spoken: UtteranceLike[] = [];
  cancels = 0;
  queue: UtteranceLike[] = [];
  constructor(private voices: VoiceLike[] = []) {}
  getVoices() {
    return this.voices;
  }
  speak(u: UtteranceLike) {
    this.spoken.push(u);
    this.queue.push(u);
  }
  cancel() {
    this.cancels += 1;
    const pending = this.queue;
    this.queue = [];
    for (const u of pending) u.onerror?.({ error: "interrupted" });
  }
  finish() {
    const u = this.queue.shift();
    u?.onend?.();
  }
}

const makeUtterance = (text: string): UtteranceLike => ({ text, lang: "", voice: null, onend: null, onerror: null });

const UR_PK: VoiceLike = { lang: "ur-PK", name: "Urdu (Pakistan)", localService: true };
const UR_IN_NET: VoiceLike = { lang: "ur_IN", name: "Urdu India (network)", localService: false };
const EN_US: VoiceLike = { lang: "en-US", name: "English", localService: true, default: true };
const EN_GB_NET: VoiceLike = { lang: "en-GB", name: "English UK (network)", localService: false };
const AR: VoiceLike = { lang: "ar-SA", name: "Arabic", localService: true };

describe("selectVoice — by content language, never across languages", () => {
  const all = [EN_US, EN_GB_NET, UR_IN_NET, UR_PK, AR];

  it.each([
    ["exact tag", "ur-PK", UR_PK],
    ["exact tag, case/underscore-insensitive", "UR_in", UR_IN_NET],
    ["base language, preferring an on-device voice", "ur", UR_PK],
    ["region with no exact voice -> same language", "ur-AF", UR_PK],
    ["English content", "en-GB", EN_GB_NET],
    ["English base", "en", EN_US],
  ])("%s (%s)", (_name, lang, expected) => {
    expect(selectVoice(all, lang)).toBe(expected);
  });

  it("never reads Urdu with an English or Arabic voice", () => {
    expect(selectVoice([EN_US, EN_GB_NET, AR], "ur")).toBeNull();
    expect(selectVoice([EN_US], "ur-PK")).toBeNull();
  });

  it("returns null with no voices or no language", () => {
    expect(selectVoice([], "ur")).toBeNull();
    expect(selectVoice(all, "")).toBeNull();
  });

  it("normalises tags", () => {
    expect(normalizeTag(" ur_PK ")).toBe("ur-pk");
  });
});

describe("speechLang", () => {
  it("uses the declared content locale", () => {
    expect(speechLang("anything", "ur", "en")).toBe("ur");
  });
  it("uses the lesson locale only when the script agrees", () => {
    expect(speechLang("کسر پورے کا حصہ ہے۔", null, "ur")).toBe("ur");
    expect(speechLang("Step one", null, "ur")).toBeNull();
    expect(speechLang("Add the numbers", null, "en")).toBe("en");
  });
  it("is unknown without a declared or lesson locale, or for script-less text", () => {
    expect(speechLang("کسر", null, null)).toBeNull();
    expect(speechLang("12 + 3", null, "ur")).toBeNull();
  });
});

describe("readAloudPlan", () => {
  const base = { text: "کسر", lang: "ur", engineAvailable: true, voices: [UR_PK, EN_US] };

  it("prefers recorded audio when present, even with a voice available", () => {
    expect(readAloudPlan({ ...base, audioSrc: "/a.mp3" })).toEqual({ kind: "recorded", src: "/a.mp3" });
  });

  it("falls back to the device voice when the recording failed", () => {
    expect(readAloudPlan({ ...base, audioSrc: "/a.mp3", recordedFailed: true })).toEqual({
      kind: "speech",
      voice: UR_PK,
      lang: "ur-PK",
    });
  });

  it("speaks with the content-language voice", () => {
    expect(readAloudPlan(base)).toMatchObject({ kind: "speech", voice: UR_PK });
    expect(readAloudPlan({ ...base, text: "Add", lang: "en" })).toMatchObject({ kind: "speech", voice: EN_US });
  });

  it.each([
    ["no engine", { engineAvailable: false }, "no-engine"],
    ["no voice for the content language", { voices: [EN_US] }, "no-voice"],
    ["no voices loaded at all", { voices: [] }, "no-voice"],
    ["unknown content language", { lang: null }, "unknown-language"],
    ["no text", { text: "  " }, "no-text"],
    ["muted, even with a recording", { muted: true, audioSrc: "/a.mp3" }, "muted"],
  ] as const)("is unavailable: %s", (_name, override, reason) => {
    expect(readAloudPlan({ ...base, ...override })).toEqual({ kind: "unavailable", reason });
  });
});

describe("labels are honest about the source and the reason", () => {
  const nameEn = (tag: string) => languageName(tag, "en");
  const label = (plan: ReturnType<typeof readAloudPlan>, lang?: string) => {
    const { key, params } = readAloudLabel(statusFor(plan, lang), nameEn);
    return translate("en", key, params);
  };

  it("names the device voice and the missing language", () => {
    expect(label({ kind: "speech", voice: UR_PK, lang: "ur-PK" })).toBe("Listen · device voice");
    expect(label({ kind: "recorded", src: "/a.mp3" })).toBe("Listen");
    expect(label({ kind: "unavailable", reason: "no-voice" }, "ur")).toBe("No Urdu voice on this device");
    expect(label({ kind: "unavailable", reason: "no-engine" })).toBe("Read-aloud isn't available on this device");
    expect(label({ kind: "unavailable", reason: "muted" })).toBe("Read-aloud is turned off");
    expect(label({ kind: "unavailable", reason: "unknown-language" })).toBe("Audio not available");
  });

  it("names the language in the interface locale (Urdu UI)", () => {
    const { key, params } = readAloudLabel(
      { kind: "unavailable", reason: "no-voice", lang: "ur" },
      (tag) => languageName(tag, "ur"),
    );
    expect(translate("ur", key, params)).toBe("اس آلے پر اردو آواز دستیاب نہیں");
  });

  it("offers Stop while playing", () => {
    expect(readAloudLabel({ kind: "playing" }, nameEn).key).toBe("common.readAloud.stop");
  });
});

describe("speech channel — one utterance at a time", () => {
  it("speaks with the chosen voice and language, and reports a natural finish", () => {
    const engine = new FakeEngine();
    const channel = createSpeechChannel(engine, makeUtterance);
    const ends: SpeechEnd[] = [];
    const token = channel.speak("کسر", UR_PK, "ur-PK", (how) => ends.push(how));
    expect(engine.spoken[0]).toMatchObject({ text: "کسر", lang: "ur-PK", voice: UR_PK });
    expect(channel.current()).toBe(token);
    engine.finish();
    expect(ends).toEqual(["finished"]);
    expect(channel.current()).toBeNull();
  });

  it("cancels the previous utterance when another starts, telling the first it was replaced", () => {
    const engine = new FakeEngine();
    const channel = createSpeechChannel(engine, makeUtterance);
    const a: SpeechEnd[] = [];
    const b: SpeechEnd[] = [];
    channel.speak("one", UR_PK, "ur-PK", (how) => a.push(how));
    const second = channel.speak("two", UR_PK, "ur-PK", (how) => b.push(how));
    expect(a).toEqual(["replaced"]); // the late "interrupted" error is not reported twice
    expect(engine.cancels).toBeGreaterThanOrEqual(1);
    expect(engine.queue.map((u) => u.text)).toEqual(["two"]);
    expect(channel.current()).toBe(second);
    engine.finish();
    expect(b).toEqual(["finished"]);
  });

  it("stops only the current token; a stale stop is a no-op", () => {
    const engine = new FakeEngine();
    const channel = createSpeechChannel(engine, makeUtterance);
    const ends: SpeechEnd[] = [];
    const first = channel.speak("one", UR_PK, "ur-PK", () => undefined);
    const second = channel.speak("two", UR_PK, "ur-PK", (how) => ends.push(how));
    const cancelsBefore = engine.cancels;
    channel.stop(first); // stale (e.g. an unmounting button that was already replaced)
    expect(engine.cancels).toBe(cancelsBefore);
    expect(channel.current()).toBe(second);
    channel.stop(second); // unmount / navigation
    expect(ends).toEqual(["stopped"]);
    expect(engine.queue).toEqual([]);
  });

  it("stopCurrent silences whatever is speaking (before recorded audio plays)", () => {
    const engine = new FakeEngine();
    const channel = createSpeechChannel(engine, makeUtterance);
    const ends: SpeechEnd[] = [];
    channel.speak("one", UR_PK, "ur-PK", (how) => ends.push(how));
    channel.stopCurrent();
    expect(ends).toEqual(["stopped"]);
    expect(channel.current()).toBeNull();
  });

  it("reports an engine error", () => {
    const engine = new FakeEngine();
    const channel = createSpeechChannel(engine, makeUtterance);
    const ends: SpeechEnd[] = [];
    channel.speak("one", UR_PK, "ur-PK", (how) => ends.push(how));
    engine.queue[0]!.onerror?.({ error: "synthesis-failed" });
    expect(ends).toEqual(["error"]);
  });
});
