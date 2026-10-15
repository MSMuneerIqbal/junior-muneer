"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";
import { PERMISSIONS_KEY } from "@/lib/keys";

type Mode = "rules" | "ask_all";

const MODES: Record<Mode, { label: string; hint: string }> = {
  rules: { label: "Use my rules", hint: "Each action follows its Ask / Auto / Deny rule" },
  ask_all: { label: "Ask everything", hint: "Every action waits for your OK" },
};

/** The permission mode, as a small dropdown under the message box. */
export function ModeSelect() {
  const { data, mutate } = useSWR<{ mode: Mode; paused: boolean }>(PERMISSIONS_KEY, fetcher);
  const [error, setError] = useState<string | null>(null);
  const mode = data?.mode ?? "rules";

  async function change(next: Mode) {
    setError(null);
    try {
      await mutate(send("PUT", "/api/permissions/mode", { mode: next }), {
        optimisticData: data && { ...data, mode: next },
        rollbackOnError: true,
        revalidate: false,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't change the mode");
    }
  }

  return (
    <div className="flex min-w-0 items-center gap-2 text-xs text-muted">
      <label
        title={MODES[mode].hint}
        className={`relative flex items-center gap-1 rounded-full border px-2.5 py-1 transition hover:text-ink ${
          mode === "ask_all" ? "border-warn/40 bg-warn-soft text-warn" : "border-line bg-panel"
        }`}
      >
        <span aria-hidden>{mode === "ask_all" ? "✋" : "🛡"}</span>
        <select
          aria-label="Permission mode"
          value={mode}
          disabled={!data}
          onChange={(e) => change(e.target.value as Mode)}
          className="cursor-pointer appearance-none bg-transparent pr-3.5 font-medium outline-none disabled:opacity-50"
        >
          {(Object.keys(MODES) as Mode[]).map((m) => (
            <option key={m} value={m}>
              {MODES[m].label}
            </option>
          ))}
        </select>
        <span aria-hidden className="pointer-events-none absolute right-2.5">
          ▾
        </span>
      </label>
      {data?.paused ? (
        <span className="truncate text-warn">Paused: nothing runs until you resume</span>
      ) : (
        <Link href="/settings#permissions" className="truncate hover:text-ink hover:underline">
          Edit rules
        </Link>
      )}
      {error && <span className="truncate text-danger">{error}</span>}
    </div>
  );
}
