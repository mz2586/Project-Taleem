// Read-aloud decisions and the single shared speech channel. No React; the engine is injected, so
// all of this is unit-tested with a fake `speechSynthesis`.
//
// Phase E, first step: speak the visible text with the device's own speech engine (Web Speech API),
// with zero asset cost. The rules:
//
// - **Recorded audio wins.** When a lesson ships a recording, that is what the child hears; the
//   device voice is the fallback, including when the recording fails to play (e.g. not cached and
//   offline).
// - **The voice is chosen by the CONTENT's language, never the interface language.** An Urdu lesson
//   in an English interface is read by an Urdu voice. Exact BCP 47 tag first, then the same base
//   language; otherwise read-aloud is honestly unavailable. Urdu text is never read by an English
//   voice — mispronounced instruction is worse than none.
// - **One utterance at a time,** across every button on the page: starting one cancels the other,
//   and the cancelled button is told so it can return to idle.
// - Device voices usually work offline (most engines are local), but not on every device — network
//   voices are only preferred last, and nothing here claims offline support for a given device.

import { baseLanguage, directionOf } from "../i18n/config";
import { scriptDirection } from "../i18n/content";
import type { MessageKey } from "../i18n/messages";

// ---- the engine surface we use (a subset of SpeechSynthesis / SpeechSynthesisVoice) ------------

export interface VoiceLike {
  lang: string;
  name: string;
  /** True when the voice runs on the device (works offline). */
  localService?: boolean;
  default?: boolean;
}

export interface UtteranceLike {
  text: string;
  lang: string;
  voice: VoiceLike | null;
  onend: (() => void) | null;
  onerror: ((event: { error?: string }) => void) | null;
}

export interface SpeechEngine {
  speak(utterance: UtteranceLike): void;
  cancel(): void;
  getVoices(): VoiceLike[];
}

export type UtteranceFactory = (text: string) => UtteranceLike;

/** The browser's engine, or null where there is none (server render, old browsers, some WebViews). */
export function browserSpeech(): { engine: SpeechEngine; makeUtterance: UtteranceFactory } | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    speechSynthesis?: SpeechEngine;
    SpeechSynthesisUtterance?: new (text: string) => UtteranceLike;
  };
  if (!w.speechSynthesis || typeof w.SpeechSynthesisUtterance !== "function") return null;
  const Utterance = w.SpeechSynthesisUtterance;
  return { engine: w.speechSynthesis, makeUtterance: (text) => new Utterance(text) };
}

// ---- voice selection ----------------------------------------------------------------------------

/** "ur_PK" / "UR-pk" -> "ur-pk": comparable form of a BCP 47 tag. */
export function normalizeTag(tag: string): string {
  return tag.trim().replace(/_/g, "-").toLowerCase();
}

// Among equally good matches: on-device first (works offline), then the engine's default.
function rank(v: VoiceLike): number {
  return (v.localService ? 2 : 0) + (v.default ? 1 : 0);
}

function best(voices: VoiceLike[]): VoiceLike | null {
  return voices.reduce<VoiceLike | null>((acc, v) => (acc === null || rank(v) > rank(acc) ? v : acc), null);
}

/**
 * The voice for content in `lang`: an exact tag match, else a voice of the same base language
 * ("ur" content -> an "ur-PK" voice, "ur-IN" content -> "ur-PK" if that is all there is). Null when
 * the device has no voice for that language — never a voice for a different language.
 */
export function selectVoice(voices: readonly VoiceLike[], lang: string): VoiceLike | null {
  const want = normalizeTag(lang);
  if (!want) return null;
  const exact = voices.filter((v) => normalizeTag(v.lang) === want);
  if (exact.length) return best(exact);
  const base = baseLanguage(want);
  const sameLanguage = voices.filter((v) => baseLanguage(normalizeTag(v.lang)) === base);
  return best(sameLanguage);
}

/**
 * The language to read `text` in. A declared content locale wins. Otherwise the lesson's locale is
 * used only if the text's script agrees with it (an English example inside an Urdu lesson is not
 * Urdu). Null means "unknown" — and unknown is not read aloud, because guessing is how Urdu ends up
 * in an English voice.
 */
export function speechLang(text: string, declared?: string | null, lessonLocale?: string | null): string | null {
  if (declared) return declared;
  if (!lessonLocale) return null;
  const dir = scriptDirection(text);
  return dir !== null && dir === directionOf(lessonLocale) ? lessonLocale : null;
}

// ---- what pressing the button does ---------------------------------------------------------------

export type Unavailable = "no-text" | "no-engine" | "no-voice" | "unknown-language" | "muted";

export type ReadAloudPlan =
  | { kind: "recorded"; src: string }
  | { kind: "speech"; voice: VoiceLike; lang: string }
  | { kind: "unavailable"; reason: Unavailable };

