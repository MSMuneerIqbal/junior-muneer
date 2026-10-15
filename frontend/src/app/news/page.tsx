"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";
import { urduClass } from "@/lib/urdu";

type Source = { name: string; title: string; url: string; date: string };
type Item = { headline: string; summary: string; date: string; sources: Source[] };
type Section = { key: string; title: string; items: Item[] };
type Board = { key: string; title: string; rows: { rank: number; model: string; creator: string; score: number }[] };
type Digest = {
  id: number;
  topic: "ai" | "pakistan";
  label: string;
  built_at: string;
  cost_usd: number;
  window_days: number;
  sections: Section[];
  removed: { headline: string; reason: string }[];
  failed: { source: string; reason: string }[];
  read: string[];
  articles: number;
  leaderboards: { source: string; url: string; fetched_at: string; boards: Board[]; problems: string[] } | null;
};

const TOPICS = [
  { key: "ai", label: "AI", ask: "What's new in AI?" },
  { key: "pakistan", label: "Pakistan", ask: "What's happening in Pakistan?" },
] as const;

const day = (iso: string) => new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short" });
const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const money = (n: number) => (n > 0 && n < 0.01 ? `$${n.toFixed(4)}` : `$${n.toFixed(2)}`);

function Rankings({ data }: { data: Digest["leaderboards"] }) {
  if (!data) {
    return (
      <section aria-label="Who's on top" className="rounded-2xl border border-dashed border-line p-4 text-sm text-muted">
        <p className="font-medium text-ink">Live rankings are off</p>
        <p className="mt-1">
          To see who&apos;s on top in coding, reasoning, voice, image and video, add a free Artificial Analysis key to{" "}
          <code>backend/.env</code> as <code>ARTIFICIAL_ANALYSIS_API_KEY</code> and restart. Until then, rankings come
          only from what the companies and Arena say in their own posts.
        </p>
      </section>
    );
  }
  return (
    <section aria-label="Who's on top" className="flex flex-col gap-3">
      <h2 className="text-base font-semibold">Who&apos;s on top right now</h2>
      <div className="grid gap-3 sm:grid-cols-2">
        {data.boards.map((b) => (
          <div key={b.key} className="rounded-2xl border border-line bg-panel p-4 shadow-sm">
            <p className="text-sm font-medium">{b.title}</p>
            <ol className="mt-2 flex flex-col gap-1 text-sm">
              {b.rows.map((r) => (
                <li key={r.rank + r.model} className="flex items-baseline gap-2">
                  <span className="w-6 shrink-0 text-muted tabular-nums">#{r.rank}</span>
                  <span className="min-w-0 flex-1 truncate">
                    {r.model} <span className="text-muted">· {r.creator}</span>
                  </span>
                  <span className="tabular-nums text-muted">{r.score}</span>
                </li>
              ))}
            </ol>
          </div>
        ))}
      </div>
      <p className="text-xs text-muted">
        Data:{" "}
        <a href={data.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-ink">
          Artificial Analysis
        </a>
        , {when(data.fetched_at)}.{data.problems.length > 0 && ` Not available today: ${data.problems.join("; ")}.`}
      </p>
    </section>
  );
}

function DigestView({ digest }: { digest: Digest }) {
  return (
    <div className="flex flex-col gap-8">
      {digest.failed.length > 0 && (
        <p role="note" className="rounded-xl bg-warn-soft px-4 py-2.5 text-sm text-warn">
          Couldn&apos;t read today: {digest.failed.map((f) => `${f.source} (${f.reason})`).join(", ")}. Nothing was filled
          in for them.
        </p>
      )}
      {digest.topic === "ai" && <Rankings data={digest.leaderboards} />}
      {digest.sections.map((section) => (
        <section key={section.key} aria-label={section.title} className="flex flex-col gap-3">
          <h2 className="flex items-baseline gap-2 text-base font-semibold">
            {section.title}
            <span className="text-sm font-normal text-muted">{section.items.length}</span>
          </h2>
          {section.items.length === 0 ? (
            <p className="text-sm text-muted">Nothing in this section today.</p>
          ) : (
            <ul className="flex flex-col gap-2">
              {section.items.map((item, n) => (
                <li key={n} className="rounded-2xl border border-line bg-panel px-4 py-3 shadow-sm">
                  <p dir="auto" className={`text-sm font-medium ${urduClass(item.headline)}`}>
                    {item.headline}
                  </p>
                  {item.summary && (
                    <p dir="auto" className={`mt-1 text-sm leading-relaxed text-ink/90 ${urduClass(item.summary)}`}>
                      {item.summary}
                    </p>
                  )}
                  <p className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-muted">
                    {item.sources.map((s) => (
                      <a
                        key={s.url}
                        href={s.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        title={s.title}
                        className="underline-offset-2 hover:text-ink hover:underline"
                      >
                        {s.name} · {day(s.date)} ↗
                      </a>
                    ))}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      ))}
      {digest.removed.length > 0 && (
        <details className="text-xs text-muted">
          <summary className="cursor-pointer hover:text-ink">
            The fact guard removed {digest.removed.length} item{digest.removed.length > 1 ? "s" : ""}
          </summary>
          <ul className="mt-2 list-disc pl-5">
            {digest.removed.map((r, n) => (
              <li key={n}>
                {r.headline}: {r.reason}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export default function NewsPage() {
  const [topic, setTopic] = useState<"ai" | "pakistan">("ai");
  const key = `/api/news/${topic}`;
  const { data, error, mutate } = useSWR<{ topic: string; digest: Digest | null }>(key, fetcher);
  const [building, setBuilding] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const digest = data?.digest ?? null;
  const current = TOPICS.find((t) => t.key === topic)!;

  async function refresh() {
    setBuilding(topic);
    setProblem(null);
    try {
      const result = await send<{ topic: string; digest: Digest }>("POST", `${key}/refresh`);
      await mutate(result, { revalidate: false });
    } catch (e) {
      setProblem(e instanceof Error ? e.message : "Couldn't build the digest");
    } finally {
      setBuilding(null);
    }
  }

  const busy = building === topic;
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
        <header className="mb-5">
          <h1 className="text-2xl font-semibold tracking-tight">News</h1>
          <p className="mt-1 text-sm text-muted">
            The last 15 days, from official sources only. Every item links to where it came from.
          </p>
        </header>

        <nav role="tablist" aria-label="News topic" className="mb-4 flex gap-1.5">
          {TOPICS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={topic === t.key}
              onClick={() => {
                setTopic(t.key);
                setProblem(null);
              }}
              className={`rounded-full border px-4 py-1.5 text-sm ${
                topic === t.key ? "border-accent bg-accent-soft font-medium" : "border-line bg-panel text-muted hover:text-ink"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div className="mb-6 flex flex-wrap items-center gap-x-3 gap-y-2 text-xs text-muted">
          {digest && (
            <span data-testid="digest-info">
              Updated {when(digest.built_at)} · {digest.articles} articles from {digest.read.length} sources ·{" "}
              {money(digest.cost_usd)}
            </span>
          )}
          <button
            type="button"
            onClick={refresh}
            disabled={busy}
            className="rounded-lg border border-line bg-panel px-3 py-1.5 text-sm font-medium text-ink hover:bg-panel-2 disabled:opacity-60"
          >
            {busy ? "Reading official sources… about a minute" : digest ? "↻ Refresh" : "Build it now"}
          </button>
          <Link
            href={`/?ask=${encodeURIComponent(current.ask)}`}
            className="rounded-lg px-2 py-1.5 text-sm text-accent hover:underline"
          >
            Ask about it
          </Link>
        </div>

        {problem && (
          <p role="alert" className="mb-4 rounded-xl bg-danger-soft px-4 py-2.5 text-sm text-danger">
            {problem}
          </p>
        )}
        {error && <p className="text-danger">Couldn&apos;t load the news: {error.message}</p>}
        {data && !digest && !busy && (
          <p className="rounded-2xl border border-dashed border-line p-8 text-center text-sm text-muted">
            No {current.label} digest yet. It&apos;s built every morning, or now with “Build it now”.
          </p>
        )}
        {digest && <DigestView digest={digest} />}
      </div>
    </div>
  );
}
