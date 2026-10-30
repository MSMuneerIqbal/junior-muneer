"use client";

import Link from "next/link";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import useSWR, { useSWRConfig } from "swr";
import { GitHubConnect } from "@/components/GitHubConnect";
import { SettingsIcon } from "@/components/icons";
import SkillsSettings from "@/components/SkillsSettings";
import UpdatesSettings from "@/components/UpdatesSettings";
import CodeSettings from "@/components/CodeSettings";
import LimitSummary from "@/components/LimitSummary";
import ComputerJobs from "@/components/ComputerJobs";
import DesktopSettings from "@/components/DesktopSettings";
import BrowserSettings from "@/components/BrowserSettings";
import ScheduledJobsSettings from "@/components/ScheduledJobsSettings";
import { BACKEND_URL, fetcher, send } from "@/lib/api";
import { PERMISSIONS_KEY, SETTINGS_KEY, USAGE_KEY } from "@/lib/keys";
import type { Settings } from "@/lib/types";

// ---- data shapes ---------------------------------------------------------------

type ModelChoice = {
  model: string;
  label: string;
  note: string;
  speed: "fast" | "medium" | "slow";
  provider: string;
  ready: boolean;
  key_env: string;
  price_per_million: { input: number; output: number };
};
type Choices = { choices: ModelChoice[]; defaults: { main_model: string; helper_model: string } };
type ModelsView = {
  agents: {
    agent: string;
    description: string;
    model: string;
    price_per_million: { input: number; output: number };
  }[];
};

type Rule = "ask" | "auto" | "deny";
type Permissions = {
  mode: "ask_all" | "rules" | "plan";
  paused: boolean;
  types: { type: string; label: string; group: string; rule: Rule; default: Rule; locked: boolean; note: string }[];
};

// The left menu: one section shows at a time. "#news" in the address opens that section.
type SectionId =
  | "profile" | "budget" | "models" | "search" | "voice" | "calls" | "connections" | "whatsapp" | "posting" | "news"
  | "computer" | "skills" | "tasks" | "scheduled" | "permissions" | "advanced";
type MenuItem = { id: SectionId; title: string }; // its icon: SettingsIcon by id
const GROUPS: { title: string; items: MenuItem[] }[] = [
  { title: "Account", items: [{ id: "profile", title: "Profile" }, { id: "budget", title: "Budget" }] },
  {
    title: "AI",
    items: [
      { id: "models", title: "Models" },
      { id: "search", title: "Search & photos" },
      { id: "voice", title: "Voice" },
      { id: "calls", title: "Live calls" },
    ],
  },
  {
    title: "Channels",
    items: [
      { id: "connections", title: "Connections" },
      { id: "whatsapp", title: "WhatsApp" },
      { id: "posting", title: "Posting" },
    ],
  },
  { title: "Automation", items: [{ id: "skills", title: "Skills" }, { id: "tasks", title: "Background tasks" }, { id: "scheduled", title: "Scheduled jobs" }, { id: "news", title: "News & email" }, { id: "computer", title: "Computer" }] },
  {
    title: "Safety",
    items: [
      { id: "permissions", title: "Permissions" },
      { id: "advanced", title: "Advanced" },
    ],
  },
];
const SECTIONS: MenuItem[] = GROUPS.flatMap((g) => g.items);
const isSection = (id: string): id is SectionId => SECTIONS.some((s) => s.id === id);

const ActiveSection = createContext<SectionId>("profile");

// ---- building blocks ---------------------------------------------------------------

function Section({
  id,
  title,
  description,
  children,
}: {
  id: string;
  title: string;
  description: string;
  children: ReactNode;
}) {
  // Every section stays mounted (its state and checks keep working); only the chosen one shows.
  const active = useContext(ActiveSection) === id;
  return (
    // Flat, like Claude's own settings: a title, then rows split by thin lines.
    <section id={id} hidden={!active} aria-labelledby={`${id}-title`} className="@container">
      <header className="pb-2">
        <h2 id={`${id}-title`} className="text-[17px] font-semibold">
          {title}
        </h2>
        <p className="mt-1 text-[14px] leading-relaxed text-muted">{description}</p>
      </header>
      <div className="divide-y divide-line">{children}</div>
    </section>
  );
}

/** One setting: label and explanation on the left, the control on the right.
 *  `wide` controls (model cards, voices, lists) go under the label, full width. */
function Row({ label, hint, wide, children }: { label: string; hint?: ReactNode; wide?: boolean; children: ReactNode }) {
  const text = (
    <div className="min-w-0">
      <p className="text-[15px] font-medium">{label}</p>
      {hint && <p className="mt-1 text-[14px] leading-relaxed text-muted">{hint}</p>}
    </div>
  );
  if (wide) {
    return (
      <div className="flex flex-col gap-4 py-5">
        {text}
        <div className="min-w-0">{children}</div>
      </div>
    );
  }
  return (
    <div className="flex flex-col gap-3 py-5 @2xl:flex-row @2xl:items-center @2xl:justify-between @2xl:gap-10">
      <div className="@2xl:max-w-[60%]">{text}</div>
      <div className="min-w-0 @2xl:flex @2xl:shrink-0 @2xl:justify-end">{children}</div>
    </div>
  );
}

/** A few options side by side, like iOS / macOS segmented controls. */
function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string; sub?: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="grid gap-2 @md:auto-cols-fr @md:grid-flow-col">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(o.value)}
            className={`rounded-xl border px-3 py-2.5 text-left transition ${
              on
                ? "border-accent bg-accent-soft ring-1 ring-accent"
                : "border-line hover:border-muted hover:bg-panel-2"
            }`}
          >
            <span className="block text-sm font-medium">{o.label}</span>
            {o.sub && <span className="mt-0.5 block text-xs text-muted">{o.sub}</span>}
          </button>
        );
      })}
    </div>
  );
}

function Toggle({
  checked,
  onChange,
  label,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={`relative h-6 w-11 shrink-0 rounded-full transition ${checked ? "bg-accent" : "bg-line"}`}
    >
      <span
        className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${
          checked ? "left-[22px]" : "left-0.5"
        }`}
      />
    </button>
  );
}

type NewsEmail = { configured: boolean; address: string; enabled: boolean; last_sent: string; rule: Rule };

/** Whether Gmail is set up for the daily top 5, and a button to send it now. */
function NewsEmailStatus() {
  const { data, mutate } = useSWR<NewsEmail>("/api/news-email", fetcher);
  const [busy, setBusy] = useState(false);
  const [said, setSaid] = useState<{ ok: boolean; text: string } | null>(null);
  if (!data) return null;
  if (!data.configured) {
    return (
      <p className="text-xs text-muted">
        Gmail isn&apos;t set up yet: add <code>GMAIL_ADDRESS</code> and <code>GMAIL_APP_PASSWORD</code> (a Google App
        Password, not your normal password) to <code>backend/.env</code>, then restart.
      </p>
    );
  }
  async function sendNow() {
    setBusy(true);
    setSaid(null);
    try {
      const r = await send<{ message: string }>("POST", "/api/news-email/send");
      setSaid({ ok: true, text: r.message });
      await mutate();
    } catch (e) {
      setSaid({ ok: false, text: e instanceof Error ? e.message : "Couldn't send it" });
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="flex flex-col gap-1.5 text-xs text-muted">
      <p>
        To <span className="text-ink">{data.address}</span>
        {data.last_sent ? ` · last sent ${data.last_sent}` : " · not sent yet"}
        {data.rule !== "auto" && ` · your rule is ${data.rule === "ask" ? "Ask" : "Deny"}, so it won't send by itself`}
      </p>
      <div>
        <button
          type="button"
          onClick={sendNow}
          disabled={busy}
          className="rounded-lg border border-line px-3 py-1.5 text-sm text-ink hover:bg-panel-2 disabled:opacity-50"
        >
          {busy ? "Sending…" : "Send it now"}
        </button>
      </div>
      {said && (
        <p role={said.ok ? "status" : "alert"} className={said.ok ? "text-ok" : "text-danger"}>
          {said.text}
        </p>
      )}
    </div>
  );
}

