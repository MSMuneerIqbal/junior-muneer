"use client";

import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { Orb } from "@/components/call/Orb";
import { fetcher } from "@/lib/api";
import { urduClass } from "@/lib/urdu";
import { isChatsKey, USAGE_KEY } from "@/lib/keys";
import { useLiveCall, type Activity } from "@/lib/useLiveCall";

type Limits = { minutes_used: number; minutes_allowed: number; minutes_left: number };

const ACTIVITY: Record<Activity, string> = {
  listening: "Listening",
  you: "You're speaking",
  thinking: "Thinking",
  speaking: "Speaking",
  checking: "Searching",
};

function clock(ms: number) {
  const s = Math.max(0, Math.floor(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** The live call screen: a dark, glowing call view with a live transcript. */
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
    transcript.current?.scrollTo({ top: transcript.current.scrollHeight, behavior: "smooth" });
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

  const elapsed = call.startedAt ? now - call.startedAt : 0;
  const live = call.status === "live";
  const status =
    call.status === "connecting"
      ? "Connecting"
      : live
        ? call.muted
          ? "Muted"
          : ACTIVITY[call.activity]
        : call.status === "ended"
          ? "Call ended"
          : "Couldn't connect";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Live call"
      className="fixed inset-0 z-50 flex flex-col overflow-hidden text-slate-100"
      style={{
        background:
          "radial-gradient(1200px 700px at 50% 20%, #0b3b46 0%, #071a24 45%, #03070c 100%)",
      }}
    >
      {/* faint grid */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "linear-gradient(#5eead4 1px, transparent 1px), linear-gradient(90deg, #5eead4 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage: "radial-gradient(circle at 50% 35%, black, transparent 75%)",
        }}
      />

      <header className="relative flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3">
          <span
            className={`h-2.5 w-2.5 rounded-full ${live ? "animate-pulse bg-emerald-400 shadow-[0_0_12px_#34d399]" : "bg-slate-500"}`}
          />
          <div>
            <p className="text-sm font-semibold tracking-wide">JUNIOR MUNEER · LIVE</p>
            <p className="font-mono text-xs text-slate-400">
              {live ? clock(elapsed) : "--:--"}
              {limits && live ? ` · ${limits.minutes_left} min left today` : ""}
            </p>
          </div>
        </div>
        {(call.status === "ended" || call.status === "error") && (
          <button
            onClick={() => onClose(call.lines.length ? call.conversationId : null)}
            className="rounded-full border border-white/20 bg-white/5 px-4 py-1.5 text-sm backdrop-blur hover:bg-white/10"
          >
            Close
          </button>
        )}
      </header>

      {/* Left: the glowing orb and controls. Right: the conversation. Stacked on phones. */}
      <div className="relative flex min-h-0 flex-1 flex-col md:flex-row">
        <section className="flex flex-1 flex-col items-center justify-center px-4 md:w-[55%] md:flex-none">
          <Orb
            mic={call.micStream}
            remote={call.remoteStream}
            activity={call.activity}
            muted={call.muted}
          />
          <p
            role="status"
            className="mt-1 font-mono text-xs tracking-[0.3em] text-teal-200/90 uppercase"
          >
            {status}
            {(call.status === "connecting" ||
              (live && ["thinking", "checking"].includes(call.activity))) && (
              <span className="animate-pulse">…</span>
            )}
          </p>
          {call.error && (
            <p className="mt-2 max-w-md text-center text-sm text-rose-300">{call.error}</p>
          )}
          {call.status === "ended" && (
            <p className="mt-3 text-center text-sm text-slate-400 md:hidden">
              Saved in your chats. Tap Close to read it.
            </p>
          )}
          {(live || call.status === "connecting") && (
            <div className="flex items-center justify-center gap-5 pt-6 pb-4">
              <button
                onClick={call.toggleMute}
                disabled={!live}
                aria-pressed={call.muted}
                className="h-14 w-14 rounded-full border border-white/20 bg-white/5 text-xl backdrop-blur hover:bg-white/10 disabled:opacity-40"
                aria-label={call.muted ? "Unmute" : "Mute"}
                title={call.muted ? "Unmute" : "Mute"}
              >
                {call.muted ? "🔇" : "🎙"}
              </button>
              <button
                onClick={() => void call.end()}
                className="h-14 rounded-full bg-rose-500 px-8 text-sm font-semibold tracking-wide text-white shadow-[0_0_30px_rgba(244,63,94,0.45)] hover:bg-rose-400"
              >
                End call
              </button>
            </div>
          )}
        </section>

        <section className="hidden min-h-0 flex-1 flex-col border-l border-white/10 bg-black/25 backdrop-blur-sm md:flex">
          <p className="px-5 pt-4 pb-1 font-mono text-[11px] tracking-[0.3em] text-slate-400 uppercase">
            Conversation
          </p>
          <div
            ref={transcript}
            className="min-h-0 flex-1 overflow-y-auto px-5"
            aria-label="Live transcript"
            style={{ maskImage: "linear-gradient(transparent, black 6%, black 94%, transparent)" }}
          >
            <div className="flex flex-col gap-3 py-4">
              {call.lines.map((l) => (
                <div key={l.id} className={`flex ${l.who === "you" ? "justify-end" : ""}`}>
                  <p
                    dir="auto"
                    className={`max-w-[88%] rounded-2xl border px-4 py-2 ${
                      l.who === "you"
                        ? "border-violet-300/20 bg-violet-400/10"
                        : "border-teal-300/20 bg-teal-400/10"
                    } ${l.final ? "" : "opacity-70"} ${l.ignored ? "opacity-40" : ""} ${urduClass(l.text)}`}
                    title={l.ignored ? "Sounded like background noise, so he didn't reply" : undefined}
                  >
                    {l.text}
                    {l.ignored && <span className="ml-2 text-xs text-slate-400">(noise?)</span>}
                  </p>
                </div>
              ))}
              {live && !call.lines.length && (
                <p className="pt-8 text-center text-sm text-slate-400">
                  Say hello. Speak Urdu or English; you can interrupt him any time.
                </p>
              )}
              {call.status === "ended" && (
                <p className="text-center text-sm text-slate-400">Saved in your chats.</p>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
