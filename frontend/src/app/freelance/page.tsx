"use client";

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";
import useSWR, { useSWRConfig } from "swr";
import { ApprovalCard } from "@/components/approvals/ApprovalCard";
import { fetcher, send } from "@/lib/api";
import { isFreelanceKey } from "@/lib/keys";
import { timeLeft } from "@/lib/orders";
import type { ApprovalItem, Order } from "@/lib/types";

type Job = {
  id: number;
  platform: string;
  title: string;
  url: string;
  budget: string;
  score: number;
  verdict: "apply" | "maybe" | "skip";
  reasons: string[];
  concerns: string[];
  scam_signs: string[];
  status: "new" | "proposal" | "sent" | "skipped";
  approval_id: number | null;
  created_at: string;
};

const PLATFORMS = [
  { key: "upwork", label: "Upwork" },
  { key: "fiverr", label: "Fiverr" },
];

const JOB_STATUS: Record<Job["status"], string> = {
  new: "Scored",
  proposal: "Proposal drafted",
  sent: "Proposal sent",
  skipped: "Skipped",
};

const ORDER_STATUS: Record<Order["status"], string> = {
  active: "In progress",
  revision: "Revision asked",
  delivered: "Delivered",
  completed: "Completed",
  cancelled: "Cancelled",
};

const VERDICT_TONE: Record<Job["verdict"], string> = {
  apply: "bg-accent-soft text-accent",
  maybe: "bg-warn-soft text-warn",
  skip: "bg-danger-soft text-danger",
};

const small = "rounded-lg border border-line px-3 py-1.5 text-sm hover:bg-panel-2";

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

/** The clock for "due in 5 h", started in the browser (the page is prerendered without one). */
function useNow() {
  const [now, setNow] = useState(0);
  useEffect(() => {
    const tick = () => setNow(Date.now());
    const first = setTimeout(tick, 0);
    const id = setInterval(tick, 60_000);
    return () => {
      clearTimeout(first);
      clearInterval(id);
    };
  }, []);
  return now;
}

