"use client";

import Link from "next/link";
import { useState } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";
import { urduClass } from "@/lib/urdu";

type EmailItem = {
  id: number;
  gmail_id: string;
  from_name: string;
  from_address: string;
  subject: string;
  snippet: string;
  received_at: string | null;
  category: string;
  important: boolean;
  summary: string;
  why: string;
  notified: boolean;
  link: string;
};
type Inbox = { ready: boolean; watching: boolean; checked_at: string; items: EmailItem[] };

const FILTERS = [
  { key: "important", label: "Important" },
  { key: "", label: "All" },
  { key: "client", label: "Clients" },
  { key: "freelance", label: "Freelance" },
  { key: "money", label: "Money" },
  { key: "security", label: "Security" },
] as const;

const when = (iso: string | null) =>
  iso ? new Date(iso).toLocaleString(undefined, { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "";

/** Your Gmail inbox as Junior sorted it (Phase 4). The emails stay in Gmail; replies are drafts you approve. */
export default function InboxPage() {
  const [filter, setFilter] = useState<string>("important");
  const query = filter === "important" ? "?important=true" : filter ? `?category=${filter}` : "";
  const { data, error, mutate } = useSWR<Inbox>(`/api/emails${query}`, fetcher);
  const [checking, setChecking] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  async function checkNow() {
    setChecking(true);
    setNote(null);
    try {
      const r = await send<{ new: number }>("POST", "/api/emails/check");
      setNote({ ok: true, text: r.new ? `${r.new} new email${r.new > 1 ? "s" : ""} sorted.` : "Nothing new." });
      await mutate();
    } catch (e) {
      setNote({ ok: false, text: e instanceof Error ? e.message : "Couldn't check" });
    } finally {
      setChecking(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
        <header className="mb-5">
          <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
          <p className="mt-1 text-sm text-muted">
            New Gmail, sorted by Junior every 5 minutes. Important ones also come to your WhatsApp. To answer, ask him to reply:
            it becomes a draft you approve.
          </p>
        </header>

        {data && !data.ready && (
          <p className="mb-4 rounded-xl bg-warn-soft px-4 py-2.5 text-sm text-warn">
            Gmail isn&apos;t connected yet. Go to{" "}
            <Link href="/settings#connections" className="font-medium underline">
              Settings → Connections
            </Link>
            , click Connect again, and tick the Gmail boxes.
          </p>
        )}

        <div className="mb-4 flex flex-wrap items-center gap-2">
          <nav role="tablist" aria-label="Which emails" className="flex flex-wrap gap-1.5">
            {FILTERS.map((f) => (
              <button
                key={f.key || "all"}
                type="button"
                role="tab"
                aria-selected={filter === f.key}
                onClick={() => setFilter(f.key)}
                className={`rounded-full border px-3.5 py-1 text-sm ${
                  filter === f.key ? "border-accent bg-accent-soft font-medium" : "border-line bg-panel text-muted hover:text-ink"
                }`}
              >
                {f.label}
              </button>
            ))}
          </nav>
          <button
            type="button"
            onClick={checkNow}
            disabled={checking || (data && !data.ready)}
            className="ml-auto rounded-lg border border-line bg-panel px-3 py-1.5 text-sm hover:bg-panel-2 disabled:opacity-50"
          >
            {checking ? "Checking…" : "↻ Check now"}
          </button>
        </div>
        {data?.checked_at && <p className="mb-3 text-xs text-muted">Last checked {when(data.checked_at)}.</p>}
        {note && (
          <p role={note.ok ? "status" : "alert"} className={`mb-3 text-sm ${note.ok ? "text-ok" : "text-danger"}`}>
            {note.text}
          </p>
        )}
        {error && <p className="text-danger">Couldn&apos;t load the inbox: {error.message}</p>}
        {data && data.items.length === 0 && (
          <p className="rounded-2xl border border-dashed border-line p-8 text-center text-sm text-muted">
            {filter === "important" ? "No important emails yet." : "No emails here yet."} New mail shows up after the next check.
          </p>
        )}

        <ul aria-label="Emails" className="flex flex-col gap-2">
          {data?.items.map((e) => (
            <li key={e.id} aria-label={e.subject} className="rounded-2xl border border-line bg-panel px-4 py-3 shadow-sm">
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs text-muted">
                <span className="font-semibold text-ink">email {e.id}</span>
                <span>{e.from_name || e.from_address}</span>
                <span>· {when(e.received_at)}</span>
                <span className="rounded-full bg-panel-2 px-2 py-0.5">{e.category}</span>
                {e.important && <span className="rounded-full bg-accent-soft px-2 py-0.5 font-medium text-accent">important</span>}
                {e.notified && <span>· sent to WhatsApp</span>}
              </div>
              <p dir="auto" className={`mt-1 text-sm font-medium ${urduClass(e.subject)}`}>
                {e.subject}
              </p>
              {e.summary && e.summary !== e.subject && (
                <p dir="auto" className={`mt-0.5 text-sm text-ink/90 ${urduClass(e.summary)}`}>
                  {e.summary}
                </p>
              )}
              <div className="mt-2 flex flex-wrap gap-3 text-sm">
                <Link href={`/?ask=${encodeURIComponent(`Junior read email ${e.id}`)}`} className="text-accent hover:underline">
                  Read it
                </Link>
                <Link href={`/?ask=${encodeURIComponent(`Junior reply to email ${e.id}: `)}`} className="text-accent hover:underline">
                  Reply
                </Link>
                <a href={e.link} target="_blank" rel="noopener noreferrer" className="text-muted hover:text-ink">
                  Open in Gmail ↗
                </a>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
