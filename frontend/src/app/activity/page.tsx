"use client";

import Link from "next/link";
import { useState } from "react";
import useSWRInfinite from "swr/infinite";
import { fetcher } from "@/lib/api";
import type { Activity } from "@/lib/types";

const PAGE = 50;
const FILTERS = [
  { kind: "", label: "All" },
  { kind: "agent_run", label: "Agent runs" },
  { kind: "tool_call", label: "Tool calls" },
  { kind: "web_search", label: "Web searches" },
  { kind: "memory", label: "Memory" },
  { kind: "setting", label: "Settings" },
  { kind: "system", label: "System" },
];

const RESULT_STYLE: Record<string, string> = {
  ok: "bg-accent-soft text-accent",
  error: "bg-danger-soft text-danger",
  blocked: "bg-warn-soft text-warn",
  refused: "bg-warn-soft text-warn",
};

function summary(a: Activity): string {
  const d = a.detail as Record<string, unknown>;
  if (a.kind === "web_search") return String(d.query ?? "");
  if (a.kind === "memory") return String(d.content ?? d.after ?? "");
  if (a.kind === "tool_call") return String(d.arguments ?? "");
  if (a.kind === "agent_run") {
    if (d.error) return String(d.error);
    const steps = Array.isArray(d.steps) ? d.steps.join(" · ") : "";
    return [`${d.model_calls ?? 0} model call(s)`, steps].filter(Boolean).join(" · ");
  }
  if (a.kind === "system") return String(d.file ?? "");
  return "";
}

function Row({ a }: { a: Activity }) {
  const [open, setOpen] = useState(false);
  const time = new Date(a.created_at);
  return (
    <li className="border-b border-line last:border-0">
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        className="grid w-full grid-cols-[4.5rem_1fr_auto] items-baseline gap-x-3 px-3 py-2 text-left hover:bg-panel-2 sm:grid-cols-[4.5rem_9rem_1fr_auto]"
      >
        <span className="text-xs text-muted tabular-nums" title={time.toLocaleString()}>
          {time.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </span>
        <span className="truncate text-sm font-medium">
          {a.name === a.kind ? (
            a.kind.replace("_", " ")
          ) : (
            <>
              <span className="text-muted">{a.kind.replace("_", " ")} · </span>
              {a.name}
            </>
          )}
        </span>
        <span dir="auto" className="hidden truncate text-sm text-muted sm:block">
          {summary(a)}
        </span>
        <span className="flex items-center gap-2">
          {a.cost_usd > 0 && (
            <span className="text-xs text-muted tabular-nums">${a.cost_usd.toFixed(4)}</span>
          )}
          <span className={`rounded px-1.5 py-0.5 text-xs ${RESULT_STYLE[a.result] ?? "bg-panel-2"}`}>
            {a.result}
          </span>
        </span>
      </button>
      {open && (
        <div className="px-3 pb-3">
          <p className="mb-1 text-xs text-muted">
            {time.toLocaleString()}
            {a.conversation_id && (
              <>
                {" · "}
                <Link href={`/?c=${a.conversation_id}`} className="text-accent underline">
                  open chat
                </Link>
              </>
            )}
          </p>
          <pre className="overflow-x-auto rounded-md border border-line bg-panel-2 p-2 text-xs whitespace-pre-wrap">
            {JSON.stringify(a.detail, null, 2)}
          </pre>
        </div>
      )}
    </li>
  );
}

export default function ActivityPage() {
  const [kind, setKind] = useState("");
  const getKey = (index: number, previous: Activity[] | null) => {
    if (previous && previous.length < PAGE) return null;
    const before = previous?.length ? `&before_id=${previous[previous.length - 1].id}` : "";
    return `/api/activity?limit=${PAGE}&kind=${kind}${before}`;
  };
  const { data, error, size, setSize, isLoading, mutate } = useSWRInfinite<Activity[]>(
    getKey,
    fetcher,
  );
  const rows = data?.flat() ?? [];
  const hasMore = data ? data[data.length - 1]?.length === PAGE : false;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-4xl flex-col gap-4 px-4 py-6 sm:px-6">
        <header className="flex items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold">Activity</h1>
            <p className="mt-1 text-muted">Everything Junior Muneer did, newest first.</p>
          </div>
          <button
            onClick={() => mutate()}
            className="rounded-md border border-line px-3 py-1.5 text-sm hover:bg-panel-2"
          >
            Refresh
          </button>
        </header>

        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Filter by type">
          {FILTERS.map((f) => (
            <button
              key={f.kind}
              onClick={() => setKind(f.kind)}
              aria-pressed={kind === f.kind}
              className={`rounded-full px-3 py-1 text-sm ${
                kind === f.kind ? "bg-accent text-accent-fg" : "border border-line hover:bg-panel-2"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        {error && <p className="text-danger">Couldn&apos;t load activity: {error.message}</p>}
        {!isLoading && !rows.length && !error && (
          <p className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-muted">
            Nothing here yet.
          </p>
        )}
        {rows.length > 0 && (
          <ul className="rounded-lg border border-line bg-panel">
            {rows.map((a) => (
              <Row key={a.id} a={a} />
            ))}
          </ul>
        )}
        {hasMore && (
          <button
            onClick={() => setSize(size + 1)}
            className="self-center rounded-md border border-line px-4 py-1.5 text-sm hover:bg-panel-2"
          >
            Load older
          </button>
        )}
      </div>
    </div>
  );
}
