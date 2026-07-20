// ReadAloud — the mandated low-literacy primitive (docs/16 §7, audit AR-C-19/AR-H-11).
// Every instructional text pairs with this. States: idle | playing | loading | unavailable | offline.
// Prefers pre-recorded Urdu audio (mandatory for core-path text); TTS is a controlled fallback only.
import { useState } from "react";

type State = "idle" | "playing" | "loading" | "unavailable" | "offline";

interface ReadAloudProps {
  audioSrc?: string; // pre-recorded Urdu audio (packaged offline)
  label: string; // accessible label
}

export function ReadAloud({ audioSrc, label }: ReadAloudProps) {
  const [state, setState] = useState<State>(audioSrc ? "idle" : "unavailable");

  const onClick = () => {
    if (!audioSrc) {
      setState("unavailable"); // never silently no-op; surfaces the missing-audio state
      return;
    }
    setState("playing");
    // Real impl: play packaged audio; if absent and offline, show "offline"; TTS fallback if permitted.
  };

  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={`🔊 ${label}`}
      data-state={state}
      style={{
        minHeight: "var(--size-touch-min)",
        minWidth: "var(--size-touch-min)",
        background: "transparent",
        border: "1px solid var(--color-focus-ring)",
        borderRadius: "var(--radius-md)",
        color: "var(--color-text-primary)",
      }}
    >
      🔊 {state === "unavailable" ? "—" : ""}
    </button>
  );
}
