"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";

type Review = { id: string; base: string; target: string; changes: string; dirty: boolean; supervised: boolean };
type Status = { supervised: boolean; review: Review | null; progress: { state: string; step: string } | null };

export default function UpdatesSettings() {
  const { data, error, mutate } = useSWR<Status>("/api/updates", fetcher, { refreshInterval: 3000 });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  async function action(path: string, body?: unknown) {
    setBusy(true); setNotice("");
    try {
      await send("POST", path, body);
      setNotice(path.endsWith("propose") ? "Review card is ready in Approvals. Nothing installs before approval." : "Update check finished.");
      await mutate();
    } catch (e) { setNotice(e instanceof Error ? e.message : "Could not complete this request."); }
    finally { setBusy(false); }
  }
  return <div className="space-y-4" role="group" aria-label="Junior updates">
    <p className="text-sm text-muted">Check the configured Git upstream, review the revision, then approve a tested update. Local edits block installation. The previous release and database are retained for rollback.</p>
    <p className="text-sm">{data?.supervised ? "Supervised launcher connected" : "Start through start.bat after stopping existing servers to enable supervised updates."}</p>
    {error && <p role="alert">Cannot load update status.</p>}
    {data?.progress && <p className="rounded-xl border border-line p-3 text-sm" role="status">{data.progress.state.replaceAll("_", " ")}: {data.progress.step}</p>}
    <button className="rounded-xl border border-line px-4 py-2 text-sm disabled:opacity-50" disabled={busy} onClick={() => action("/api/updates/check")}>{busy ? "Working…" : "Check for updates"}</button>
    {data?.review && <div className="space-y-3 rounded-xl border border-line p-4 text-sm">
      <p className="break-all">{data.review.base.slice(0, 12)} → {data.review.target.slice(0, 12)}</p>
      <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words">{data.review.changes || "No upstream changes."}</pre>
      {data.review.dirty && <p>Local edits exist. Commit or save them yourself before applying.</p>}
      <button className="rounded-xl border border-line px-4 py-2 disabled:opacity-50" disabled={busy || data.review.dirty || !data.supervised || data.review.base === data.review.target} onClick={() => action("/api/updates/propose", { review_id: data.review!.id })}>Prepare update review</button>
    </div>}
    {notice && <p role="status" className="text-sm">{notice}</p>}
  </div>;
}
