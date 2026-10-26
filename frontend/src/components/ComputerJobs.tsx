"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";

type Job = {
  id: string;
  command: string;
  folder: string;
  seconds: number;
  state: string;
  output: string;
  output_chars: number;
  output_truncated: boolean;
  note: string;
  exit_code: number | null;
  created_at: string;
  finished_at: string | null;
};

type Jobs = { jobs: Job[]; limits: { max_running: number; default_seconds: number; max_seconds: number } };
const active = (job: Job) => ["starting", "running"].includes(job.state);
const stateLabel = (state: string) => state.replaceAll("_", " ");

export default function ComputerJobs() {
  const { data, error: loadError, mutate } = useSWR<Jobs>("/api/computer/jobs", fetcher, { refreshInterval: 3000 });
  const [selected, setSelected] = useState<string | null>(null);
  const [stopping, setStopping] = useState<string | null>(null);
  const [error, setError] = useState("");
  const detail = useSWR<Job>(selected ? `/api/computer/jobs/${selected}` : null, fetcher, {
    refreshInterval: (job) => job && active(job) ? 1500 : 0,
  });

  async function stop(id: string) {
    setStopping(id);
    setError("");
    try {
      const job = await send<Job>("POST", `/api/computer/jobs/${id}/stop`, {});
      if (selected === id) await detail.mutate(job, { revalidate: false });
      await mutate();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't stop that job.");
    } finally {
      setStopping(null);
    }
  }

  return (
    <section aria-label="PC jobs" className="flex min-w-0 flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">PC jobs</h3>
        <button type="button" onClick={() => void mutate()} className="rounded-md border border-line px-2 py-1 text-xs">
          Refresh jobs
        </button>
      </div>
      <p className="text-xs text-muted">
        Ask Junior to run a background command, then approve its card. Up to {data?.limits.max_running ?? 3} jobs,
        with a default 10-minute limit. Checking output here uses no AI tokens.
      </p>
      <p className="text-xs text-muted">
        Jobs stop on their time limit, Pause, Computer off, Plan mode or backend shutdown. Stop keeps any partial changes.
      </p>
      {(error || loadError) && <p role="alert" className="text-xs text-danger">{error || "Couldn't load PC jobs. Try Refresh jobs."}</p>}
      {!data && !loadError && <p role="status" className="text-sm text-muted">Loading PC jobs…</p>}
      {data?.jobs.length === 0 && <p className="text-sm text-muted">No PC jobs yet.</p>}
      {data?.jobs.map((job) => (
        <article key={job.id} data-testid="pc-job-row" aria-label={`PC job ${job.id}`}
          className="min-w-0 rounded-xl border border-line p-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span data-testid="pc-job-state" className={`text-xs font-semibold capitalize ${active(job) ? "text-accent" : "text-muted"}`}>
              {stateLabel(job.state)}
            </span>
            <span className="text-xs text-muted">Limit: {job.seconds}s · {new Date(job.created_at).toLocaleString()}</span>
          </div>
          <pre className="mt-2 max-h-28 overflow-auto whitespace-pre-wrap break-all font-mono text-xs">{job.command}</pre>
          <p className="mt-1 break-all text-xs text-muted">{job.folder}</p>
          {job.note && <p className="mt-2 text-xs">{job.note}</p>}
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" aria-label={`View output for ${job.id}`} aria-expanded={selected === job.id}
              onClick={() => setSelected(selected === job.id ? null : job.id)}
              className="rounded-md border border-line px-3 py-1.5 text-xs hover:bg-panel-2">
              {selected === job.id ? "Hide output" : "View output"}
            </button>
            {active(job) && (
              <button type="button" aria-label={`Stop job ${job.id}`} disabled={stopping !== null}
                onClick={() => void stop(job.id)}
                className="rounded-md border border-danger/40 px-3 py-1.5 text-xs text-danger disabled:opacity-50">
                {stopping === job.id ? "Stopping…" : "Stop"}
              </button>
            )}
          </div>
          {selected === job.id && (
            <div className="mt-3" aria-label="Job output">
              {detail.error && <p role="alert" className="text-xs text-danger">Couldn&apos;t load output.</p>}
              {!detail.data && !detail.error && <p role="status" className="text-xs text-muted">Loading output…</p>}
              {detail.data && <>
                {detail.data.output_truncated && <p className="mb-1 text-xs text-muted">Showing the last 16,000 characters.</p>}
                <pre data-testid="pc-job-output" className="max-h-72 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-panel-2 p-3 font-mono text-xs">
                  {detail.data.output || "No output yet."}
                </pre>
              </>}
            </div>
          )}
        </article>
      ))}
      {data && data.jobs.length >= 50 && <p className="text-xs text-muted">Showing up to 50 jobs, active jobs first.</p>}
    </section>
  );
}
