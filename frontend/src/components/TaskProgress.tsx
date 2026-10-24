"use client";

import { useState } from "react";
import { useSWRConfig } from "swr";
import { send } from "@/lib/api";
import { isTasksKey } from "@/lib/keys";
import type { BackgroundTask } from "@/lib/types";

export function TaskProgress({ task }: { task: BackgroundTask }) {
  const { mutate } = useSWRConfig();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const percent = Math.round(100 * task.completed_steps / Math.max(1, task.total_steps));
  async function cancel() {
    setBusy(true);
    setError("");
    try {
      await send("POST", `/api/tasks/${task.id}/cancel`);
      await mutate(isTasksKey);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't stop the task");
    } finally {
      setBusy(false);
    }
  }
  return (
    <div role="status" className="min-w-0 rounded-lg border border-line p-3 text-sm" aria-label={`Task ${task.id} progress`}>
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 break-words font-medium">Working on it in the background: {task.title}</p>
        {task.status === "running" && <button type="button" onClick={cancel} disabled={busy} className="shrink-0 text-xs text-muted hover:text-danger">{busy ? "Stopping…" : "Stop"}</button>}
      </div>
      <p className="mt-2 text-xs text-muted">{task.stage} · {task.completed_steps}/{task.total_steps} steps</p>
      <div role="progressbar" aria-label="Task steps completed" aria-valuemin={0} aria-valuemax={task.total_steps} aria-valuenow={task.completed_steps} className="mt-2 h-1.5 overflow-hidden rounded-full bg-panel-2">
        <div className="h-full bg-accent transition-all" style={{ width: `${percent}%` }} />
      </div>
      <p className="mt-2 text-xs text-muted">
        {task.elapsed_seconds}s elapsed · {task.eta_seconds == null ? "Estimating time from completed tasks" : task.eta_seconds > 0 ? `About ${task.eta_seconds}s left` : "Taking longer than similar tasks"}
      </p>
      <p className="mt-1 text-xs text-muted">${task.cost_usd.toFixed(4)} of ${task.cost_limit_usd.toFixed(2)} allowance · {task.retries_used}/{task.max_retries} retries</p>
      {error && <p className="mt-2 text-xs text-danger">{error}</p>}
    </div>
  );
}
