"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { fetcher, send } from "@/lib/api";
import { PAUSE_KEY, PERMISSIONS_KEY } from "@/lib/keys";

type Mode = "rules" | "ask_all" | "pause";

const MODES: { value: Mode; icon: string; label: string; hint: string }[] = [
  {
    value: "rules",
    icon: "🛡",
    label: "Use my rules",
    hint: "Each action follows its Ask / Auto / Deny rule from Settings.",
  },
  {
    value: "ask_all",
    icon: "✋",
    label: "Ask everything",
    hint: "Every action waits for your OK, even ones set to Auto.",
  },
  {
    value: "pause",
    icon: "⏸",
    label: "Pause everything",
    hint: "Nothing is sent and no background work runs. Chat still works.",
  },
];

/**
 * Permissions, like Claude's permission modes: what Junior Muneer may do without asking.
 * A small menu under the message box.
 */
export function ModeSelect() {
  const { data, error, mutate } = useSWR<{ mode: "rules" | "ask_all"; paused: boolean }>(PERMISSIONS_KEY, fetcher);
  const { mutate: mutateGlobal } = useSWRConfig();
  const [open, setOpen] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const current: Mode = data?.paused ? "pause" : (data?.mode ?? "rules");
  const shown = MODES.find((m) => m.value === current)!;

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  async function choose(next: Mode) {
    setOpen(false);
    setProblem(null);
    try {
      if (next === "pause") {
        await send("POST", PAUSE_KEY, { paused: true });
      } else {
        await send("PUT", "/api/permissions/mode", { mode: next });
        if (data?.paused) await send("POST", PAUSE_KEY, { paused: false });
      }
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "Couldn't change it");
    }
    await mutate();
    void mutateGlobal(PAUSE_KEY);
  }

  if (error) {
    return (
      <p className="text-xs text-warn">
        Permissions aren&apos;t available: restart the backend (stop.bat, then start.bat).
      </p>
    );
  }

  return (
    <div ref={root} className="relative flex min-w-0 items-center gap-2 text-xs text-muted">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Permissions: ${shown.label}`}
        disabled={!data}
        onClick={() => setOpen(!open)}
        title={shown.hint}
        className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 transition hover:text-ink disabled:opacity-50 ${
          current === "rules" ? "border-line bg-panel" : "border-warn/40 bg-warn-soft text-warn"
        }`}
      >
        <span aria-hidden>{shown.icon}</span>
        <span>
          Permissions: <span className="font-medium">{shown.label}</span>
        </span>
        <span aria-hidden className="text-[10px]">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {problem && <span className="truncate text-danger">{problem}</span>}

      {open && (
        <div
          role="menu"
          aria-label="Permissions"
          className="absolute bottom-full left-0 z-30 mb-2 w-80 max-w-[calc(100vw-2rem)] rounded-2xl border border-line bg-panel p-1.5 text-ink shadow-lg"
        >
          <p className="px-3 pt-2 pb-1.5 text-xs text-muted">What may Junior Muneer do without asking you?</p>
          {MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              role="menuitemradio"
              aria-checked={m.value === current}
              onClick={() => choose(m.value)}
              className={`flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-panel-2 ${
                m.value === current ? "bg-accent-soft" : ""
              }`}
            >
              <span aria-hidden className="mt-0.5 text-base">
                {m.icon}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium">{m.label}</span>
                <span className="block text-xs text-muted">{m.hint}</span>
              </span>
              {m.value === current && <span className="mt-0.5 text-accent">✓</span>}
            </button>
          ))}
          <Link
            href="/settings#permissions"
            onClick={() => setOpen(false)}
            className="mt-1 block border-t border-line px-3 pt-2 pb-1.5 text-xs text-accent hover:underline"
          >
            Edit the rule for each action in Settings →
          </Link>
        </div>
      )}
    </div>
  );
}
