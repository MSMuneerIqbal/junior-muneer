"use client";

import { useRef, useState, type ReactNode } from "react";
import useSWR, { useSWRConfig } from "swr";
import { BACKEND_URL, fetcher, send } from "@/lib/api";
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

const ACCENTS: { value: Settings["voice_accent"]; label: string }[] = [
  { value: "pakistani", label: "Pakistani (Urdu)" },
  { value: "indian", label: "Indian (Hindi-Urdu)" },
  { value: "neutral", label: "Neutral / international" },
];

/** Plays a short Urdu + English sample of the chosen voice and accent. */
function VoicePreview({ voice, accent }: { voice: string; accent: string }) {
  const [state, setState] = useState<"idle" | "loading" | "playing" | "error">("idle");
  const audio = useRef<HTMLAudioElement | null>(null);

  function play() {
    audio.current?.pause();
    const el = new Audio(`${BACKEND_URL}/api/voice/preview/${voice}/${accent}.mp3`);
    audio.current = el;
    setState("loading");
    el.onplaying = () => setState("playing");
    el.onended = () => setState("idle");
    el.onerror = () => setState("error");
    el.play().catch(() => setState("error"));
  }

  return (
    <div className="flex items-center gap-3 text-sm">
      <button
        type="button"
        onClick={play}
        className="rounded-lg border border-line px-3 py-1.5 hover:bg-panel-2"
      >
        {state === "loading" ? "Loading…" : state === "playing" ? "Playing…" : "▶ Preview this voice"}
      </button>
      <span className="text-xs text-muted">
        {state === "error"
          ? "Couldn't play the preview."
          : "A short sample in Urdu and English (the first time takes a few seconds)."}
      </span>
    </div>
  );
}

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
  const { data: voices } = useSWR<string[]>("/api/voices", fetcher);
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
        tts_voice: form.tts_voice,
        voice_accent: form.voice_accent,
        tts_speed: Number(form.tts_speed),
        voice_autoplay: form.voice_autoplay,
        call_minutes_per_day: Number(form.call_minutes_per_day),
        call_quality: form.call_quality,
        turn_taking: form.turn_taking,
        mic_type: form.mic_type,
        main_model: form.main_model,
        helper_model: form.helper_model,
      });
      await mutate(SETTINGS_KEY, saved, { revalidate: false });
      await mutate(USAGE_KEY);
      await mutate("/api/models");
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
      <fieldset className="flex flex-col gap-4 border-t border-line pt-4">
        <legend className="pr-2 text-sm font-semibold">Voice</legend>
        <Field label="His voice" hint="Used for spoken answers and live calls.">
          <select
            value={form.tts_voice}
            onChange={(e) => setForm({ ...form, tts_voice: e.target.value })}
            className={input}
          >
            {(voices ?? [form.tts_voice]).map((v) => (
              <option key={v} value={v}>
                {v[0].toUpperCase() + v.slice(1)}
                {v === "marin" || v === "cedar" ? " · most natural" : ""}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Accent" hint="How he sounds in Urdu and in English.">
          <select
            value={form.voice_accent}
            onChange={(e) =>
              setForm({ ...form, voice_accent: e.target.value as Settings["voice_accent"] })
            }
            className={input}
          >
            {ACCENTS.map((a) => (
              <option key={a.value} value={a.value}>
                {a.label}
              </option>
            ))}
          </select>
        </Field>
        <VoicePreview voice={form.tts_voice} accent={form.voice_accent} />
        <Field label={`Speaking speed: ${Number(form.tts_speed).toFixed(2)}×`}>
          <input
            type="range"
            min={0.75}
            max={1.5}
            step={0.05}
            value={form.tts_speed}
            onChange={(e) => setForm({ ...form, tts_speed: Number(e.target.value) })}
            aria-label="Speaking speed"
          />
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={form.voice_autoplay}
            onChange={(e) => setForm({ ...form, voice_autoplay: e.target.checked })}
          />
          Read answers aloud automatically when I send a voice message
        </label>
        <Field
          label="Call quality"
          hint="Natural uses OpenAI's full voice model: the most human-sounding, about $0.04–0.06 a minute. Economy uses the mini model: about a third of the price, flatter."
        >
          <select
            value={form.call_quality}
            onChange={(e) =>
              setForm({ ...form, call_quality: e.target.value as Settings["call_quality"] })
            }
            className={input}
          >
            <option value="natural">Natural (recommended)</option>
            <option value="economy">Economy</option>
          </select>
        </Field>
        <Field
          label="Turn-taking"
          hint="How soon he answers when you pause. Patient lets you stop and think mid-sentence."
        >
          <select
            value={form.turn_taking}
            onChange={(e) =>
              setForm({ ...form, turn_taking: e.target.value as Settings["turn_taking"] })
            }
            className={input}
          >
            <option value="patient">Patient: waits while you think</option>
            <option value="balanced">Balanced (recommended)</option>
            <option value="quick">Quick: answers as soon as you pause</option>
          </select>
        </Field>
        <Field
          label="Microphone"
          hint="Cleans up background noise in calls to suit your microphone."
        >
          <select
            value={form.mic_type}
            onChange={(e) => setForm({ ...form, mic_type: e.target.value as Settings["mic_type"] })}
            className={input}
          >
            <option value="headset">Headset or earphones</option>
            <option value="laptop">Laptop or desk microphone</option>
            <option value="off">Off (no noise reduction)</option>
          </select>
        </Field>
        <Field
          label="Live-call minutes per day"
          hint="Live calls cost the most. The call ends when the limit is reached."
        >
          <input
            type="number"
            min={0}
            max={600}
            step={5}
            value={form.call_minutes_per_day}
            onChange={(e) =>
              setForm({ ...form, call_minutes_per_day: e.target.value as unknown as number })
            }
            className={`${input} w-40`}
            aria-label="Live-call minutes per day"
          />
        </Field>
      </fieldset>
      <ModelChoices form={form} setForm={setForm} />
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

type Choices = {
  choices: {
    model: string;
    label: string;
    provider: string;
    ready: boolean;
    key_env: string;
    price_per_million: { input: number; output: number };
  }[];
  defaults: { main_model: string; helper_model: string };
};

/** Which text models answer you (OpenAI or DeepSeek). Voice always uses OpenAI. */
function ModelChoices({
  form,
  setForm,
}: {
  form: Settings;
  setForm: (s: Settings) => void;
}) {
  const { data } = useSWR<Choices>("/api/models/choices", fetcher);
  if (!data) return null;
  const pick = (key: "main_model" | "helper_model", hint: string, label: string) => {
    const current = form[key] || data.defaults[key];
    const chosen = data.choices.find((c) => c.model === current);
    return (
      <Field label={label} hint={hint}>
        <select
          value={current}
          onChange={(e) =>
            setForm({ ...form, [key]: e.target.value === data.defaults[key] ? "" : e.target.value })
          }
          className={input}
        >
          {data.choices.map((c) => (
            <option key={c.model} value={c.model}>
              {c.label} · ${c.price_per_million.input} / ${c.price_per_million.output} per 1M
              {c.model === data.defaults[key] ? " (default)" : ""}
              {c.ready ? "" : " · needs key"}
            </option>
          ))}
        </select>
        {chosen && !chosen.ready && (
          <span className="text-xs text-warn">
            Add {chosen.key_env}=… to backend/.env and restart, or he can&apos;t answer with this
            model.
          </span>
        )}
        {chosen?.provider === "DeepSeek" && (
          <span className="text-xs text-muted">
            DeepSeek is very cheap. Your chats go to DeepSeek (servers in China) instead of
            OpenAI. Web search and voice still use OpenAI.
          </span>
        )}
      </Field>
    );
  };
  return (
    <fieldset className="flex flex-col gap-4 border-t border-line pt-4">
      <legend className="pr-2 text-sm font-semibold">Models</legend>
      {pick("main_model", "Writes his answers in chat. Prices are $ per 1M tokens in / out.", "Chat model")}
      {pick("helper_model", "Summarizes long chats in the background.", "Helper model")}
    </fieldset>
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
