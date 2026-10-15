"use client";

import { useEffect, useRef, useState } from "react";
import { BACKEND_URL } from "@/lib/api";
import { useRecorder, type Recording } from "@/lib/useRecorder";

export type VoiceMessage = { text: string; audioId: string; seconds: number };

const MIN_SECONDS = 0.6;
const TAP_MS = 300;

async function transcribe(rec: Recording): Promise<VoiceMessage> {
  const ext = rec.mimeType.includes("mp4") ? "m4a" : rec.mimeType.includes("ogg") ? "ogg" : "webm";
  const form = new FormData();
  form.append("audio", new File([rec.blob], `voice.${ext}`, { type: rec.mimeType.split(";")[0] }));
  form.append("seconds", rec.seconds.toFixed(1));
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api/voice/transcribe`, { method: "POST", body: form });
  } catch {
    throw new Error("Can't reach the backend.");
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail ?? `Speech-to-text failed (${res.status})`);
  return { text: body.text, audioId: body.audio_id, seconds: body.seconds };
}

function clock(s: number) {
  const m = Math.floor(s / 60);
  return `${m}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

/**
 * 🎙 Hold to talk and release to send — or tap to start and tap again to send.
 * Esc cancels. The recording is transcribed, then sent like a typed message.
 */
export function MicButton({
  onVoice,
  disabled,
}: {
  onVoice: (v: VoiceMessage) => void;
  disabled?: boolean;
}) {
  const { recording, elapsed, error, start, stop, setError } = useRecorder();
  const [busy, setBusy] = useState(false);
  const pressedAt = useRef(0);
  const [tapMode, setTapMode] = useState(false);

  async function finish(cancel = false) {
    const rec = await stop(cancel);
    setTapMode(false);
    if (cancel) return;
    // A very quick tap can end before any sound is recorded at all.
    if (!rec || rec.seconds < MIN_SECONDS) {
      setError("Too short. Hold the mic button while you speak.");
      return;
    }
    setBusy(true);
    try {
      const v = await transcribe(rec);
      if (!v.text.trim()) setError("I didn't catch that. Please try again.");
      else onVoice(v);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Speech-to-text failed");
    } finally {
      setBusy(false);
    }
  }

  async function onPointerDown(e: React.PointerEvent) {
    if (disabled || busy) return;
    e.preventDefault();
    if (recording) {
      void finish(); // second tap in tap mode
      return;
    }
    pressedAt.current = Date.now();
    await start();
  }

  function onPointerUp() {
    if (!recording) return;
    if (Date.now() - pressedAt.current < TAP_MS) {
      setTapMode(true); // a quick tap: keep recording until the next tap
      return;
    }
    if (!tapMode) void finish();
  }

  useEffect(() => {
    if (!recording) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && void finish(true);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recording]);

  return (
    <>
      <button
        type="button"
        onPointerDown={onPointerDown}
        onPointerUp={onPointerUp}
        onContextMenu={(e) => e.preventDefault()}
        disabled={disabled || busy}
        aria-label={recording ? "Stop and send voice message" : "Record a voice message"}
        aria-pressed={recording}
        title="Hold to talk, or tap to start and tap again to send"
        className={`flex h-8 w-8 shrink-0 touch-none items-center justify-center rounded-full text-base select-none ${
          recording ? "animate-pulse bg-danger text-white" : "text-muted hover:bg-panel-2"
        } disabled:opacity-40`}
      >
        {busy ? "…" : "🎙"}
      </button>
      {(recording || busy || error) && (
        <div className="absolute -top-8 left-3 rounded-md bg-panel px-2 py-1 text-xs shadow ring-1 ring-line">
          {recording ? (
            <span className="text-danger">
              ● {clock(elapsed)} · {tapMode ? "tap 🎙 to send" : "release to send"} · Esc
              cancels
            </span>
          ) : busy ? (
            <span className="text-muted">Transcribing…</span>
          ) : (
            <span className="text-danger">{error}</span>
          )}
        </div>
      )}
    </>
  );
}