function useAction() {
  const { mutate } = useSWRConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function run(path: string, body?: unknown) {
    setBusy(true);
    setError(null);
    try {
      await send("POST", path, body);
      await mutate(isFreelanceKey);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't work");
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run };
}

function JobRow({ job }: { job: Job }) {
  const { busy, error, run } = useAction();
  return (
    <li aria-label={`Job ${job.id}: ${job.title}`} className="rounded-2xl border border-line bg-panel px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-baseline gap-2">
        <span className={`rounded-full px-2 py-0.5 text-xs font-semibold tabular-nums ${VERDICT_TONE[job.verdict]}`}>
          {job.score}/10 · {job.verdict}
        </span>
        <p className="min-w-0 flex-1 text-sm font-medium">{job.title}</p>
        <span className="text-xs text-muted">{JOB_STATUS[job.status]}</span>
      </div>
      <p className="mt-1 text-xs text-muted">
        {[job.budget, new Date(job.created_at).toLocaleDateString()].filter(Boolean).join(" · ")}
      </p>
      {job.scam_signs.length > 0 && (
        <p className="mt-1.5 text-xs font-medium text-danger">⚠ Scam signs: {job.scam_signs.join(" ")}</p>
      )}
      {job.reasons.length > 0 && (
        <ul className="mt-1.5 list-disc pl-4 text-xs text-muted">
          {job.reasons.slice(0, 3).map((r, n) => (
            <li key={n}>{r}</li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {job.url && (
          <a href={job.url} target="_blank" rel="noopener noreferrer" className={small}>
            Open the job ↗
          </a>
        )}
        {job.status === "new" && job.verdict !== "skip" && (
          <Link href={`/?ask=${encodeURIComponent(`Write the proposal for job ${job.id}`)}`} className={small}>
            Write a proposal
          </Link>
        )}
        {job.status === "new" && (
          <button type="button" disabled={busy} onClick={() => run(`/api/jobs/${job.id}/skip`)} className={`${small} text-muted`}>
            Skip
          </button>
        )}
      </div>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </li>
  );
}

function OrderRow({ order, now }: { order: Order; now: number }) {
  const { busy, error, run } = useAction();
  const open = order.status === "active" || order.status === "revision";
  const left = order.due_at && now ? timeLeft(order.due_at, now) : null;
  const revisions =
    order.revisions_included === null
      ? `${order.revisions_used} revisions used`
      : `${order.revisions_used} of ${order.revisions_included} revisions used`;
  const mark = (status: Order["status"]) => run(`/api/orders/${order.id}/status`, { status });
  return (
    <li aria-label={`Order ${order.id}: ${order.title}`} className="rounded-2xl border border-line bg-panel px-4 py-3 shadow-sm">
      <div className="flex flex-wrap items-baseline gap-2">
        <p className="min-w-0 flex-1 text-sm font-medium">{order.title}</p>
        {open && left && <span className={`text-xs tabular-nums ${left.tone}`}>{left.text}</span>}
        <span className="text-xs text-muted">{ORDER_STATUS[order.status]}</span>
      </div>
      <p className="mt-1 text-xs text-muted">
        {[
          order.number && `#${order.number}`,
          order.buyer,
          order.price,
          order.due_at && `due ${new Date(order.due_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}`,
          revisions,
        ]
          .filter(Boolean)
          .join(" · ")}
      </p>
      {order.requirements.length > 0 && (
        <ul className="mt-1.5 list-disc pl-4 text-xs text-muted">
          {order.requirements.map((r, n) => (
            <li key={n}>{r}</li>
          ))}
        </ul>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {order.url && (
          <a href={order.url} target="_blank" rel="noopener noreferrer" className={small}>
            Open the order ↗
          </a>
        )}
        {open && (
          <>
            <Link
              href={`/?ask=${encodeURIComponent(`Write the delivery message for order ${order.id}. I'm delivering: `)}`}
              className={small}
            >
              Write delivery message
            </Link>
            <button type="button" disabled={busy} onClick={() => mark("delivered")} className={small}>
              Mark delivered
            </button>
          </>
        )}
        {order.status === "delivered" && (
          <button type="button" disabled={busy} onClick={() => mark("completed")} className={small}>
            Mark completed
          </button>
        )}
        {open && (
          <button type="button" disabled={busy} onClick={() => mark("cancelled")} className={`${small} text-muted`}>
            Cancelled
          </button>
        )}
      </div>
      {error && <p className="mt-1 text-xs text-danger">{error}</p>}
    </li>
  );
}

export default function FreelancePage() {
  const [platform, setPlatform] = useState("upwork");
  const now = useNow();
  const { data: waiting } = useSWR<ApprovalItem[]>(`/api/approvals?status=waiting&platform=${platform}`, fetcher, {
    refreshInterval: 30_000,
  });
  const { data: jobs } = useSWR<Job[]>("/api/jobs?status=all", fetcher);
  const { data: orders } = useSWR<Order[]>("/api/orders?status=all", fetcher, { refreshInterval: 60_000 });
  const label = PLATFORMS.find((p) => p.key === platform)!.label;
  const theirJobs = jobs?.filter((j) => j.platform === platform);
  const theirOrders = orders?.filter((o) => o.platform === platform);
  const openOrders = theirOrders
    ?.filter((o) => o.status === "active" || o.status === "revision")
    .sort((a, b) => (a.due_at ?? "9999").localeCompare(b.due_at ?? "9999"));
  const finished = theirOrders?.filter((o) => o.status !== "active" && o.status !== "revision").slice(0, 20);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
        <header className="mb-5 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Freelance</h1>
            <p className="mt-1 text-sm text-muted">Jobs you pasted, drafts to send, and orders to deliver.</p>
          </div>
          <Link href="/" className="rounded-xl border border-line bg-panel px-3.5 py-2 text-sm font-medium hover:bg-panel-2">
            📋 Paste a job, message or order
          </Link>
        </header>

        <nav role="tablist" aria-label="Platform" className="mb-6 flex gap-1.5">
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
          {(platform === "fiverr" || (openOrders?.length ?? 0) > 0) && (
            <Block title="Orders to deliver" count={openOrders?.length} empty="No open orders. Paste an order page in the chat to track it.">
              <ul className="flex flex-col gap-2">
                {openOrders?.map((o) => (
                  <OrderRow key={o.id} order={o} now={now} />
                ))}
              </ul>
            </Block>
          )}

          <Block title="Drafts waiting" count={waiting?.length} empty={`No ${label} drafts waiting.`}>
            <div className="flex flex-col gap-4">
              {waiting?.map((i) => (
                <ApprovalCard key={i.id} item={i} />
              ))}
            </div>
          </Block>

          {(platform === "upwork" || (theirJobs?.length ?? 0) > 0) && (
            <Block title="Jobs" count={theirJobs?.length} empty="No jobs yet. Paste a job post in the chat and ask “Should I apply?”.">
              <ul className="flex flex-col gap-2">
                {theirJobs?.map((j) => (
                  <JobRow key={j.id} job={j} />
                ))}
              </ul>
            </Block>
          )}

          {(finished?.length ?? 0) > 0 && (
            <Block title="Finished orders" count={finished?.length} empty="">
              <ul className="flex flex-col gap-2">
                {finished?.map((o) => (
                  <OrderRow key={o.id} order={o} now={now} />
                ))}
              </ul>
            </Block>
          )}
        </div>
      </div>
    </div>
  );
}
