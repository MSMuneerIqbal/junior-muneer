"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";

type Proposal = { id: string; summary: string; status: string; diff: string; test_result: string; estimated_cost_usd?: number; preparation_seconds?: number };

export default function CodeSettings() {
  const { data, error, mutate } = useSWR<Proposal[]>("/api/code-proposals", fetcher, { refreshInterval: 3000 });
  const [busy, setBusy] = useState("");
  const [notice, setNotice] = useState("");
  async function review(id: string, operation: string) {
    setBusy(id); setNotice("");
    try {
      await send("POST", `/api/code-proposals/${id}/review`, { operation });
      setNotice(`${operation} review card is ready in Approvals. Nothing runs before approval.`);
      await mutate();
    } catch (e) { setNotice(e instanceof Error ? e.message : "Could not prepare review."); }
    finally { setBusy(""); }
  }
  return <div className="space-y-4 border-t border-line p-6" role="group" aria-label="Code proposals">
    <h3 className="font-medium">Code proposals</h3>
    <p className="text-sm text-muted">Ask Junior to propose a small change to his local source. Review the diff, approve tests, then approve application separately. Native tests have your account&apos;s authority. Permission and credential internals require manual developer review.</p>
    {error && <p role="alert">Cannot load code proposals.</p>}
    {data?.length === 0 && <p className="text-sm text-muted">No code proposals yet.</p>}
    {data?.map(p => <article key={p.id} className="space-y-3 rounded-xl border border-line p-4 text-sm">
      <h4 className="font-medium">{p.summary}</h4>
      <p className="break-all text-xs text-muted">{p.id}</p>
      <p role="status">{p.status.replaceAll("_", " ")}: {p.test_result}</p>
      {typeof p.estimated_cost_usd === "number" && <p className="text-xs text-muted">AI draft estimate: ${p.estimated_cost_usd.toFixed(6)} · {p.preparation_seconds}s preparation</p>}
      <details><summary className="cursor-pointer">Review full diff</summary><pre className="mt-3 max-h-96 overflow-auto whitespace-pre-wrap break-words text-xs">{p.diff}</pre></details>
      <div className="flex flex-wrap gap-2">
        {[["test", ["staged", "test_failed", "interrupted"]], ["apply", ["passed"]], ["rollback", ["applied"]]].map(([op, states]) => (states as string[]).includes(p.status) && <button key={op as string} disabled={!!busy} className="rounded-lg border border-line px-3 py-2 disabled:opacity-50" onClick={() => review(p.id, op as string)}>Prepare {op as string} review</button>)}
      </div>
    </article>)}
    {notice && <p role="status" className="text-sm">{notice}</p>}
  </div>;
}
