"use client";

import { useState } from "react";
import useSWR from "swr";
import { ApprovalCard } from "@/components/approvals/ApprovalCard";
import { fetcher } from "@/lib/api";
import { APPROVALS_KEY } from "@/lib/keys";
import type { ApprovalItem, ApprovalStatus } from "@/lib/types";

const TABS: { status: ApprovalStatus | "all"; label: string }[] = [
  { status: "waiting", label: "Waiting" },
  { status: "approved", label: "Approved" },
  { status: "posted", label: "Posted" },
  { status: "rejected", label: "Rejected" },
  { status: "all", label: "All" },
];

const EMPTY: Record<string, string> = {
  waiting: "Nothing waits for you. Ask Junior Muneer for a post, a comment or a proposal and it lands here.",
  approved: "Nothing approved yet.",
  posted: "Nothing posted yet.",
  rejected: "Nothing rejected.",
  all: "No drafts yet.",
};

export default function ApprovalsPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["status"]>("waiting");
  const { data, error } = useSWR<ApprovalItem[]>(`${APPROVALS_KEY}?status=${tab}`, fetcher, {
    refreshInterval: 30_000,
  });

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
        <header className="mb-5">
          <h1 className="text-2xl font-semibold tracking-tight">Approvals</h1>
          <p className="mt-1 text-sm text-muted">
            Every draft waits here for you. Copy-and-paste items you post yourself; nothing is sent without you.
          </p>
        </header>
        <nav role="tablist" aria-label="Approval status" className="mb-5 flex gap-1.5 overflow-x-auto">
          {TABS.map((t) => (
            <button
              key={t.status}
              type="button"
              role="tab"
              aria-selected={tab === t.status}
              onClick={() => setTab(t.status)}
              className={`shrink-0 rounded-full border px-3.5 py-1.5 text-sm ${
                tab === t.status ? "border-accent bg-accent-soft font-medium" : "border-line bg-panel text-muted hover:text-ink"
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
        {error && <p className="text-danger">Couldn&apos;t load approvals: {error.message}</p>}
        {data && data.length === 0 && <p className="rounded-2xl border border-dashed border-line p-8 text-center text-sm text-muted">{EMPTY[tab]}</p>}
        <div className="flex flex-col gap-4">
          {data?.map((item) => (
            <ApprovalCard key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