function Badge({ tone, children }: { tone: "accent" | "warn" | "muted" | "ok"; children: ReactNode }) {
  const style = {
    accent: "bg-accent-soft text-accent",
    warn: "bg-warn-soft text-warn",
    muted: "bg-panel-2 text-muted",
    ok: "bg-accent-soft text-ok",
  }[tone];
  return <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${style}`}>{children}</span>;
}

const input =
  "w-full rounded-xl border border-line bg-bg px-3.5 py-2.5 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20";

function timezones(current: string): string[] {
  try {
    const all = Intl.supportedValuesOf("timeZone");
    return all.includes(current) ? all : [current, ...all];
  } catch {
    return [current];
  }
}

// ---- models -------------------------------------------------------------------------

const SPEED: Record<ModelChoice["speed"], { label: string; tone: "ok" | "muted" | "warn" }> = {
  fast: { label: "Fast", tone: "ok" },
  medium: { label: "Normal speed", tone: "muted" },
  slow: { label: "Slow", tone: "warn" },
};

function ModelPicker({
  value,
  defaultModel,
  choices,
  onChange,
  label,
}: {
  value: string;
  defaultModel: string;
  choices: ModelChoice[];
  onChange: (model: string) => void;
  label: string;
}) {
  const current = value || defaultModel;
  return (
    <div role="radiogroup" aria-label={label} className="grid gap-2 @md:grid-cols-2 @4xl:grid-cols-3">
      {choices.map((c) => {
        const on = c.model === current;
        return (
          <button
            key={c.model}
            type="button"
            role="radio"
            aria-checked={on}
            onClick={() => onChange(c.model === defaultModel ? "" : c.model)}
            className={`flex flex-col gap-1.5 rounded-xl border p-3 text-left transition ${
              on ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-line hover:bg-panel-2"
            }`}
          >
            <span className="flex flex-wrap items-center gap-1.5">
              <span className="text-sm font-semibold">{c.label}</span>
              <span className="text-xs text-muted">{c.provider}</span>
            </span>
            <span className="flex flex-wrap gap-1.5">
              <Badge tone={SPEED[c.speed].tone}>{SPEED[c.speed].label}</Badge>
              <Badge tone="muted">
                ${c.price_per_million.input} / ${c.price_per_million.output} per 1M
              </Badge>
              {c.model === defaultModel && <Badge tone="accent">Default</Badge>}
              {!c.ready && <Badge tone="warn">Needs key</Badge>}
            </span>
            {c.note && <span className="text-xs leading-relaxed text-muted">{c.note}</span>}
            {on && !c.ready && (
              <span className="text-xs text-warn">
                Add {c.key_env}=… to backend/.env and restart to use this model.
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

// ---- voice --------------------------------------------------------------------------

const ACCENTS: { value: Settings["voice_accent"]; label: string; sub: string }[] = [
  { value: "pakistani", label: "Pakistani", sub: "Lahore / Karachi" },
  { value: "indian", label: "Indian", sub: "Delhi Hindi-Urdu" },
  { value: "neutral", label: "Neutral", sub: "International" },
];

function usePreview() {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const [loading, setLoading] = useState<string | null>(null);
  useEffect(() => () => audio.current?.pause(), []);
  function play(voice: string, url: string) {
    audio.current?.pause();
    if (playing === voice || loading === voice) {
      setPlaying(null);
      setLoading(null);
      return;
    }
    const el = new Audio(url);
    audio.current = el;
    setLoading(voice);
    setPlaying(null);
    el.onplaying = () => {
      setLoading(null);
      setPlaying(voice);
    };
    el.onended = el.onerror = () => {
      setLoading(null);
      setPlaying(null);
    };
    el.play().catch(() => setLoading(null));
  }
  return { play, playing, loading };
}

function VoicePicker({
  voices,
  value,
  accent,
  onChange,
}: {
  voices: string[];
  value: string;
  accent: string;
  onChange: (v: string) => void;
}) {
  const preview = usePreview();
  return (
    <div role="radiogroup" aria-label="His voice" className="grid grid-cols-2 gap-2 @lg:grid-cols-3 @4xl:grid-cols-5">
      {voices.map((v) => {
        const on = v === value;
        const natural = v === "marin" || v === "cedar";
        const busy = preview.loading === v;
        const playing = preview.playing === v;
        return (
          <div
            key={v}
            className={`flex items-center gap-2 rounded-xl border p-2 pl-3 transition ${
              on ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-line hover:bg-panel-2"
            }`}
          >
            <button
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(v)}
              className="min-w-0 flex-1 text-left"
            >
              <span className="block text-sm font-medium">{v[0].toUpperCase() + v.slice(1)}</span>
              <span className="block text-[11px] text-muted">{natural ? "Most natural" : " "}</span>
            </button>
            <button
              type="button"
              onClick={() => preview.play(v, `${BACKEND_URL}/api/voice/preview/${v}/${accent}.mp3`)}
              aria-label={`${playing ? "Stop" : "Play"} a sample of ${v}`}
              title="Hear a short Urdu + English sample"
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs ${
                playing ? "border-accent bg-accent text-accent-fg" : "border-line hover:bg-panel"
              }`}
            >
              {busy ? "…" : playing ? "■" : "▶"}
            </button>
          </div>
        );
      })}
    </div>
  );
}

// Google's own short descriptions of its Live voices.
const GEMINI_VOICES: { value: Settings["gemini_voice"]; sub: string }[] = [
  { value: "Charon", sub: "Male · calm, deep" },
  { value: "Puck", sub: "Male · upbeat" },
  { value: "Orus", sub: "Male · firm" },
  { value: "Fenrir", sub: "Male · lively" },
  { value: "Kore", sub: "Female · firm" },
  { value: "Aoede", sub: "Female · breezy" },
  { value: "Leda", sub: "Female · youthful" },
  { value: "Zephyr", sub: "Female · bright" },
];

