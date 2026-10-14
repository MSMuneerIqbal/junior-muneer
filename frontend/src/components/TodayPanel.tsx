"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";
import { PAUSE_KEY, USAGE_KEY } from "@/lib/keys";
import type { UsageToday } from "@/lib/types";

function money(n: number) {
  return n < 0.01 && n > 0 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`;
}

function Spend() {
  const { data, error } = useSWR<UsageToday>(USAGE_KEY, fetcher, { refreshInterval: 60_000 });
  if (error) return <p className="text-sm text-danger">Spend unavailable: {error.message}</p>;
  if (!data) return <p className="text-sm text-muted">Loading spend…</p>;
  const used = data.cap_usd > 0 ? Math.min(data.spent_usd / data.cap_usd, 1) : 1;
  const bar = data.cap_reached ? "bg-danger" : used > 0.8 ? "bg-warn" : "bg-accent";
  return (
    <section aria-label="Spend today">
      <div className="flex items-baseline justify-between">
        <span className="text-sm text-muted">Spend today</span>
        <span className="font-semibold tabular-nums" data-testid="spend-today">
          {money(data.spent_usd)}
        </span>
      </div>
      <div
        className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-panel-2"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={data.cap_usd}
        aria-valuenow={data.spent_usd}
        aria-label="Spend against daily cap"
      >
        <div className={`h-full ${bar}`} style={{ width: `${used * 100}%` }} />
      </div>
      <p className="mt-1 text-xs text-muted">
        {data.cap_reached ? (
          <span className="text-danger">Daily cap reached. Raise it in Settings.</span>
        ) : (
          <>
            {money(data.left_usd)} left of the {money(data.cap_usd)} daily cap
          </>
        )}
      </p>
      {Object.keys(data.by_mode).length > 0 && (
        <ul className="mt-2 flex flex-col gap-0.5 text-xs text-muted">
          {Object.entries(data.by_mode).map(([mode, cost]) => (
            <li key={mode} className="flex justify-between">
              <span className="capitalize">{mode}</span>
              <span className="tabular-nums">{money(cost)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function PauseButton() {
  const { data, mutate } = useSWR<{ paused: boolean }>(PAUSE_KEY, fetcher);
  const [error, setError] = useState<string | null>(null);
  const paused = data?.paused ?? false;

  async function toggle() {
    setError(null);
    try {
      await mutate(send<{ paused: boolean }>("POST", PAUSE_KEY, { paused: !paused }), {
        optimisticData: { paused: !paused },
        rollbackOnError: true,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div>
      <button
        onClick={toggle}
        disabled={!data}
        aria-pressed={paused}
        className={`w-full rounded-lg px-3 py-2 text-sm font-medium ${
          paused
            ? "bg-warn-soft text-warn ring-1 ring-warn"
            : "border border-line hover:bg-panel-2"
        }`}
      >
        {paused ? "▶ Resume everything" : "⏸ Pause everything"}
      </button>
      <p className="mt-1 text-xs text-muted">
        {paused
          ? "Paused: no background work or actions. Chat still works."
          : "Stops background work and actions. Chat keeps working."}
      </p>
      {error && <p className="text-xs text-danger">{error}</p>}
    </div>
  );
}

/** Today's spend, Pause, and what needs your OK. */
export function TodayPanel() {
  return (
    <div className="flex flex-col gap-5 p-4">
      <h2 className="font-semibold">Today</h2>
      <PauseButton />
      <Spend />
      <section aria-label="Needs your OK">
        <div className="flex items-baseline justify-between">
          <span className="text-sm text-muted">Needs your OK</span>
          <span className="font-semibold">0</span>
        </div>
        <p className="mt-1 text-xs text-muted">Approvals arrive in phase 2.</p>
      </section>
      <section aria-label="Mode">
        <label className="flex items-center justify-between text-sm text-muted">
          Mode
          <select disabled className="rounded-md border border-line bg-panel px-2 py-1 text-ink disabled:opacity-50">
            <option>Ask</option>
          </select>
        </label>
        <p className="mt-1 text-xs text-muted">Ask / Auto / Deny rules arrive in phase 2.</p>
      </section>
    </div>
  );
}
