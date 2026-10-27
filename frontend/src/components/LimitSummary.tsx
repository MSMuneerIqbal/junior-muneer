"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";

type Limits = {
  chat: { seconds: number };
  background: { model_calls: number; searches: number };
  computer: { desktop_snapshots: number; browser_snapshots: number; browser_session_seconds: number; jobs: number };
};

export default function LimitSummary() {
  const { data, error } = useSWR<Limits>("/api/usage/limits", fetcher);
  if (error) return <p className="px-6 py-4 text-sm" role="alert">Cannot load runtime limits.</p>;
  if (!data) return <p className="px-6 py-4 text-sm text-muted">Loading limits…</p>;
  return <div className="space-y-2 border-t border-line px-6 py-4 text-sm text-muted" role="group" aria-label="Runtime limits">
    <p>Chat replies stop after {data.chat.seconds / 60} minutes. Background tasks allow up to {data.background.model_calls} AI calls and {data.background.searches} search requests.</p>
    <p>Per message: up to {data.computer.desktop_snapshots} desktop captures and {data.computer.browser_snapshots} browser snapshots. Browser sessions expire after {data.computer.browser_session_seconds / 60} minutes; up to {data.computer.jobs} PC jobs can run together.</p>
    <p>Local commands and status polling use no model tokens. /clear starts fresh context and keeps today&apos;s spending record. Cost figures are estimates; usage already in flight and provider billing can differ.</p>
  </div>;
}
