"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ApprovalCard } from "@/components/approvals/ApprovalCard";
import { fetcher, send } from "@/lib/api";
import type { ApprovalItem } from "@/lib/types";

type Idea = {
  id: number;
  platform: string;
  title: string;
  angle: string;
  kind: string;
  status: "new" | "used" | "dismissed";
  approval_id: number | null;
  created_at: string;
};

const PLATFORMS = [
  { key: "linkedin", label: "LinkedIn" },
  { key: "facebook", label: "Facebook" },
  { key: "instagram", label: "Instagram" },
  { key: "x", label: "X" },
];

const KIND_LABEL: Record<string, string> = {
  project: "Project story",
  lesson: "Lesson",
  how_to: "How-to",
  milestone: "Milestone",
  opinion: "Opinion",
  other: "Idea",
};

function Block({ title, count, empty, children }: { title: string; count?: number; empty: string; children: ReactNode }) {
  return (
    <section aria-label={title} className="flex flex-col gap-3">
      <h2 className="flex items-baseline gap-2 text-base font-semibold">
        {title}
        {count !== undefined && <span className="text-sm font-normal text-muted">{count}</span>}
      </h2>
      {count === 0 ? (
        <p className="rounded-2xl border border-dashed border-line p-5 text-center text-sm text-muted">{empty}</p>
      ) : (
        children
      )}
    </section>
  );
}

function IdeaRow({ idea }: { idea: Idea }) {
  const { mutate } = useSWRConfig();
  const [busy, setBusy] = useState(false);
  async function dismiss() {
    setBusy(true);
    try {
      await send("POST", `/api/ideas/${idea.id}/dismiss`);
      await mutate((key) => typeof key === "string" && key.startsWith("/api/ideas"));
    } finally {
      setBusy(false);
    }
  }
  return (
    <li className="flex flex-wrap items-start gap-3 rounded-2xl border border-line bg-panel px-4 py-3 shadow-sm">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          <span className="mr-1.5 text-muted">#{idea.id}</span>
          {idea.title}
        </p>
        {idea.angle && <p className="mt-0.5 text-xs text-muted">{idea.angle}</p>}
        <p className="mt-1 text-[11px] text-muted">{KIND_LABEL[idea.kind] ?? "Idea"}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <Link
          href={`/?ask=${encodeURIComponent(`Write idea ${idea.id}`)}`}
          className="rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg hover:opacity-90"
        >
          Write it
        </Link>
        <button
          type="button"
          onClick={dismiss}
          disabled={busy}
          className="rounded-lg border border-line px-3 py-1.5 text-sm text-muted hover:bg-panel-2 hover:text-ink"
        >
          Dismiss
        </button>
      </div>
    </li>
  );
}

export default function SocialPage() {
  const [platform, setPlatform] = useState("linkedin");
  const q = `platform=${platform}`;
  const { data: ideas } = useSWR<Idea[]>(`/api/ideas?status=new&${q}`, fetcher);
  const { data: waiting } = useSWR<ApprovalItem[]>(`/api/approvals?status=waiting&${q}`, fetcher, { refreshInterval: 30_000 });
  const { data: planned } = useSWR<ApprovalItem[]>(`/api/approvals?status=all&planned=true&${q}`, fetcher, {
    refreshInterval: 60_000,
  });
  const { data: posted } = useSWR<ApprovalItem[]>(`/api/approvals?status=posted&limit=20&${q}`, fetcher);
  const upcoming = planned?.filter((i) => i.status === "waiting" || i.status === "approved") ?? [];
  const unplannedWaiting = waiting?.filter((i) => !i.planned_at) ?? [];
  const label = PLATFORMS.find((p) => p.key === platform)!.label;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
        <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Social</h1>
            <p className="mt-1 text-sm text-muted">Ideas, drafts, planned and posted, per platform.</p>
          </div>
          <Link
            href={`/?ask=${encodeURIComponent(`Give me 5 ${label} post ideas for this week`)}`}
            className="rounded-xl border border-line bg-panel px-3.5 py-2 text-sm font-medium hover:bg-panel-2"
          >
            ✨ Get new ideas
          </Link>
        </header>

        <nav role="tablist" aria-label="Platform" className="mb-6 flex gap-1.5 overflow-x-auto">
          {PLATFORMS.map((p) => (
            <button
              key={p.key}
              type="button"
              role="tab"
              aria-selected={platform === p.key}
              onClick={() => setPlatform(p.key)}
              className={`shrink-0 rounded-full border px-3.5 py-1.5 text-sm ${
                platform === p.key ? "border-accent bg-accent-soft font-medium" : "border-line bg-panel text-muted hover:text-ink"
              }`}
            >
              {p.label}
            </button>
          ))}
        </nav>

        <div className="flex flex-col gap-8">
          <Block title="Planned" count={planned ? upcoming.length : undefined} empty={`Nothing planned for ${label}. Use 📅 Plan on a draft.`}>
            <div className="flex flex-col gap-4">
              {upcoming.map((i) => (
                <ApprovalCard key={i.id} item={i} />
              ))}
            </div>
          </Block>

          <Block title="Drafts waiting" count={waiting ? unplannedWaiting.length : undefined} empty={`No ${label} drafts waiting.`}>
            <div className="flex flex-col gap-4">
              {unplannedWaiting.map((i) => (
                <ApprovalCard key={i.id} item={i} />
              ))}
            </div>
          </Block>

          <Block title="Ideas" count={ideas?.length} empty={`No ${label} ideas yet. Ask for some with ✨ Get new ideas.`}>
            <ul className="flex flex-col gap-2">
              {ideas?.map((i) => (
                <IdeaRow key={i.id} idea={i} />
              ))}
            </ul>
          </Block>

          <Block title="Posted" count={posted?.length} empty={`Nothing marked as posted on ${label} yet.`}>
            <ul className="flex flex-col gap-2">
              {posted?.map((i) => (
                <li key={i.id} className="rounded-2xl border border-line bg-panel px-4 py-3 text-sm">
                  <p className="line-clamp-2 whitespace-pre-wrap">{i.text}</p>
                  <p className="mt-1 text-xs text-muted">
                    Posted {new Date(i.updated_at).toLocaleDateString()}
                    {i.meta.score !== undefined && ` · ${i.meta.score}/10`}
                  </p>
                </li>
              ))}
            </ul>
          </Block>
        </div>
      </div>
    </div>
  );
}
