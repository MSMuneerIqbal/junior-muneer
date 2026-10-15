"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { fetcher, send } from "@/lib/api";
import { PAUSE_KEY, PERMISSIONS_KEY } from "@/lib/keys";

type Mode = "rules" | "ask_all" | "plan";

// Like Claude's permission modes.
const MODES: { value: Mode; label: string; hint: string }[] = [
  { value: "rules", label: "Auto", hint: "Follows your rules: safe actions run, the rest wait for you" },
  { value: "ask_all", label: "Manual", hint: "Always asks before doing anything" },
  { value: "plan", label: "Plan", hint: "Shows a plan first and does nothing until you switch" },
];

/** The mode menu under the message box. Keys 1–3 pick a mode while it's open. */
export function ModeSelect() {
  const { data, error, mutate } = useSWR<{ mode: Mode; paused: boolean }>(PERMISSIONS_KEY, fetcher);
  const { mutate: mutateGlobal } = useSWRConfig();
  const [open, setOpen] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const mode = data?.mode ?? "rules";
  const paused = data?.paused ?? false;
  const shown = MODES.find((m) => m.value === mode) ?? MODES[0];

  async function run(action: () => Promise<unknown>) {
    setOpen(false);
    setProblem(null);
    try {
      await action();
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "Couldn't change it");
    }
    await mutate();
    void mutateGlobal(PAUSE_KEY);
  }
  const choose = (next: Mode) => run(() => send("PUT", "/api/permissions/mode", { mode: next }));
  const togglePause = () => run(() => send("POST", PAUSE_KEY, { paused: !paused }));

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      const n = Number(e.key);
      if (n >= 1 && n <= MODES.length) {
        e.preventDefault();
        void choose(MODES[n - 1].value);
      }
    };
    const onClick = (e: MouseEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onClick);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onClick);
    };
    // choose is stable enough for a listener that lives while the menu is open
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (error) {
    return (
      <p className="text-xs text-warn">Modes aren&apos;t available: restart the backend (stop.bat, then start.bat).</p>
    );
  }

  return (
    <div ref={root} className="relative flex min-w-0 items-center gap-2 text-xs text-muted">
      <button
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Mode: ${shown.label}${paused ? ", paused" : ""}`}
        disabled={!data}
        onClick={() => setOpen(!open)}
        title={shown.hint}
        className={`flex items-center gap-1.5 rounded-full border px-2.5 py-1 transition hover:text-ink disabled:opacity-50 ${
          paused || mode !== "rules" ? "border-warn/40 bg-warn-soft text-warn" : "border-line bg-panel"
        }`}
      >
        <span className="font-medium">{paused ? "Paused" : shown.label}</span>
        <span aria-hidden className="text-[10px]">
          {open ? "▴" : "▾"}
        </span>
      </button>
      {problem && <span className="truncate text-danger">{problem}</span>}

      {open && (
        <div
          role="menu"
          aria-label="Mode"
          className="absolute bottom-full left-0 z-30 mb-2 w-80 max-w-[calc(100vw-2rem)] rounded-xl border border-line bg-panel py-1.5 text-ink shadow-lg"
        >
          <p className="px-3.5 pt-1 pb-1.5 text-xs text-muted">Mode</p>
          {MODES.map((m, i) => (
            <button
              key={m.value}
              type="button"
              role="menuitemradio"
              aria-checked={m.value === mode}
              onClick={() => choose(m.value)}
              className="flex w-full items-start gap-3 px-3.5 py-2 text-left transition hover:bg-panel-2"
            >
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold">{m.label}</span>
                <span className="block text-xs text-muted">{m.hint}</span>
              </span>
              <span className="mt-0.5 flex items-center gap-2 text-xs text-muted">
                {m.value === mode && <span className="text-accent">✓</span>}
                <span className="tabular-nums">{i + 1}</span>
              </span>
            </button>
          ))}
          <div className="mt-1 flex items-center justify-between border-t border-line px-3.5 pt-2 pb-1">
            <span className="text-sm font-semibold">Pause everything</span>
            <button
              type="button"
              role="menuitemcheckbox"
              aria-checked={paused}
              aria-label="Pause everything"
              onClick={togglePause}
              className="rounded-md px-2 py-0.5 text-sm text-accent hover:bg-panel-2"
            >
              {paused ? "Disable" : "Enable"}
            </button>
          </div>
          <Link
            href="/settings#permissions"
            onClick={() => setOpen(false)}
            className="block px-3.5 pt-1 pb-1 text-xs text-muted hover:text-ink hover:underline"
          >
            Rules for each action: Settings →
          </Link>
        </div>
      )}
    </div>
  );
}
