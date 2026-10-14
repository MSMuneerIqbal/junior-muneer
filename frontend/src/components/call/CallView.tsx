"use client";

import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { fetcher } from "@/lib/api";
import { isChatsKey, USAGE_KEY } from "@/lib/keys";
import { useLiveCall, type Activity } from "@/lib/useLiveCall";

type Limits = { minutes_used: number; minutes_allowed: number; minutes_left: number };

const ACTIVITY: Record<Activity, string> = {
  listening: "Listening…",
  you: "You're speaking",
  thinking: "Thinking…",
  speaking: "Junior Muneer is speaking",
  checking: "Checking…",
};

function clock(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The live call screen: hands-free conversation with a live transcript. */
export function CallView({ onClose }: { onClose: (conversationId: number | null) => void }) {
  const call = useLiveCall();
  const { mutate } = useSWRConfig();
  const { data: limits } = useSWR<Limits>("/api/call/limits", fetcher);
  const [now, setNow] = useState(() => Date.now());
  const started = useRef(false);
  const transcript = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    void call.start();
  }, [call]);

  useEffect(() => {
    if (call.status !== "live") return;
    const id = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(id);
  }, [call.status]);

  useEffect(() => {
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight });
  }, [call.lines]);

  useEffect(() => {
    if (call.status === "ended") {
      // The backend saves the call as a chat; refresh lists and spend.
      const t = setTimeout(() => {
        mutate(isChatsKey);
        mutate(USAGE_KEY);
        mutate("/api/call/limits");
      }, 1500);
      return () => clearTimeout(t);
    }
  }, [call.status, mutate]);

  async function hangUp() {
    await call.end();
  }

  const elapsed = call.startedAt ? now - call.startedAt : 0;
  const live = call.status === "live";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Live call"
      className="fixed inset-0 z-50 flex flex-col bg-bg"
    >
      <header className="flex items-center justify-between border-b border-line bg-panel px-4 py-3">
        <div>
          <p className="font-semibold">📞 Live call with Junior Muneer</p>
          <p className="text-xs text-muted">
            {call.status === "connecting" && "Connecting…"}
            {live && `${clock(elapsed)}${limits ? ` · ${limits.minutes_left} min left today` : ""}`}
            {call.status === "ended" && "Call ended. It's saved in your chats."}
            {call.status === "error" && "Couldn't connect"}
          </p>
        </div>
        {(call.status === "ended" || call.status === "error") && (
          <button
            onClick={() => onClose(call.lines.length ? call.conversationId : null)}
            className="rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-panel-2"
          >
            Close
          </button>
        )}
      </header>

      <div className="flex flex-col items-center gap-2 py-8">
        <div
          aria-hidden
          className={`flex h-28 w-28 items-center justify-center rounded-full text-5xl transition ${
            live && call.activity === "speaking"
              ? "scale-110 bg-accent text-accent-fg"
              : live && call.activity === "you"
                ? "bg-accent-soft ring-4 ring-accent"
                : "bg-panel-2"
          } ${live && !call.muted ? "" : "opacity-70"}`}
        >
          {call.muted ? "🔇" : "🎙"}
        </div>
        <p role="status" className="text-sm text-muted">
          {live ? (call.muted ? "Muted: he can't hear you" : ACTIVITY[call.activity]) : ""}
        </p>
        {call.error && <p className="max-w-md px-4 text-center text-sm text-danger">{call.error}</p>}
      </div>

      <div ref={transcript} className="min-h-0 flex-1 overflow-y-auto px-4" aria-label="Live transcript">
        <div className="mx-auto flex max-w-2xl flex-col gap-3 pb-6">
          {call.lines.map((l) => (
            <div key={l.id} className={`flex ${l.who === "you" ? "justify-end" : ""}`}>
              <p
                dir="auto"
                className={`max-w-[85%] rounded-2xl px-4 py-2 ${
                  l.who === "you" ? "bg-user" : "bg-panel ring-1 ring-line"
                } ${l.final ? "" : "opacity-70"}`}
              >
                {l.text}
              </p>
            </div>
          ))}
          {live && !call.lines.length && (
            <p className="text-center text-muted">Say hello. You can interrupt him any time.</p>
          )}
        </div>
      </div>

      {(live || call.status === "connecting") && (
        <footer className="flex items-center justify-center gap-4 border-t border-line bg-panel p-4">
          <button
            onClick={call.toggleMute}
            disabled={!live}
            aria-pressed={call.muted}
            className="rounded-full border border-line px-5 py-2.5 text-sm hover:bg-panel-2 disabled:opacity-40"
          >
            {call.muted ? "Unmute" : "Mute"}
          </button>
          <button
            onClick={hangUp}
            className="rounded-full bg-danger px-6 py-2.5 text-sm font-medium text-white"
          >
            End call
          </button>
        </footer>
      )}
    </div>
  );
}
