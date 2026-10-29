"use client";

import { useState } from "react";
import useSWR, { useSWRConfig } from "swr";
import { fetcher, send } from "@/lib/api";
import { SETTINGS_KEY } from "@/lib/keys";

type Job = { id: string; title: string; schedule: string; enabled: boolean };
type Jobs = { scheduler_running: boolean; paused: boolean; jobs: Job[] };
const KEY = "/api/scheduled-jobs";

export default function ScheduledJobsSettings() {
  const { data, error, mutate } = useSWR<Jobs>(KEY, fetcher, { refreshInterval: 10000 });
  const { mutate: refresh } = useSWRConfig();
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState("");

  async function toggle(job: Job) {
    setBusy(job.id);
    setMessage("");
    try {
      const updated = await send<Jobs>("PATCH", `${KEY}/${job.id}`, { enabled: !job.enabled });
      await mutate(updated, false);
      await refresh(SETTINGS_KEY);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not update this job.");
    } finally { setBusy(null); }
  }

  if (error) return <p role="alert" className="py-4 text-sm text-red-500">Could not load scheduled jobs.</p>;
  if (!data) return <p className="py-4 text-sm text-muted">Loading scheduled jobs…</p>;
  return <div className="py-4">
    <p className="mb-3 text-sm text-muted">These switches control future automatic runs. Work already running may finish. Manual requests still work; existing permissions and limits still apply.</p>
    {!data.scheduler_running && <p className="mb-3 text-sm text-amber-600">The scheduler is disabled on this installation, so automatic jobs will not run.</p>}
    {data.paused && <p className="mb-3 text-sm text-amber-600">Junior is paused. Jobs that respect Pause will wait until resumed.</p>}
    {message && <p role="alert" className="mb-3 text-sm text-red-500">{message}</p>}
    <ul className="divide-y divide-line">
      {data.jobs.map((job) => <li key={job.id} className="flex items-center justify-between gap-4 py-3">
        <div><div className="text-sm font-medium">{job.title}</div><div className="text-xs text-muted">{job.schedule}</div></div>
        <button type="button" role="switch" aria-label={job.title} aria-checked={job.enabled} disabled={busy !== null}
          onClick={() => void toggle(job)} className="rounded-md border border-line px-3 py-1.5 text-sm disabled:opacity-50">
          {job.enabled ? "On" : "Off"}
        </button>
      </li>)}
    </ul>
    <p className="mt-3 text-xs text-muted">Change news and briefing times in Settings → News &amp; email. Backups and reminders may run while Junior is paused.</p>
  </div>;
}
