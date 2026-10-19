"use client";

import Link from "next/link";
import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import useSWR, { useSWRConfig } from "swr";
import { GitHubConnect } from "@/components/GitHubConnect";
import { SettingsIcon } from "@/components/icons";
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
  | "profile" | "budget" | "models" | "voice" | "calls" | "connections" | "whatsapp" | "posting" | "news" | "permissions" | "advanced";
type MenuItem = { id: SectionId; title: string }; // its icon: SettingsIcon by id
const GROUPS: { title: string; items: MenuItem[] }[] = [
  { title: "Account", items: [{ id: "profile", title: "Profile" }, { id: "budget", title: "Budget" }] },
  {
    title: "AI",
    items: [
      { id: "models", title: "Models" },
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
  { title: "Automation", items: [{ id: "news", title: "News & email" }] },
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
  function play(voice: string, accent: string) {
    audio.current?.pause();
    if (playing === voice || loading === voice) {
      setPlaying(null);
      setLoading(null);
      return;
    }
    const el = new Audio(`${BACKEND_URL}/api/voice/preview/${voice}/${accent}.mp3`);
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
              onClick={() => preview.play(v, accent)}
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

// ---- the form ------------------------------------------------------------------------

function SettingsForm({ initial }: { initial: Settings }) {
  const { mutate } = useSWRConfig();
  const { data: voices } = useSWR<string[]>("/api/voices", fetcher);
  const { data: models } = useSWR<Choices>("/api/models/choices", fetcher);
  const [form, setForm] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const changed = (Object.keys(form) as (keyof Settings)[]).some(
    (k) => String(form[k]) !== String(saved[k]),
  );
  const set = <K extends keyof Settings>(key: K, value: Settings[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  useEffect(() => {
    if (!status?.ok) return;
    const t = setTimeout(() => setStatus(null), 3000);
    return () => clearTimeout(t);
  }, [status]);

  async function save() {
    setSaving(true);
    setStatus(null);
    try {
      const result = await send<Settings>("PATCH", SETTINGS_KEY, {
        ...form,
        daily_cap_usd: Number(form.daily_cap_usd),
        tts_speed: Number(form.tts_speed),
        call_minutes_per_day: Number(form.call_minutes_per_day),
        paused: undefined,
      });
      await mutate(SETTINGS_KEY, result, { revalidate: false });
      await mutate(USAGE_KEY);
      await mutate("/api/models");
      setForm(result);
      setSaved(result);
      setStatus({ ok: true, text: "Saved. Applies from your next message or call." });
    } catch (e) {
      setStatus({ ok: false, text: e instanceof Error ? e.message : "Couldn't save" });
    } finally {
      setSaving(false);
    }
  }

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

      <Section id="budget" title="Budget" description="A safety net against surprises.">
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
        description="Which AI writes his typed answers. Voice messages and live calls always use OpenAI."
      >
        {models ? (
          <>
            <Row
              wide
              label="Chat model"
              hint="For typed messages. Prices are US$ per 1 million tokens, in / out (a message is usually under 2,000)."
            >
              <ModelPicker
                label="Chat model"
                value={form.main_model}
                defaultModel={models.defaults.main_model}
                choices={models.choices}
                onChange={(m) => set("main_model", m)}
              />
            </Row>
            <Row wide label="Helper model" hint="Summarizes long chats in the background. A cheap model is fine.">
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

      <Section id="voice" title="Voice" description="How he sounds when he speaks to you.">
        <Row wide label="His voice" hint="Used for spoken answers and live calls. Press ▶ to hear each one.">
          <VoicePicker
            voices={voices ?? [form.tts_voice]}
            value={form.tts_voice}
            accent={form.voice_accent}
            onChange={(v) => set("tts_voice", v)}
          />
        </Row>
        <Row label="Accent" hint="How he pronounces Urdu and English. The ▶ samples use this accent.">
          <Segmented
            label="Accent"
            value={form.voice_accent}
            onChange={(v) => set("voice_accent", v)}
            options={ACCENTS}
          />
        </Row>
        <Row label="Speaking speed" hint="For spoken answers and calls.">
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
        <Row label="Call quality">
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
            {status ? status.text : "You have unsaved changes"}
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

type GoogleStatus = { configured: boolean; connected: boolean; account: string; missing: string[]; redirect_uri: string };

/** Google Docs, Sheets and Calendar: Google's own consent page, then back here. */
function GoogleConnection() {
  const { data, mutate } = useSWR<GoogleStatus>("/api/google/status", fetcher);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    // Google sends you back here with ?google=connected or ?google=error&message=...
    const q = new URLSearchParams(window.location.search);
    const result = q.get("google");
    if (!result) return;
    setMessage(
      result === "connected"
        ? { ok: true, text: `Connected${q.get("account") ? ` as ${q.get("account")}` : ""}.` }
        : { ok: false, text: q.get("message") || "Google didn't connect." },
    );
    window.history.replaceState(null, "", `${window.location.pathname}#connections`);
    void mutate();
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
    <Row wide label="Google (Docs, Sheets, Calendar, Drive, Gmail)">
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
        {!data.configured && (
          <p className="text-xs leading-relaxed text-muted">
            First add your Google Cloud project&apos;s OAuth client to <code>backend/.env</code> (<code>GOOGLE_CLIENT_ID</code>,{" "}
            <code>GOOGLE_CLIENT_SECRET</code>; its redirect URI must be <code>{data.redirect_uri}</code>), then restart.
          </p>
        )}
        {data.configured && !data.connected && (
          <p className="text-xs text-muted">
            Asks only for: files the app creates, finding and reading your Drive files (read-only: never changes or
            deletes them), and your calendar events. Never your Gmail.
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
            whatever the rule. Copy-and-paste items (Upwork, Fiverr, LinkedIn comments, X) are never sent by him.
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
                        <SettingsIcon name={s.id} className="h-[18px] w-[18px] shrink-0 opacity-90" />
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