function GeminiVoicePicker({
  value,
  onChange,
}: {
  value: Settings["gemini_voice"];
  onChange: (v: Settings["gemini_voice"]) => void;
}) {
  const preview = usePreview();
  return (
    <div role="radiogroup" aria-label="Gemini voice" className="grid grid-cols-2 gap-2 @lg:grid-cols-3 @4xl:grid-cols-4">
      {GEMINI_VOICES.map(({ value: v, sub }) => {
        const on = v === value;
        const busy = preview.loading === v;
        const playing = preview.playing === v;
        return (
          <div
            key={v}
            className={`flex items-center gap-2 rounded-xl border p-2 pl-3 transition ${
              on ? "border-accent bg-accent-soft ring-1 ring-accent" : "border-line hover:bg-panel-2"
            }`}
          >
            <button
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange(v)}
              className="min-w-0 flex-1 text-left"
            >
              <span className="block text-sm font-medium">{v}</span>
              <span className="block text-[11px] text-muted">{sub}</span>
            </button>
            <button
              type="button"
              onClick={() => preview.play(v, `${BACKEND_URL}/api/voice/gemini-preview/${v}.wav`)}
              aria-label={`${playing ? "Stop" : "Play"} a sample of ${v}`}
              title="Hear a short Urdu + English sample (the first time takes a few seconds)"
              className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full border text-xs ${
                playing ? "border-accent bg-accent text-accent-fg" : "border-line hover:bg-panel"
              }`}
            >
              {busy ? "…" : playing ? "■" : "▶"}
            </button>
          </div>
        );
      })}
    </div>
  );
}

type VoiceModel = { model: string; label: string; note: string; per_minute: number };
type VoiceModels = Record<
  "openai" | "gemini",
  { hear: VoiceModel[]; speak: VoiceModel[]; defaults: { hear: string; speak: string } }
>;

function VoiceModelSelect({
  label,
  options,
  defaultModel,
  value,
  onChange,
}: {
  label: string;
  options: VoiceModel[];
  defaultModel: string;
  value: string;
  onChange: (v: string) => void;
}) {
  const known = options.some((o) => o.model === value);
  const shown = options.find((o) => o.model === (known ? value : defaultModel));
  return (
    <div className="max-w-md">
      <select
        value={known ? value : ""}
        onChange={(e) => onChange(e.target.value)}
        className={input}
        aria-label={label}
      >
        {options.map((o) => (
          <option key={o.model} value={o.model === defaultModel ? "" : o.model}>
            {o.label}
            {o.model === defaultModel ? " (default)" : ""} · ${o.per_minute.toFixed(4)}/min
          </option>
        ))}
      </select>
      {shown && <p className="mt-1.5 text-[13px] text-muted">{shown.note}</p>}
    </div>
  );
}

// ---- the form ------------------------------------------------------------------------

function SettingsForm({ initial }: { initial: Settings }) {
  const { mutate } = useSWRConfig();
  const { data: voices } = useSWR<string[]>("/api/voices", fetcher);
  const { data: models } = useSWR<Choices>("/api/models/choices", fetcher);
  const { data: limits } = useSWR<{ gemini_ready: boolean }>("/api/call/limits", fetcher);
  const { data: voiceModels } = useSWR<VoiceModels>("/api/voice/models", fetcher);
  const [form, setForm] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const savedRef = useRef(initial);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const failedSave = useRef("");
  const changed = (Object.keys(form) as (keyof Settings)[]).some(
    (k) => String(form[k]) !== String(saved[k]),
  );
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) => {
    setStatus(null);
    setForm((f) => ({ ...f, [key]: value }));
  };

  useEffect(() => {
    const previous = savedRef.current;
    savedRef.current = initial;
    // Synchronize settings changed through another control with the external SWR cache.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSaved(initial);
    setForm((current) => Object.fromEntries((Object.keys(initial) as (keyof Settings)[]).map((key) =>
      [key, String(current[key]) === String(previous[key]) ? initial[key] : current[key]])) as Settings);
  }, [initial]);

  useEffect(() => {
    if (!status?.ok) return;
    const t = setTimeout(() => setStatus(null), 3000);
    return () => clearTimeout(t);
  }, [status]);

  const save = useCallback(async () => {
    if (saving) return;
    const snapshot = form;
    const changes = Object.fromEntries((Object.keys(snapshot) as (keyof Settings)[])
      .filter((key) => key !== "paused" && String(snapshot[key]) !== String(saved[key]))
      .map((key) => [key, snapshot[key]]));
    if (!Object.keys(changes).length) return;
    setSaving(true);
    setStatus(null);
    try {
      const result = await send<Settings>("PATCH", SETTINGS_KEY, changes);
      await mutate(SETTINGS_KEY, result, { revalidate: false });
      await Promise.allSettled([mutate(USAGE_KEY), mutate("/api/models")]);
      // Keep edits made while this request was in flight; refresh untouched fields from the server.
      setForm((current) => Object.fromEntries((Object.keys(result) as (keyof Settings)[]).map((key) =>
        [key, String(current[key]) === String(snapshot[key]) ? result[key] : current[key]])) as Settings);
      setSaved(result);
      failedSave.current = "";
      setStatus({ ok: true, text: "Saved. Applies from your next message or call." });
    } catch (e) {
      failedSave.current = JSON.stringify(changes);
      setStatus({ ok: false, text: e instanceof Error ? e.message : "Couldn't save" });
    } finally {
      setSaving(false);
    }
  }, [form, saved, saving, mutate]);

  useEffect(() => {
    if (!changed || saving) return;
    const changes = Object.fromEntries((Object.keys(form) as (keyof Settings)[])
      .filter((key) => key !== "paused" && String(form[key]) !== String(saved[key]))
      .map((key) => [key, form[key]]));
    if (!Object.keys(changes).length || JSON.stringify(changes) === failedSave.current) return;
    const timer = setTimeout(() => void save(), 800);
    return () => clearTimeout(timer);
  }, [changed, saving, form, saved, save]);

  return (
    <div className="flex flex-col gap-6 pb-28">
      <Section id="profile" title="Profile" description="Who you are and how he talks to you.">
        <Row label="Your name" hint="Junior Muneer calls you by this name.">
          <input
            dir="auto"
            value={form.user_name}
            onChange={(e) => set("user_name", e.target.value)}
            className={`${input} max-w-sm`}
            maxLength={50}
            aria-label="Your name"
          />
        </Row>
        <Row
          label="Language"
          hint="For chat and calls. Client work (posts, proposals, emails) stays in English."
        >
          <Segmented
            label="Language"
            value={form.language}
            onChange={(v) => set("language", v)}
            options={[
              { value: "match", label: "Match me", sub: "Same as you write" },
              { value: "english", label: "English", sub: "Always" },
              { value: "urdu", label: "Urdu اردو", sub: "Always" },
            ]}
          />
        </Row>
        <Row label="Time zone" hint="Used for “today”, your spend and backups.">
          <select
            value={form.timezone}
            onChange={(e) => set("timezone", e.target.value)}
            className={`${input} max-w-sm`}
            aria-label="Time zone"
          >
            {timezones(form.timezone).map((tz) => (
              <option key={tz}>{tz}</option>
            ))}
          </select>
        </Row>
      </Section>

      <Section id="scheduled" title="Scheduled jobs" description="See Junior's automatic work and choose which jobs run.">
        <ScheduledJobsSettings />
      </Section>
      <Section id="tasks" title="Background tasks" description="Limits for new research, presentations and other background jobs. Running jobs keep the limits they started with.">
        <Row label="Cost allowance per task" hint="Stops further AI work when reached. Responses are bounded to fit the remaining allowance; provider billing can differ slightly.">
          <input type="number" min={0.01} max={10} step={0.05} value={form.task_budget_usd} onChange={(e) => set("task_budget_usd", e.target.value as unknown as number)} className={`${input} max-w-40`} aria-label="Task cost allowance in US dollars" />
        </Row>
        <Row label="Time limit" hint="Seconds before the task stops. Default: 600 (10 minutes).">
          <input type="number" min={30} max={1800} step={30} value={form.task_timeout_seconds} onChange={(e) => set("task_timeout_seconds", e.target.value as unknown as number)} className={`${input} max-w-40`} aria-label="Task time limit in seconds" />
        </Row>
        <Row label="Retry limit" hint="Shared by busy-service retries and content revisions. External actions are never retried by the task.">
          <select value={form.task_max_retries} onChange={(e) => set("task_max_retries", Number(e.target.value))} className={`${input} max-w-40`} aria-label="Task retry limit">
            {[0, 1, 2].map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </Row>
      </Section>

      <Section id="budget" title="Budget" description="A safety net against surprises.">
        <LimitSummary />
        <Row label="Cost allowance per chat reply (USD)" hint="A typed reply and its helpers share this allowance. Input, schema and output are bounded before requests; estimates and in-flight provider billing can differ.">
          <input type="number" min={0.01} max={10} step={0.01} value={form.chat_budget_usd} onChange={e => set("chat_budget_usd", e.target.value as unknown as number)} className={`${input} max-w-40`} aria-label="Chat cost allowance in US dollars" />
        </Row>
        <Row label="AI calls per chat reply" hint="Includes helper agents and provider fallback. Background tasks keep their existing 12-call cap; live calls have their own limits.">
          <input type="number" min={1} max={24} value={form.chat_max_model_calls} onChange={e => set("chat_max_model_calls", Number(e.target.value))} className={`${input} max-w-40`} aria-label="AI calls per chat reply" />
        </Row>
        <Row label="Output tokens per AI response" hint="Maximum generated tokens, including hidden reasoning and tool-call text. Very low limits can prevent long documents from completing.">
          <input type="number" min={512} max={16000} step={1} value={form.max_output_tokens} onChange={e => set("max_output_tokens", Number(e.target.value))} className={`${input} max-w-40`} aria-label="Output tokens per AI response" />
        </Row>
        <Row
          label="Daily safety cap"
          hint="When today's AI spend reaches this, new AI work stops until midnight. Live calls end too."
        >
          <div className="flex max-w-[12rem] items-center rounded-xl border border-line bg-bg focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
            <span className="pl-3.5 text-sm text-muted">$</span>
            <input
              type="number"
              min={0}
              max={1000}
              step={0.5}
              value={form.daily_cap_usd}
              onChange={(e) => set("daily_cap_usd", e.target.value as unknown as number)}
              className="w-full bg-transparent px-2 py-2.5 text-sm outline-none"
              aria-label="Daily safety cap in US dollars"
            />
            <span className="pr-3.5 text-xs whitespace-nowrap text-muted">per day</span>
          </div>
        </Row>
      </Section>

      <Section
        id="models"
        title="Models"
        description="Choose which AI writes chat and voice-message answers. If it is unavailable, Junior reports the error without switching models."
      >
        {models ? (
          <>
            <Row
              wide
              label="Chat model"
              hint="For chat and voice-message answers and live-call tasks. Prices are US$ per 1 million tokens, in / out."
            >
              <ModelPicker
                label="Chat model"
                value={form.main_model}
                defaultModel={models.defaults.main_model}
                choices={models.choices}
                onChange={(m) => set("main_model", m)}
              />
            </Row>
            <Row wide label="Helper model" hint="Used for chat summaries, the Computer Agent and the Browser Agent. When unset, those two agents use your selected chat model.">
              <ModelPicker
                label="Helper model"
                value={form.helper_model}
                defaultModel={models.defaults.helper_model}
                choices={models.choices.filter((c) => c.speed !== "slow")}
                onChange={(m) => set("helper_model", m)}
              />
            </Row>
          </>
        ) : (
          <p className="px-6 py-5 text-sm text-muted">Loading models…</p>
        )}
      </Section>

      <Section id="search" title="Search & photos" description="Which engine searches the web for fresh facts, and which AI reads the photos you send.">
        <Row
          label="Search engine"
          hint={
            <>
              DeepSeek is much cheaper and answers from the results directly; Gemini searches Google and can read
              links; OpenAI uses a small helper. If the selected provider fails, Junior reports the error without switching providers. The news workflow uses separate models.
              {form.web_search_provider === "gemini" && limits && !limits.gemini_ready && (
                <span className="mt-1 block text-warn">
                  Gemini search needs <code>GEMINI_API_KEY</code> in backend/.env.
                </span>
              )}
              {form.web_search_provider === "deepseek" && models && !models.choices.some((c) => c.provider === "DeepSeek" && c.ready) && (
                <span className="mt-1 block text-warn">
                  DeepSeek search needs <code>DEEPSEEK_API_KEY</code> in backend/.env.
                </span>
              )}
            </>
          }
        >
          <Segmented
            label="Web search"
            value={form.web_search_provider}
            onChange={(v) => set("web_search_provider", v)}
            options={[
              { value: "openai", label: "OpenAI", sub: "~$0.01 a search + a helper" },
              { value: "deepseek", label: "DeepSeek", sub: "~$0.0008 a search" },
              { value: "gemini", label: "Gemini", sub: "Google Search · free tier" },
            ]}
          />
        </Row>
        <Row
          label="Reading photos"
          hint="Photos you send on WhatsApp or with 📎, and images in your Drive: the text in them and what they show. If DeepSeek fails, OpenAI reads it."
        >
          <Segmented
            label="Reading photos"
            value={form.vision_provider}
            onChange={(v) => set("vision_provider", v)}
            options={[
              { value: "openai", label: "OpenAI", sub: "Small vision model" },
              { value: "deepseek", label: "DeepSeek V4.1 Flash", sub: "~$0.0005 a photo" },
            ]}
          />
        </Row>
      </Section>

      <Section id="voice" title="Voice" description="How he hears your voice messages and how he sounds when he answers.">
        <Row
          wide
          label="Voice messages engine"
          hint={
            <>
              Who hears your recorded voice messages (dashboard mic and WhatsApp voice notes) and reads his answers
              aloud. Live calls have their own engine under Live calls. Gemini may try another Gemini hearing model if the selected model is busy or over quota; it does not switch to OpenAI.
              {form.voice_engine === "gemini" && limits && !limits.gemini_ready && (
                <span className="mt-1 block text-warn">
                  Gemini needs <code>GEMINI_API_KEY</code> in backend/.env (from aistudio.google.com/apikey), then a restart.
                </span>
              )}
            </>
          }
        >
          <Segmented
            label="Voice messages engine"
            value={form.voice_engine}
            onChange={(v) => {
              set("voice_engine", v);
              set("voice_hear_model", ""); // each engine has its own models: start from its defaults
              set("voice_speak_model", "");
            }}
            options={[
              { value: "openai", label: "OpenAI", sub: "Best Urdu hearing · ~$0.02/min" },
              { value: "gemini", label: "Gemini", sub: "Cheaper, free tier · Gemini voices" },
            ]}
          />
        </Row>
        {voiceModels && (
          <>
            <Row label="Hearing model" hint="Turns your voice messages into text.">
              <VoiceModelSelect
                label="Hearing model"
                options={voiceModels[form.voice_engine].hear}
                defaultModel={voiceModels[form.voice_engine].defaults.hear}
                value={form.voice_hear_model}
                onChange={(v) => set("voice_hear_model", v)}
              />
            </Row>
            <Row label="Speaking model" hint="Reads his answers aloud.">
              <VoiceModelSelect
                label="Speaking model"
                options={voiceModels[form.voice_engine].speak}
                defaultModel={voiceModels[form.voice_engine].defaults.speak}
                value={form.voice_speak_model}
                onChange={(v) => set("voice_speak_model", v)}
              />
            </Row>
          </>
        )}
        {form.voice_engine === "gemini" ? (
          <Row
            wide
            label="His voice"
            hint="Gemini's voices, the same choice as Gemini live calls. Press ▶ to hear each one."
          >
            <GeminiVoicePicker value={form.gemini_voice} onChange={(v) => set("gemini_voice", v)} />
          </Row>
        ) : (
          <Row wide label="His voice" hint="Used for spoken answers and OpenAI live calls. Press ▶ to hear each one.">
            <VoicePicker
              voices={voices ?? [form.tts_voice]}
              value={form.tts_voice}
              accent={form.voice_accent}
              onChange={(v) => set("tts_voice", v)}
            />
          </Row>
        )}
        <Row label="Accent" hint="How he pronounces Urdu and English. The ▶ samples use this accent.">
          <Segmented
            label="Accent"
            value={form.voice_accent}
            onChange={(v) => set("voice_accent", v)}
            options={ACCENTS}
          />
        </Row>
        <Row
          label="Speaking speed"
          hint={form.voice_engine === "gemini" ? "For OpenAI only: Gemini speaks at its own pace." : "For spoken answers and calls."}
        >
          <div className="flex max-w-sm items-center gap-4">
            <input
              type="range"
              min={0.75}
              max={1.5}
              step={0.05}
              value={form.tts_speed}
              onChange={(e) => set("tts_speed", Number(e.target.value))}
              aria-label="Speaking speed"
              className="flex-1 accent-[var(--accent)]"
            />
            <span className="w-14 rounded-lg bg-panel-2 py-1 text-center text-sm tabular-nums">
              {Number(form.tts_speed).toFixed(2)}×
            </span>
          </div>
        </Row>
        <Row label="Auto-play answers" hint="When you send a voice message, he reads his answer aloud.">
          <Toggle
            label="Auto-play answers"
            checked={form.voice_autoplay}
            onChange={(v) => set("voice_autoplay", v)}
          />
        </Row>
      </Section>

      <Section
        id="calls"
        title="Live calls"
        description="Real-time voice conversations. These cost the most, so they have their own limits."
      >
        <Row
          wide
          label="Voice engine"
          hint={
            <>
              Who runs the call. Gemini is much cheaper (about $0.02 a minute, with a free tier) and searches Google
              by itself; OpenAI is what you used so far.
              {form.voice_provider_model !== "openai-realtime" && limits && !limits.gemini_ready && (
                <span className="mt-1 block text-warn">
                  Gemini needs <code>GEMINI_API_KEY</code> in backend/.env (from aistudio.google.com/apikey), then a restart.
                </span>
              )}
            </>
          }
        >
          <Segmented
            label="Voice engine"
            value={form.voice_provider_model}
            onChange={(v) => set("voice_provider_model", v)}
            options={[
              { value: "openai-realtime", label: "OpenAI Realtime", sub: "Natural or Economy below · ~$0.02–0.05/min" },
              { value: "gemini-3.8-live", label: "Gemini 3.8 Live", sub: "Newest, fastest · ~$0.023/min" },
              {
                value: "gemini-2.5-flash-native-audio-preview-12-2025",
                label: "Gemini 2.5 Flash Live",
                sub: "Budget · ~$0.02/min",
              },
            ]}
          />
        </Row>
        {form.voice_provider_model !== "openai-realtime" && (
          <Row
            wide
            label="Gemini voice"
            hint="Gemini has its own voices. Press ▶ to hear one; he speaks Urdu and English in Pakistani style either way."
          >
            <GeminiVoicePicker value={form.gemini_voice} onChange={(v) => set("gemini_voice", v)} />
          </Row>
        )}
        <Row label="Call quality" hint="For OpenAI Realtime only.">
          <Segmented
            label="Call quality"
            value={form.call_quality}
            onChange={(v) => set("call_quality", v)}
            options={[
              { value: "natural", label: "Natural", sub: "Most human · ~$0.05/min" },
              { value: "economy", label: "Economy", sub: "Flatter · ~$0.02/min" },
            ]}
          />
        </Row>
        <Row label="Turn-taking" hint="How long he waits when you pause before he answers.">
          <Segmented
            label="Turn-taking"
            value={form.turn_taking}
            onChange={(v) => set("turn_taking", v)}
            options={[
              { value: "patient", label: "Patient", sub: "Lets you think" },
              { value: "balanced", label: "Balanced", sub: "Recommended" },
              { value: "quick", label: "Quick", sub: "Any pause" },
            ]}
          />
        </Row>
        <Row label="Microphone" hint="Noise reduction tuned to your microphone.">
          <Segmented
            label="Microphone"
            value={form.mic_type}
            onChange={(v) => set("mic_type", v)}
            options={[
              { value: "headset", label: "Headset", sub: "Or earphones" },
              { value: "laptop", label: "Laptop mic", sub: "Or desk mic" },
              { value: "off", label: "Off", sub: "No filtering" },
            ]}
          />
        </Row>
        <Row label="Minutes per day" hint="A call ends when today's minutes run out.">
          <div className="flex max-w-[12rem] items-center rounded-xl border border-line bg-bg focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/20">
            <input
              type="number"
              min={0}
              max={600}
              step={5}
              value={form.call_minutes_per_day}
              onChange={(e) => set("call_minutes_per_day", e.target.value as unknown as number)}
              className="w-full bg-transparent px-3.5 py-2.5 text-sm outline-none"
              aria-label="Live-call minutes per day"
            />
            <span className="pr-3.5 text-xs whitespace-nowrap text-muted">minutes</span>
          </div>
        </Row>
      </Section>

      <ConnectionsSection />

      <ComputerSection enabled={form.computer_enabled} onEnabled={(v) => set("computer_enabled", v)} />
      <Section id="skills" title="Skills" description="Teach Junior how you like work done. Add, edit or delete instructions for your everyday tasks.">
        <SkillsSettings />
      </Section>

      <Section id="posting" title="Posting" description="Posts that go out through the official APIs (Facebook Page, Instagram, LinkedIn).">
        <Row
          label="Posts per platform per day"
          hint="The Safety Guard stops more than this many API posts on one platform in a day. Copy-and-paste items don't count."
        >
          <input
            type="number"
            min={0}
            max={50}
            value={form.api_posts_per_day}
            onChange={(e) => set("api_posts_per_day", Number(e.target.value))}
            className={`${input} w-28`}
            aria-label="Posts per platform per day"
          />
        </Row>
      </Section>

      <Section id="whatsapp" title="WhatsApp" description="How your WhatsApp messages are grouped into chats (each shows with 🟢 in your chat list).">
        <Row label="WhatsApp action mode" hint="Applies to requests received from WhatsApp, separately from the dashboard mode. Manual asks before actions; Auto follows your permission rules.">
          <select value={form.whatsapp_action_mode} onChange={(e) => set("whatsapp_action_mode", e.target.value as "ask_all" | "rules")}
            className={`${input} max-w-sm`} aria-label="WhatsApp action mode">
            <option value="ask_all">Manual</option><option value="rules">Auto</option>
          </select>
        </Row>
        <Row
          label="Start a new chat"
          hint="Within one chat Junior Muneer remembers what you said. Your saved memories work in every chat."
        >
          <select
            value={String(form.whatsapp_session_hours)}
            onChange={(e) => set("whatsapp_session_hours", Number(e.target.value))}
            className={`${input} max-w-sm`}
            aria-label="Start a new WhatsApp chat"
          >
            <option value="6">After 6 quiet hours</option>
            <option value="12">After 12 quiet hours</option>
            <option value="24">After 24 quiet hours</option>
            <option value="0">With every message</option>
          </select>
        </Row>
        <Row
          label="Carry the thread over"
          hint="A new chat starts with a summary of the previous one (its last messages, or its summary if it was long). No extra cost."
        >
          <Toggle
            checked={form.whatsapp_carry_summary}
            onChange={(v) => set("whatsapp_carry_summary", v)}
            label="Start a new WhatsApp chat with a summary of the previous one"
          />
        </Row>
      </Section>

      <Section id="news" title="News & email" description="Morning news, the top 5 by email, your Gmail inbox and the morning briefing.">
        <Row
          label="Morning digests"
          hint="Both digests are built each morning, so news questions are answered in seconds. Skipped while paused or when the daily cap is reached."
        >
          <div className="flex flex-wrap items-center gap-3">
            <Toggle
              checked={form.news_digest_enabled}
              onChange={(v) => set("news_digest_enabled", v)}
              label="Build the news digests every morning"
            />
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted">at</span>
              <input
                type="time"
                value={form.news_digest_time}
                disabled={!form.news_digest_enabled}
                onChange={(e) => set("news_digest_time", e.target.value)}
                className={`${input} w-32 disabled:opacity-50`}
                aria-label="Morning digest time"
              />
            </label>
          </div>
        </Row>
        <Row
          label="Top 5 AI news by email"
          hint="After the morning digest, the day's top 5 AI news goes to your own Gmail. Only ever to your address."
        >
          <div className="flex flex-col gap-2">
            <Toggle
              checked={form.news_email_enabled}
              onChange={(v) => set("news_email_enabled", v)}
              label="Email me the top 5 AI news every morning"
            />
            <NewsEmailStatus />
          </div>
        </Row>
        <Row
          label="Watch my Gmail"
          hint="Every 5 minutes, new emails are sorted (client, money, security...) with a one-line summary. Promotions and social mail cost nothing. See them on the Inbox page."
        >
          <div className="flex flex-col gap-2">
            <Toggle
              checked={form.email_watch_enabled}
              onChange={(v) => set("email_watch_enabled", v)}
              label="Watch my Gmail inbox"
            />
            <label className="flex items-center gap-2 text-sm">
              <Toggle
                checked={form.email_notify_whatsapp}
                onChange={(v) => set("email_notify_whatsapp", v)}
                label="Send important emails to my WhatsApp"
              />
              <span className="text-muted">Send important ones to my WhatsApp</span>
            </label>
          </div>
        </Row>
        <Row
          label="Morning briefing"
          hint="Each morning: what needs you today, what got done yesterday, and the news, from the app's records only. About $0.001. Skipped while paused."
        >
          <div className="flex flex-wrap items-center gap-3">
            <Toggle
              checked={form.briefing_enabled}
              onChange={(v) => set("briefing_enabled", v)}
              label="Write a morning briefing every day"
            />
            <label className="flex items-center gap-2 text-sm">
              <span className="text-muted">at</span>
              <input
                type="time"
                value={form.briefing_time}
                disabled={!form.briefing_enabled}
                onChange={(e) => set("briefing_time", e.target.value)}
                className={`${input} w-32 disabled:opacity-50`}
                aria-label="Morning briefing time"
              />
            </label>
          </div>
        </Row>
      </Section>

      <PermissionsSection />
      <AdvancedSection />

      {/* Save bar: appears when something changed. */}
      <div
        className={`fixed inset-x-0 bottom-0 z-20 flex justify-center px-4 pb-4 transition ${
          changed || status ? "translate-y-0 opacity-100" : "pointer-events-none translate-y-4 opacity-0"
        }`}
      >
        <div className="flex w-full max-w-xl items-center gap-3 rounded-2xl border border-line bg-panel px-4 py-3 shadow-lg">
          <span role="status" className={`flex-1 text-sm ${status && !status.ok ? "text-danger" : status ? "text-ok" : ""}`}>
            {saving ? "Saving changes…" : status ? status.text : "Saving changes automatically…"}
          </span>
          {changed && (
            <>
              <button
                type="button"
                onClick={() => {
                  setForm(saved);
                  setStatus(null);
                }}
                className="rounded-xl px-3 py-2 text-sm text-muted hover:bg-panel-2 hover:text-ink"
              >
                Discard
              </button>
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="rounded-xl bg-accent px-5 py-2 text-sm font-semibold text-accent-fg disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save changes"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

type Platform = {
  key: string;
  label: string;
  how: string;
  ready: boolean;
  connected: boolean;
  sender: string;
  connect?: string; // "device": connect in the app (GitHub)
  source?: string; // GitHub: app · gh · env
  account?: string;
};

function ConnectionRow({ p }: { p: Platform }) {
  const { mutate } = useSWRConfig();
  const [result, setResult] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  async function check() {
    setChecking(true);
    try {
      const r = await send<{ result: string }>("POST", `/api/connections/${p.key}/check`);
      setResult(r.result);
    } catch (e) {
      setResult(e instanceof Error ? e.message : "Couldn't check");
    } finally {
      setChecking(false);
    }
  }
  async function disconnect() {
    try {
      const r = await send<{ message: string }>("DELETE", "/api/github/connection");
      setResult(r.message);
    } catch (e) {
      setResult(e instanceof Error ? e.message : "Couldn't disconnect");
    }
    void mutate("/api/connections");
  }
  const inApp = p.source === "app";
  return (
    <Row wide label={p.label}>
      <div className="flex flex-col gap-1.5 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          {p.connected ? (
            <Badge tone="ok">
              Connected
              {inApp && p.account ? ` as @${p.account}` : ""}
              {p.source === "gh" ? " (GitHub CLI login)" : p.source === "env" ? " (token in backend/.env)" : ""}
              {p.sender.includes("(fake)") ? " (fake, for trying it out)" : ""}
            </Badge>
          ) : (
            <Badge tone="muted">{p.ready ? "Not connected" : "Coming soon"}</Badge>
          )}
          {p.connected && (
            <button type="button" onClick={check} disabled={checking} className="rounded-lg border border-line px-2.5 py-1 text-xs hover:bg-panel-2">
              {checking ? "Checking…" : "Check"}
            </button>
          )}
          {inApp && (
            <button type="button" onClick={disconnect} className="rounded-lg border border-line px-2.5 py-1 text-xs text-muted hover:bg-panel-2 hover:text-ink">
              Disconnect
            </button>
          )}
        </div>
        {p.connect === "device" && !inApp && (
          <GitHubConnect
            onConnected={() => {
              setResult(null);
              void mutate("/api/connections");
            }}
          />
        )}
        {result && <p className="text-xs text-muted" role="status">{result}</p>}
        {!p.connected && p.ready && p.connect !== "device" && (
          <p className="text-xs leading-relaxed text-muted">
            Run <code>{p.how}</code> in the project folder (the steps are in TASK.md), then restart. Your tokens stay
            in <code>backend/.env</code>: never in the browser or in Git.
          </p>
        )}
      </div>
    </Row>
  );
}

type GoogleStatus = { configured: boolean; connected: boolean; account: string; missing: string[]; redirect_uri: string; drive_folder_access: boolean };

/** Google Docs, Sheets and Calendar: Google's own consent page, then back here. */
function GoogleConnection() {
  const { data: sharing, mutate: refreshSharing } = useSWR<Settings>("/api/settings", fetcher);
  const { data, mutate } = useSWR<GoogleStatus>("/api/google/status", fetcher);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    // Google sends you back here with ?google=connected or ?google=error&message=...
    const q = new URLSearchParams(window.location.search);
    const result = q.get("google");
    if (!result) return;
    // Apply the external redirect result after the initial render. Cleanup also
    // leaves the query intact when React replays this effect in development.
    const frame = requestAnimationFrame(() => {
      setMessage(
        result === "connected"
          ? { ok: true, text: `Connected${q.get("account") ? ` as ${q.get("account")}` : ""}.` }
          : { ok: false, text: q.get("message") || "Google didn't connect." },
      );
      window.history.replaceState(null, "", `${window.location.pathname}#connections`);
      void mutate();
    });
    return () => cancelAnimationFrame(frame);
  }, [mutate]);

  async function disconnect() {
    try {
      const r = await send<{ message: string }>("DELETE", "/api/google/connection");
      setMessage({ ok: true, text: r.message });
    } catch (e) {
      setMessage({ ok: false, text: e instanceof Error ? e.message : "Couldn't disconnect" });
    }
    void mutate();
  }

  if (!data) return null;
  return (
    <Row wide label="Google (Docs, Sheets, Slides, Calendar, Drive, Gmail)">
      <div className="flex flex-col gap-1.5 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          {data.connected ? (
            <Badge tone="ok">Connected{data.account ? ` as ${data.account}` : ""}</Badge>
          ) : (
            <Badge tone="muted">Not connected</Badge>
          )}
          {data.configured && (
            <a
              href={`${BACKEND_URL}/api/google/connect`}
              className={
                data.connected
                  ? "rounded-lg border border-line px-2.5 py-1 text-xs hover:bg-panel-2"
                  : "rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg hover:opacity-90"
              }
            >
              {data.connected ? "Connect again" : "Connect Google"}
            </a>
          )}
          {data.connected && (
            <button type="button" onClick={disconnect} className="rounded-lg border border-line px-2.5 py-1 text-xs text-muted hover:bg-panel-2 hover:text-ink">
              Disconnect
            </button>
          )}
        </div>
        {data.connected && data.missing.length > 0 && (
          <p className="text-xs text-warn">
            Not allowed on Google: {data.missing.join(", ")}. Use “Connect again” and tick them, if you want those.
          </p>
        )}
        <p className="text-xs text-muted">Slides uses the existing file-creation permission. Enable Google Slides API in your Google Cloud project if Google reports it is disabled. Local PDF and PowerPoint downloads work without Google.</p>
        {data.connected && !data.drive_folder_access && (
          <div className="mt-1 text-xs text-muted">
            <p>To save directly into folders you already created, Google requires broader Drive access. Junior still adds copies and keeps existing files.</p>
            <a href={`${BACKEND_URL}/api/google/connect?drive_folders=true`} className="mt-1 inline-block text-accent underline">Allow existing Drive folders</a>
          </div>
        )}
        {data.connected && data.drive_folder_access && <p className="text-xs text-muted">Saving into your existing Drive folders is allowed on Google.</p>}
        {data.connected && <label className="mt-2 block text-xs text-muted">Default sharing for new documents and notes
          <select aria-label="Default Drive sharing" value={sharing?.drive_share_default ?? "private"} onChange={async (event) => {
            try { await send("PATCH", "/api/settings", { drive_share_default: event.target.value }); await refreshSharing(); }
            catch (error) { setMessage({ ok: false, text: error instanceof Error ? error.message : "Couldn't change sharing" }); }
          }} className="mt-1 block rounded-lg border border-line bg-bg px-2 py-1.5 text-sm text-ink">
            <option value="private">Private</option><option value="reader">Anyone with the link can view</option><option value="writer">Anyone with the link can edit</option>
          </select>
          {sharing?.drive_share_default === "writer" && <span className="mt-1 block">Anyone who gets the link will be able to change these files.</span>}
        </label>}
        {!data.configured && (
          <p className="text-xs leading-relaxed text-muted">
            First add your Google Cloud project&apos;s OAuth client to <code>backend/.env</code> (<code>GOOGLE_CLIENT_ID</code>,{" "}
            <code>GOOGLE_CLIENT_SECRET</code>; its redirect URI must be <code>{data.redirect_uri}</code>), then restart.
          </p>
        )}
        {data.configured && !data.connected && (
          <p className="text-xs text-muted">
            Asks only for: files the app creates, finding and reading your Drive files (read-only: never changes or
            deletes them), calendar events, reading Gmail and making drafts you approve.
          </p>
        )}
        {message && (
          <p role={message.ok ? "status" : "alert"} className={`text-xs ${message.ok ? "text-ok" : "text-danger"}`}>
            {message.text}
          </p>
        )}
      </div>
    </Row>
  );
}

