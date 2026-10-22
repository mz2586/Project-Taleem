"use client";
// Student ReadAloud — audio-first primitive with a VISIBLE label (never icon-only, the low-literacy
// access rule). It reads the visible text it is attached to:
//   1. the lesson's recorded audio when `audioSrc` is given;
//   2. otherwise (or if the recording cannot play) the device's own speech engine, in a voice for
//      the CONTENT's language `lang`, never the interface language;
//   3. otherwise it says plainly why there is no sound ("No Urdu voice on this device").
// The decisions are in lib/student/speech.ts. One utterance plays at a time across the page, and
// leaving the screen stops it.
import { useCallback, useEffect, useRef, useState } from "react";

import { languageName } from "../../lib/i18n/format";
import { useLocale } from "../../lib/i18n/useLocale";
import {
  browserSpeech,
  readAloudLabel,
  readAloudPlan,
  sharedSpeechChannel,
  statusFor,
  type ReadAloudStatus,
  type VoiceLike,
} from "../../lib/student/speech";

export function ReadAloud({
  audioSrc,
  text,
  lang,
  label,
}: {
  /** Recorded audio for this text (preferred when present). */
  audioSrc?: string;
  /** The visible text this button reads. */
  text?: string;
  /** The text's language (BCP 47). Unknown -> not spoken, rather than spoken in the wrong voice. */
  lang?: string | null;
  /** What is being read, for the accessible name ("Teacher", "Question"). */
  label: string;
}) {
  const { t, locale } = useLocale();
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const tokenRef = useRef<number | null>(null);
  const [engineAvailable, setEngineAvailable] = useState<boolean | null>(null); // null: not mounted yet
  const [voices, setVoices] = useState<VoiceLike[]>([]);
  const [recordedFailed, setRecordedFailed] = useState(false);
  const [playing, setPlaying] = useState(false);

  // Discover the engine and its voices after mount; many engines load voices asynchronously.
  useEffect(() => {
    const speech = browserSpeech();
    setEngineAvailable(!!speech);
    if (!speech) return;
    const refresh = () => setVoices(speech.engine.getVoices());
    refresh();
    const target = speech.engine as unknown as Partial<EventTarget>;
    target.addEventListener?.("voiceschanged", refresh);
    return () => target.removeEventListener?.("voiceschanged", refresh);
  }, []);

  const stopAll = useCallback(() => {
    const channel = sharedSpeechChannel();
    if (channel && tokenRef.current !== null) channel.stop(tokenRef.current);
    tokenRef.current = null;
    audioRef.current?.pause();
    setPlaying(false);
  }, []);

  // Leaving the screen (unmount, including route changes) stops this button's sound.
  useEffect(() => stopAll, [stopAll]);
  // New text means the old reading no longer matches the screen.
  useEffect(() => {
    stopAll();
    setRecordedFailed(false);
  }, [text, audioSrc, stopAll]);

  const plan = (failed: boolean) =>
    readAloudPlan({
      audioSrc,
      text,
      lang,
      engineAvailable: engineAvailable ?? false,
      voices: browserSpeech()?.engine.getVoices() ?? voices,
      recordedFailed: failed,
    });

  const speak = (failed: boolean) => {
    const next = plan(failed);
    if (next.kind !== "speech" || !text) return;
    const channel = sharedSpeechChannel();
    if (!channel) return;
    setPlaying(true);
    tokenRef.current = channel.speak(text, next.voice, next.lang, () => {
      tokenRef.current = null;
      setPlaying(false);
    });
  };

  const onClick = () => {
    if (playing) return stopAll();
    const next = plan(recordedFailed);
    if (next.kind === "recorded") {
      const el = audioRef.current;
      if (!el) return;
      sharedSpeechChannel()?.stopCurrent(); // one sound at a time
      setPlaying(true);
      void el.play().catch(() => {
        // Not cached and offline, or undecodable: fall back to the device voice.
        setPlaying(false);
        setRecordedFailed(true);
        speak(true);
      });
      return;
    }
    if (next.kind === "speech") speak(recordedFailed);
  };

  const status: ReadAloudStatus = playing
    ? { kind: "playing" }
    : engineAvailable === null && !audioSrc
      ? { kind: "pending" }
      : statusFor(plan(recordedFailed), lang);
  const { key, params } = readAloudLabel(status, (tag) => languageName(tag, locale));
  const visible = t(key, params);
  const unavailable = status.kind === "unavailable";

  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={playing}
      aria-disabled={unavailable || undefined}
      aria-label={`${visible}: ${label}`}
      data-state={status.kind}
      style={{
        minHeight: "var(--size-touch-min)",
        minWidth: "var(--size-touch-min)",
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-2)",
        padding: "var(--space-1) var(--space-3)",
        background: "transparent",
        border: "1px solid var(--color-focus-ring)",
        borderRadius: "var(--radius-md)",
        color: "var(--color-text-primary)",
        font: "inherit",
        cursor: unavailable ? "default" : "pointer",
        flexShrink: 0,
      }}
    >
      <span aria-hidden="true">{playing ? "⏹" : "🔊"}</span>
      <span>{visible}</span>
      {audioSrc ? (
        // Read-aloud of text that is already on screen next to this button: the visible text is the
        // transcript, so a caption <track> would duplicate it. Audio-only lesson media (no on-screen
        // text) must not use this component without captions.
        // eslint-disable-next-line jsx-a11y/media-has-caption
        <audio ref={audioRef} src={audioSrc} onEnded={() => setPlaying(false)} preload="none" />
      ) : null}
    </button>
  );
}
