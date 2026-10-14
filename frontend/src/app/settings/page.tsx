"use client";

import { useState, type ReactNode } from "react";
import useSWR, { useSWRConfig } from "swr";
import { fetcher, send } from "@/lib/api";
import { SETTINGS_KEY, USAGE_KEY } from "@/lib/keys";
import type { Settings } from "@/lib/types";

type ModelsView = {
  tiers: Record<string, string>;
  agents: {
    agent: string;
    description: string;
    tier: string;
    model: string;
    price_per_million: { input: number; cached_input: number; output: number };
  }[];
};

const LANGUAGES: { value: Settings["language"]; label: string }[] = [
  { value: "match", label: "Match me (reply in the language I use)" },
  { value: "english", label: "Always English" },
  { value: "urdu", label: "Always Urdu (اردو)" },
];

function timezones(current: string): string[] {
  try {
    const all = Intl.supportedValuesOf("timeZone");
    return all.includes(current) ? all : [current, ...all];
  } catch {
    return [current];
  }
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-sm font-medium">{label}</span>
      {children}
      {hint && <span className="text-xs text-muted">{hint}</span>}
    </label>
  );
}

const input =
  "rounded-lg border border-line bg-panel px-3 py-2 outline-none focus:border-accent";

function SettingsForm({ initial }: { initial: Settings }) {
  const { mutate } = useSWRConfig();
  const [form, setForm] = useState(initial);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const changed = (Object.keys(form) as (keyof Settings)[]).some((k) => form[k] !== initial[k]);

  async function save() {
    setSaving(true);
    setStatus(null);
    try {
      const saved = await send<Settings>("PATCH", SETTINGS_KEY, {
        user_name: form.user_name,
        language: form.language,
        timezone: form.timezone,
        daily_cap_usd: Number(form.daily_cap_usd),
      });
      await mutate(SETTINGS_KEY, saved, { revalidate: false });
      await mutate(USAGE_KEY);
      setForm(saved);
      setStatus({ ok: true, text: "Saved. It applies from your next message." });
    } catch (e) {
      setStatus({ ok: false, text: e instanceof Error ? e.message : "Couldn't save" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="flex flex-col gap-4 rounded-xl border border-line bg-panel p-5">
      <Field label="Your name" hint="Junior Muneer calls you by this name.">
        <input
          dir="auto"
          value={form.user_name}
          onChange={(e) => setForm({ ...form, user_name: e.target.value })}
          className={input}
          maxLength={50}
        />
      </Field>
      <Field label="Language" hint="Client work (posts, proposals, emails) stays in English.">
        <select
          value={form.language}
          onChange={(e) => setForm({ ...form, language: e.target.value as Settings["language"] })}
          className={input}
        >
          {LANGUAGES.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Time zone" hint="Used for 'today', spend and backups.">
        <select
          value={form.timezone}
          onChange={(e) => setForm({ ...form, timezone: e.target.value })}
          className={input}
        >
          {timezones(form.timezone).map((tz) => (
            <option key={tz}>{tz}</option>
          ))}
        </select>
      </Field>
      <Field
        label="Daily safety cap (US$)"
        hint="When today's AI spend reaches this, new AI work stops until midnight."
      >
        <input
          type="number"
          min={0}
          max={1000}
          step={0.5}
          value={form.daily_cap_usd}
          onChange={(e) => setForm({ ...form, daily_cap_usd: e.target.value as unknown as number })}
          className={`${input} w-40`}
          aria-label="Daily safety cap in US dollars"
        />
      </Field>
      <div className="flex items-center gap-3">
        <button
          onClick={save}
          disabled={!changed || saving}
          className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-fg disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        {status && (
          <span role="status" className={`text-sm ${status.ok ? "text-ok" : "text-danger"}`}>
            {status.text}
          </span>
        )}
      </div>
    </section>
  );
}

function ModelsTable() {
  const { data, error } = useSWR<ModelsView>("/api/models", fetcher);
  if (error) return <p className="text-danger">Couldn&apos;t load models: {error.message}</p>;
  if (!data) return null;
  return (
    <section className="flex flex-col gap-3 rounded-xl border border-line bg-panel p-5">
      <div>
        <h2 className="font-semibold">Models per agent</h2>
        <p className="text-sm text-muted">
          View only. To change a model, edit <code className="text-xs">agents/models.toml</code>;
          it applies on the next message.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-muted">
            <tr>
              <th className="py-1 pr-3 font-medium">Agent</th>
              <th className="py-1 pr-3 font-medium">Tier</th>
              <th className="py-1 pr-3 font-medium">Model</th>
              <th className="py-1 font-medium">$ per 1M tokens (in / out)</th>
            </tr>
          </thead>
          <tbody>
            {data.agents.map((a) => (
              <tr key={a.agent} className="border-t border-line" title={a.description}>
                <td className="py-1.5 pr-3">{a.agent}</td>
                <td className="py-1.5 pr-3">{a.tier}</td>
                <td className="py-1.5 pr-3 font-mono text-xs">{a.model}</td>
                <td className="py-1.5 tabular-nums">
                  {a.price_per_million.input} / {a.price_per_million.output}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default function SettingsPage() {
  const { data, error } = useSWR<Settings>(SETTINGS_KEY, fetcher);
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-2xl flex-col gap-5 px-4 py-6 sm:px-6">
        <header>
          <h1 className="text-2xl font-semibold">Settings</h1>
          <p className="mt-1 text-muted">Basic settings. More arrive with each phase.</p>
        </header>
        {error && <p className="text-danger">Couldn&apos;t load settings: {error.message}</p>}
        {data && <SettingsForm initial={data} />}
        <ModelsTable />
      </div>
    </div>
  );
}