type ComputerStatus = {
  enabled: boolean;
  all_files: boolean;
  folders: { path: string; exists: boolean }[];
  using_defaults: boolean;
  defaults: string[];
  blocked: string[];
};

/** Settings → Computer: which folders on this PC the computer tools may use. */
function ComputerSection({ enabled, onEnabled }: { enabled: boolean; onEnabled: (v: boolean) => void }) {
  const { data, mutate } = useSWR<ComputerStatus>("/api/computer", fetcher);
  const [path, setPath] = useState("");
  const [error, setError] = useState("");

  async function change(url: string, folder: string) {
    setError("");
    try {
      await mutate(await send<ComputerStatus>("POST", url, { path: folder }), { revalidate: false });
      if (url.endsWith("/folders")) setPath("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't change it");
    }
  }

  async function changeScope(allFiles: boolean) {
    setError("");
    try {
      await send("PATCH", "/api/settings", { computer_all_files: allFiles });
      await mutate();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't change file access");
    }
  }

  return (
    <Section
      id="computer"
      title="Computer"
      description="What Junior may use on this PC: reading, changing and running things, always through your Permissions rules."
    >
      <Row label="Computer tools" hint="Off: he can't look at or change anything on this PC.">
        <Toggle label="Computer tools" checked={enabled} onChange={onEnabled} />
      </Row>
      <Row label="Allow all local drives" hint="Use files across local drives. Protected system and secret paths remain blocked. Your folder list is kept when you turn this off.">
        <Toggle label="Allow all local drives" checked={data?.all_files ?? false} onChange={(value) => void changeScope(value)} />
      </Row>
      <Row
        wide
        label="Allowed folders"
        hint="When all local drives is off, Junior can work inside these folders or a full path you type yourself."
      >
        <div className="flex max-w-2xl flex-col gap-2">
          <ul aria-label="Allowed folders" className="flex flex-col gap-1.5">
            {data?.folders.map((f) => (
              <li key={f.path} className="flex items-center gap-2 rounded-lg border border-line px-3 py-2 text-sm">
                <span className="min-w-0 flex-1 truncate font-mono text-[13px]" title={f.path}>
                  {f.path}
                </span>
                {!f.exists && <Badge tone="muted">missing</Badge>}
                <button
                  type="button"
                  onClick={() => change("/api/computer/folders/remove", f.path)}
                  aria-label={`Remove ${f.path}`}
                  className="rounded-md px-2 py-0.5 text-xs text-muted hover:bg-panel-2 hover:text-ink"
                >
                  Remove
                </button>
              </li>
            ))}
            {data && data.folders.length === 0 && <li className="text-sm text-muted">No folders: only paths you type.</li>}
          </ul>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (path.trim()) void change("/api/computer/folders", path.trim());
            }}
          >
            <input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              placeholder="D:\Projects"
              aria-label="Folder to allow"
              className={`${input} font-mono text-[13px]`}
            />
            <button
              type="submit"
              disabled={!path.trim()}
              className="shrink-0 rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg hover:opacity-90 disabled:opacity-40"
            >
              Add folder
            </button>
          </form>
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}
        </div>
      </Row>
      <Row wide label="Always blocked" hint="Never opened, even when you type the path.">
        <ul className="list-disc space-y-1 pl-5 text-[13px] text-muted">
          {data?.blocked.map((b) => <li key={b}>{b}</li>)}
        </ul>
      </Row>
      <Row wide label="Background commands" hint="Approved commands with output and Stop controls.">
        <ComputerJobs />
      </Row>
      <Row wide label="App windows" hint="Observe and control selected local apps, one reviewed action at a time.">
        <DesktopSettings />
        <div className="border-t border-line" />
        <BrowserSettings />
      </Row>
    </Section>
  );
}

