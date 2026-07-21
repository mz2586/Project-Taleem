"use client";
// Student ReadAloud — audio-first primitive with a VISIBLE label (never icon-only, fixing the
// low-literacy access rule). Plays packaged Urdu audio; surfaces missing/offline states honestly.
import { useRef, useState } from "react";

type State = "idle" | "playing" | "unavailable";

export function ReadAloud({ audioSrc, label }: { audioSrc?: string; label: string }) {
  const [state, setState] = useState<State>(audioSrc ? "idle" : "unavailable");
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const onClick = () => {
    if (!audioSrc) {
      setState("unavailable");
      return;
    }
    const el = audioRef.current;
    if (!el) return;
    setState("playing");
    void el.play().catch(() => setState("unavailable"));
  };

  const text = state === "unavailable" ? "Audio not available" : state === "playing" ? "Playing…" : "Listen";
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={state === "playing"}
      aria-label={`${text}: ${label}`}
      data-state={state}
      style={{
        minHeight: "var(--size-touch-min)",
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-2)",
        padding: "var(--space-1) var(--space-3)",
        background: "transparent",
        border: "1px solid var(--color-focus-ring)",
        borderRadius: "var(--radius-md)",
        color: "var(--color-text-primary)",
        font: "inherit",
        cursor: "pointer",
      }}
    >
      <span aria-hidden="true">🔊</span>
      <span>{text}</span>
      {audioSrc ? (
        <audio ref={audioRef} src={audioSrc} onEnded={() => setState("idle")} preload="none" />
      ) : null}
    </button>
  );
}