export function readAloudPlan(input: {
  audioSrc?: string | null;
  text?: string | null;
  lang?: string | null;
  /** False when there is no speech engine on this device. */
  engineAvailable: boolean;
  voices: readonly VoiceLike[];
  /** A person's "no read-aloud" preference, when one is set. */
  muted?: boolean;
  /** The recording was tried and could not play; fall back to the device voice. */
  recordedFailed?: boolean;
}): ReadAloudPlan {
  if (input.muted) return { kind: "unavailable", reason: "muted" };
  if (input.audioSrc && !input.recordedFailed) return { kind: "recorded", src: input.audioSrc };
  const text = input.text?.trim() ?? "";
  if (!text) return { kind: "unavailable", reason: "no-text" };
  if (!input.engineAvailable) return { kind: "unavailable", reason: "no-engine" };
  if (!input.lang) return { kind: "unavailable", reason: "unknown-language" };
  const voice = selectVoice(input.voices, input.lang);
  if (!voice) return { kind: "unavailable", reason: "no-voice" };
  return { kind: "speech", voice, lang: voice.lang || input.lang };
}

// ---- the single speech channel -------------------------------------------------------------------

export type SpeechEnd = "finished" | "replaced" | "stopped" | "error";

export interface SpeechChannel {
  /** Speak, cancelling whatever was speaking (its `onDone` gets "replaced"). Returns a token. */
  speak(text: string, voice: VoiceLike, lang: string, onDone: (how: SpeechEnd) => void): number;
  /** Stop `token` if it is still the one speaking (a no-op for a stale token). */
  stop(token: number): void;
  /** The token currently speaking, or null. */
  current(): number | null;
  /** Stop whatever is speaking (e.g. before recorded audio plays). */
  stopCurrent(): void;
}

export function createSpeechChannel(engine: SpeechEngine, makeUtterance: UtteranceFactory): SpeechChannel {
  let active: { token: number; onDone: (how: SpeechEnd) => void } | null = null;
  let counter = 0;

  const settle = (token: number, how: SpeechEnd) => {
    if (active?.token !== token) return; // already settled (e.g. cancel fires onend/onerror late)
    const { onDone } = active;
    active = null;
    onDone(how);
  };

  return {
    speak(text, voice, lang, onDone) {
      if (active) settle(active.token, "replaced");
      // Always cancel: the engine queues by default, and a queue is not "one at a time".
      engine.cancel();
      const token = ++counter;
      active = { token, onDone };
      const utterance = makeUtterance(text);
      utterance.lang = lang;
      utterance.voice = voice;
      utterance.onend = () => settle(token, "finished");
      // Cancelling raises "interrupted"/"canceled" on the old utterance; settle() ignores it then.
      utterance.onerror = () => settle(token, "error");
      engine.speak(utterance);
      return token;
    },
    stop(token) {
      if (active?.token !== token) return;
      settle(token, "stopped");
      engine.cancel();
    },
    current() {
      return active?.token ?? null;
    },
    stopCurrent() {
      if (active) settle(active.token, "stopped");
      engine.cancel();
    },
  };
}

// One channel per page, shared by every ReadAloud button.
let shared: SpeechChannel | null | undefined;

export function sharedSpeechChannel(): SpeechChannel | null {
  if (shared !== undefined) return shared;
  const speech = browserSpeech();
  shared = speech ? createSpeechChannel(speech.engine, speech.makeUtterance) : null;
  return shared;
}

// ---- what the button says ------------------------------------------------------------------------

export type ReadAloudStatus =
  /** Before mount the engine is unknown; the button just says "Listen". */
  | { kind: "pending" }
  | { kind: "ready"; via: "recorded" | "device" }
  | { kind: "playing" }
  | { kind: "unavailable"; reason: Unavailable; lang?: string | null };

export function statusFor(plan: ReadAloudPlan, lang?: string | null): ReadAloudStatus {
  if (plan.kind === "recorded") return { kind: "ready", via: "recorded" };
  if (plan.kind === "speech") return { kind: "ready", via: "device" };
  return { kind: "unavailable", reason: plan.reason, lang };
}

/**
 * The visible label for a status: honest about where the sound comes from and why there is none.
 * `languageNameOf` names the content language in the interface locale ("No Urdu voice…").
 */
export function readAloudLabel(
  status: ReadAloudStatus,
  languageNameOf: (tag: string) => string,
): { key: MessageKey; params?: { language: string } } {
  switch (status.kind) {
    case "pending":
      return { key: "common.readAloud.listen" };
    case "ready":
      return { key: status.via === "device" ? "common.readAloud.listenDevice" : "common.readAloud.listen" };
    case "playing":
      return { key: "common.readAloud.stop" };
    case "unavailable":
      switch (status.reason) {
        case "no-engine":
          return { key: "common.readAloud.noEngine" };
        case "no-voice":
          return status.lang
            ? { key: "common.readAloud.noVoice", params: { language: languageNameOf(status.lang) } }
            : { key: "common.readAloud.unavailable" };
        case "muted":
          return { key: "common.readAloud.muted" };
        default:
          return { key: "common.readAloud.unavailable" };
      }
  }
}