function ConnectionsSection() {
  const { data } = useSWR<Platform[]>("/api/connections", fetcher);
  return (
    <Section
      id="connections"
      title="Connections"
      description="Accounts connected through their official API. Anything that changes something waits for your OK; the rest stays copy and paste."
    >
      {data?.map((p) => <ConnectionRow key={p.key} p={p} />)}
      <GoogleConnection />
    </Section>
  );
}

const RULE_LABEL: Record<Rule, string> = { ask: "Ask", auto: "Auto", deny: "Deny" };

function PermissionsSection() {
  const { data, mutate } = useSWR<Permissions>(PERMISSIONS_KEY, fetcher);
  const [error, setError] = useState<string | null>(null);

  async function change(path: string, body: object) {
    setError(null);
    try {
      await mutate(send<Permissions>("PUT", path, body), { revalidate: false });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't save");
    }
  }

  const groups = data ? [...new Set(data.types.map((t) => t.group))] : [];
  return (
    <Section
      id="permissions"
      title="Permissions"
      description="What he may do on his own. Ask: waits for your click. Auto: runs by itself (still logged). Deny: never."
    >
      {data && (
        <>
          <Row
            label="Mode"
            hint={
              data.paused
                ? "Everything is paused right now (Today panel), so nothing runs until you resume."
                : "The same modes as the menu under the message box. Pause everything is there too."
            }
          >
            <Segmented
              label="Permission mode"
              value={data.mode}
              onChange={(mode) => change("/api/permissions/mode", { mode })}
              options={[
                { value: "rules", label: "Auto", sub: "Each action follows its rule below" },
                { value: "ask_all", label: "Manual", sub: "Every action waits for you" },
                { value: "plan", label: "Plan", sub: "A plan first; nothing is done until you switch" },
              ]}
            />
          </Row>
          {groups.map((group) => (
            <Row wide key={group} label={group}>
              <ul className="divide-y divide-line rounded-xl border border-line">
                {data.types
                  .filter((t) => t.group === group)
                  .map((t) => (
                    <li key={t.type} className="flex flex-wrap items-center gap-x-4 gap-y-2 px-3.5 py-2.5">
                      <div className="min-w-0 flex-1">
                        <p className="text-sm">{t.label}</p>
                        {t.note && <p className="text-xs text-muted">{t.note}</p>}
                      </div>
                      {t.locked ? (
                        <span title="Locked for your safety; it can't be changed." className="flex items-center gap-1.5">
                          <Badge tone={t.rule === "deny" ? "warn" : "muted"}>{RULE_LABEL[t.rule]}</Badge>
                          <span className="text-xs text-muted">🔒 locked</span>
                        </span>
                      ) : (
                        <div role="radiogroup" aria-label={t.label} className="flex rounded-lg border border-line p-0.5">
                          {(["ask", "auto", "deny"] as const).map((r) => (
                            <button
                              key={r}
                              type="button"
                              role="radio"
                              aria-checked={t.rule === r}
                              onClick={() => t.rule !== r && change(`/api/permissions/rules/${t.type}`, { rule: r })}
                              className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                                t.rule === r ? "bg-accent text-accent-fg" : "text-muted hover:bg-panel-2 hover:text-ink"
                              }`}
                            >
                              {RULE_LABEL[r]}
                            </button>
                          ))}
                        </div>
                      )}
                    </li>
                  ))}
              </ul>
            </Row>
          ))}
          <p className="px-6 py-4 text-xs leading-relaxed text-muted">
            Anything caused by outside content (emails, comments, pasted text, web pages) always waits for you,
            except browser actions verified against your request. Permissions do not add unavailable capabilities or
            bypass Computer and Browser restrictions. Copy-and-paste items (Upwork, Fiverr, LinkedIn comments, X) are never sent by him.
            {error && <span className="mt-1 block text-danger">{error}</span>}
          </p>
        </>
      )}
    </Section>
  );
}

function AdvancedSection() {
  const { data } = useSWR<ModelsView>("/api/models", fetcher);
  const [open, setOpen] = useState(false);
  return (
    <Section id="advanced" title="Advanced" description="What each agent uses right now.">
      <UpdatesSettings />
      <CodeSettings />
      <div className="px-6 py-4">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
          className="text-sm font-medium text-accent hover:underline"
        >
          {open ? "Hide" : "Show"} models per agent
        </button>
        {open && data && (
          <div className="mt-3 overflow-x-auto rounded-xl border border-line">
            <table className="w-full text-sm">
              <thead className="bg-panel-2 text-left text-xs text-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">Agent</th>
                  <th className="px-3 py-2 font-medium">Model</th>
                  <th className="px-3 py-2 font-medium">$ per 1M (in / out)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {data.agents.map((a) => (
                  <tr key={a.agent} title={a.description}>
                    <td className="px-3 py-2">{a.agent}</td>
                    <td className="px-3 py-2 font-mono text-xs">{a.model}</td>
                    <td className="px-3 py-2 tabular-nums">
                      {a.price_per_million.input} / {a.price_per_million.output}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="px-3 py-2 text-xs text-muted">
              Defaults live in <code>agents/models.toml</code>.
            </p>
          </div>
        )}
      </div>
    </Section>
  );
}

// ---- page -----------------------------------------------------------------------------

/** The section in the address (#news), or Profile. Follows the back and forward buttons. */
function useActiveSection(): [SectionId, (id: SectionId) => void] {
  const [active, setActive] = useState<SectionId>("profile");
  useEffect(() => {
    const read = () => {
      const id = window.location.hash.slice(1);
      setActive(isSection(id) ? id : "profile");
    };
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);
  const choose = (id: SectionId) => {
    setActive(id);
    window.history.replaceState(null, "", `${window.location.pathname}${window.location.search}#${id}`);
  };
  return [active, choose];
}

export default function SettingsPage() {
  const { data, error } = useSWR<Settings>(SETTINGS_KEY, fetcher);
  const [active, choose] = useActiveSection();
  const current = SECTIONS.find((s) => s.id === active)!;
  return (
    <ActiveSection.Provider value={active}>
      <div className="flex h-dvh flex-col bg-bg">
        <header className="flex shrink-0 items-center gap-3 border-b border-line bg-panel px-4 py-3 sm:px-6">
          <Link href="/" className="rounded-lg px-2 py-1 text-sm text-muted hover:bg-panel-2 hover:text-ink">
            ← Back to Junior
          </Link>
          <span className="h-5 w-px bg-line" aria-hidden />
          <h1 className="text-base font-semibold tracking-tight">Settings</h1>
          <span className="ml-auto hidden text-xs text-muted sm:inline">Changes apply from your next message or call.</span>
        </header>

        <div className="flex min-h-0 flex-1">
          <nav aria-label="Settings sections" className="hidden w-64 shrink-0 overflow-y-auto border-r border-line px-3 py-5 md:block">
            {GROUPS.map((group) => (
              <div key={group.title} className="mb-5">
                <p className="mb-1 px-3 text-[13px] text-muted">{group.title}</p>
                <ul className="flex flex-col gap-0.5">
                  {group.items.map((s) => (
                    <li key={s.id}>
                      <button
                        type="button"
                        onClick={() => choose(s.id)}
                        aria-current={active === s.id ? "page" : undefined}
                        className={`flex w-full items-center gap-3 rounded-lg px-3 py-[7px] text-left text-[15px] transition ${
                          active === s.id ? "bg-panel-2 text-ink" : "text-ink/80 hover:bg-panel-2/60 hover:text-ink"
                        }`}
                      >
                        <SettingsIcon name={s.id === "scheduled" ? "tasks" : s.id} className="h-[18px] w-[18px] shrink-0 opacity-90" />
                        {s.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </nav>

          <main className="min-w-0 flex-1 overflow-y-auto">
            <div className="mx-auto max-w-5xl px-4 py-6 sm:px-8 sm:py-8">
              {/* Phones: the menu becomes a picker. */}
              <label className="mb-5 flex flex-col gap-1 md:hidden">
                <span className="text-xs text-muted">Section</span>
                <select
                  value={active}
                  onChange={(e) => choose(e.target.value as SectionId)}
                  aria-label="Settings section"
                  className="rounded-lg border border-line bg-panel px-3 py-2 text-sm"
                >
                  {GROUPS.map((g) => (
                    <optgroup key={g.title} label={g.title}>
                      {g.items.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.title}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                </select>
              </label>
              <p className="sr-only" aria-live="polite">
                {current.title}
              </p>
              {error && <p className="text-danger">Couldn&apos;t load settings: {error.message}</p>}
              {data && <SettingsForm initial={data} />}
            </div>
          </main>
        </div>
      </div>
    </ActiveSection.Provider>
  );
}
