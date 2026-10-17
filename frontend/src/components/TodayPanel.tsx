"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { fetcher, send } from "@/lib/api";
import { useWaitingCount } from "@/lib/approvals";
import { isChatsKey, ORDERS_DUE_KEY, PAUSE_KEY, PERMISSIONS_KEY, USAGE_KEY } from "@/lib/keys";
import { timeLeft } from "@/lib/orders";
import type { ApprovalItem, BackgroundTask, Order, UsageToday } from "@/lib/types";

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
  const { mutate: mutateGlobal } = useSWRConfig();
  const [error, setError] = useState<string | null>(null);
  const paused = data?.paused ?? false;

  async function toggle() {
    setError(null);
    try {
      await mutate(send<{ paused: boolean }>("POST", PAUSE_KEY, { paused: !paused }), {
        optimisticData: { paused: !paused },
        rollbackOnError: true,
      });
      void mutateGlobal(PERMISSIONS_KEY); // the Permissions menu shows Pause too
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

function CallMinutes() {
  const { data } = useSWR<{ minutes_used: number; minutes_allowed: number }>(
    "/api/call/limits",
    fetcher,
    { refreshInterval: 60_000 },
  );
  if (!data) return null;
  return (
    <div className="flex items-baseline justify-between text-sm">
      <span className="text-muted">📞 Live calls today</span>
      <span className="tabular-nums" data-testid="call-minutes">
        {data.minutes_used.toFixed(1)} of {data.minutes_allowed} min
      </span>
    </div>
  );
}

function TimeToPost() {
  const { data } = useSWR<ApprovalItem[]>("/api/approvals/due", fetcher, { refreshInterval: 60_000 });
  if (!data?.length) return null;
  return (
    <section aria-label="Time to post" className="rounded-lg bg-danger-soft px-3 py-2">
      <p className="text-sm font-medium text-danger">⏰ Time to post</p>
      <ul className="mt-1 flex flex-col gap-0.5 text-xs">
        {data.map((i) => (
          <li key={i.id}>
            <Link href="/approvals" className="hover:underline">
              {i.platform_label}: {i.title}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function OrdersDue() {
  const { data } = useSWR<Order[]>(ORDERS_DUE_KEY, fetcher, { refreshInterval: 60_000 });
  const [now, setNow] = useState(0); // set in the browser: the page is prerendered without a clock
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 60_000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, []);
  if (!data?.length || !now) return null;
  return (
    <section aria-label="Orders due" className="rounded-lg border border-line px-3 py-2">
      <p className="text-sm font-medium">📦 Orders due</p>
      <ul className="mt-1 flex flex-col gap-1 text-xs">
        {data.map((o) => {
          const left = timeLeft(o.due_at ?? "", now);
          return (
            <li key={o.id} className="flex items-baseline justify-between gap-2">
              {o.url ? (
                <a href={o.url} target="_blank" rel="noopener noreferrer" className="truncate hover:underline">
                  {o.title}
                </a>
              ) : (
                <span className="truncate">{o.title}</span>
              )}
              <span className={`shrink-0 tabular-nums ${left.tone}`}>{left.text}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Briefing() {
  const { data, mutate } = useSWR<{ conversation_id: number | null }>("/api/briefing/today", fetcher, {
    refreshInterval: 300_000,
  });
  const { mutate: mutateGlobal } = useSWRConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  if (!data) return null;
  if (data.conversation_id) {
    return (
      <Link
        href={`/?c=${data.conversation_id}`}
        className="flex items-center gap-2 rounded-lg bg-accent-soft px-3 py-2 text-sm font-medium hover:opacity-90"
      >
        <span aria-hidden>☀</span> Today&apos;s briefing
      </Link>
    );
  }
  async function make() {
    setBusy(true);
    setError(null);
    try {
      await mutate(send<{ conversation_id: number }>("POST", "/api/briefing/now"));
      void mutateGlobal(isChatsKey); // it's a chat in your list
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't make it");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button type="button" onClick={make} disabled={busy} className="w-full rounded-lg border border-line px-3 py-2 text-left text-sm hover:bg-panel-2">
        ☀ {busy ? "Writing your briefing…" : "Today's briefing"}
      </button>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </div>
  );
}

function BackgroundWork() {
  const { data } = useSWR<BackgroundTask[]>("/api/tasks?limit=4", fetcher, {
    refreshInterval: (d) => (d?.some((t) => t.status === "running") ? 3000 : 30_000),
  });
  if (!data?.length) return null;
  const mark = { running: "⏳", done: "✅", failed: "⚠" } as const;
  return (
    <section aria-label="Background work" className="rounded-lg border border-line px-3 py-2">
      <p className="text-sm font-medium">Background work</p>
      <ul className="mt-1 flex flex-col gap-1 text-xs">
        {data.map((t) => (
          <li key={t.id} className="flex items-baseline gap-1.5">
            <span aria-hidden>{mark[t.status]}</span>
            {t.conversation_id ? (
              <Link href={`/?c=${t.conversation_id}`} className="truncate hover:underline">
                {t.title}
              </Link>
            ) : (
              <span className="truncate">{t.title}</span>
            )}
            <span className="ml-auto shrink-0 text-muted">{t.status === "running" ? "working" : t.status}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function NeedsYourOk() {
  const waiting = useWaitingCount();
  return (
    <section aria-label="Needs your OK">
      <Link href="/approvals" className="flex items-baseline justify-between rounded-md hover:text-accent">
        <span className="text-sm text-muted">Needs your OK</span>
        <span className="font-semibold tabular-nums" data-testid="needs-ok">
          {waiting ?? "…"}
        </span>
      </Link>
      <p className="mt-1 text-xs text-muted">
        {waiting ? "Drafts are waiting on the Approvals page." : "Nothing waits for you."}
      </p>
    </section>
  );
}

/** Today's spend, Pause, and what needs your OK. */
export function TodayPanel() {
  return (
    <div className="flex flex-col gap-5 p-4">
      <h2 className="font-semibold">Today</h2>
      <Briefing />
      <PauseButton />
      <Spend />
      <CallMinutes />
      <TimeToPost />
      <OrdersDue />
      <BackgroundWork />
      <NeedsYourOk />
    </div>
  );
}
