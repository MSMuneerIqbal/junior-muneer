"use client";

import { useEffect, useState, type ReactNode } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";
import { urduClass } from "@/lib/urdu";

type Profile = {
  headline: string;
  about: string;
  services: string[];
  skills: string[];
  rates: string;
  proof: string[];
  audience: string;
  voice: string;
  avoid: string[];
  hashtags: string[];
  platforms: string[];
  links: string[];
  email: string;
  location: string;
  languages: string[];
};

const PLATFORMS = [
  { key: "linkedin", label: "LinkedIn" },
  { key: "facebook", label: "Facebook" },
  { key: "instagram", label: "Instagram" },
  { key: "x", label: "X" },
];

const input =
  "w-full rounded-xl border border-line bg-bg px-3.5 py-2.5 text-sm outline-none transition focus:border-accent focus:ring-2 focus:ring-accent/20";

function Section({ title, description, children }: { title: string; description: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl border border-line bg-panel shadow-sm">
      <header className="border-b border-line px-6 py-4">
        <h2 className="text-base font-semibold">{title}</h2>
        <p className="mt-0.5 text-sm text-muted">{description}</p>
      </header>
      <div className="flex flex-col gap-5 px-6 py-5">{children}</div>
    </section>
  );
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-medium">{label}</span>
      {hint && <span className="-mt-1 text-xs text-muted">{hint}</span>}
      {children}
    </label>
  );
}

/** A list edited as one item per line. */
function Lines({
  value,
  onChange,
  rows = 4,
  placeholder,
  label,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  rows?: number;
  placeholder?: string;
  label: string;
}) {
  const [text, setText] = useState(value.join("\n"));
  return (
    <textarea
      aria-label={label}
      rows={rows}
      dir="auto"
      value={text}
      placeholder={placeholder}
      onChange={(e) => {
        setText(e.target.value);
        onChange(e.target.value.split("\n"));
      }}
      className={`${input} resize-y leading-relaxed ${urduClass(text)}`}
    />
  );
}

function ProfileForm({ initial }: { initial: Profile }) {
  const [form, setForm] = useState(initial);
  const [saved, setSaved] = useState(initial);
  const [status, setStatus] = useState<{ ok: boolean; text: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const changed = JSON.stringify(form) !== JSON.stringify(saved);
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    if (!status?.ok) return;
    const t = setTimeout(() => setStatus(null), 3000);
    return () => clearTimeout(t);
  }, [status]);

  async function save() {
    setSaving(true);
    try {
      const result = await send<Profile>("PUT", "/api/profile", form);
      setSaved(result);
      setStatus({ ok: true, text: "Saved. The writing team uses it from now on." });
    } catch (e) {
      setStatus({ ok: false, text: e instanceof Error ? e.message : "Couldn't save" });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-6 pb-28">
      <Section title="What you do" description="How you'd introduce yourself to a client.">
        <Field label="Headline" hint="One line, e.g. “Agentic AI engineer building multi-agent systems”.">
          <input value={form.headline} onChange={(e) => set("headline", e.target.value)} className={input} maxLength={200} />
        </Field>
        <Field label="About you" hint="A short paragraph in your own words.">
          <textarea
            rows={5}
            dir="auto"
            value={form.about}
            onChange={(e) => set("about", e.target.value)}
            className={`${input} resize-y leading-relaxed`}
          />
        </Field>
        <Field label="Services you sell" hint="One per line.">
          <Lines label="Services" value={form.services} onChange={(v) => set("services", v)} />
        </Field>
        <Field label="Skills and tools" hint="One per line.">
          <Lines label="Skills" value={form.skills} onChange={(v) => set("skills", v)} rows={5} />
        </Field>
        <Field label="Rates" hint="e.g. “$25/hour, fixed-price projects from $300”. Left empty, he never mentions prices.">
          <input value={form.rates} onChange={(e) => set("rates", e.target.value)} className={input} maxLength={500} />
        </Field>
      </Section>

      <Section
        title="Proof"
        description="Real projects, jobs and results. The writing team may only use facts from here: nothing is invented."
      >
        <Field label="Projects, experience and results" hint="One per line. Numbers you can back up make the best posts.">
          <Lines label="Proof" value={form.proof} onChange={(v) => set("proof", v)} rows={10} />
        </Field>
        <Field label="Links" hint="Portfolio, GitHub, Upwork, LinkedIn… one per line.">
          <Lines label="Links" value={form.links} onChange={(v) => set("links", v)} rows={3} />
        </Field>
      </Section>

      <Section title="Contact" description="Kept for later (the email phase uses your address). Not put into his prompts.">
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Email">
            <input type="email" value={form.email} onChange={(e) => set("email", e.target.value)} className={input} />
          </Field>
          <Field label="Location">
            <input value={form.location} onChange={(e) => set("location", e.target.value)} className={input} />
          </Field>
        </div>
        <Field label="Languages" hint="One per line, e.g. “Urdu (native)”.">
          <Lines label="Languages" value={form.languages} onChange={(v) => set("languages", v)} rows={2} />
        </Field>
      </Section>

      <Section title="Your voice" description="How your posts should sound.">
        <Field label="Who you want to reach" hint="e.g. “Startup founders and agencies who need AI agents built”.">
          <textarea rows={2} value={form.audience} onChange={(e) => set("audience", e.target.value)} className={`${input} resize-y`} />
        </Field>
        <Field label="How you like to sound" hint="e.g. “Simple, friendly, practical; share what I built and learned”.">
          <textarea rows={2} value={form.voice} onChange={(e) => set("voice", e.target.value)} className={`${input} resize-y`} />
        </Field>
        <Field label="Never say or do" hint="One per line, e.g. “Don't claim 5+ years of experience”.">
          <Lines label="Avoid" value={form.avoid} onChange={(v) => set("avoid", v)} rows={3} />
        </Field>
        <Field label="Hashtags you use" hint="One per line, with or without #.">
          <Lines label="Hashtags" value={form.hashtags} onChange={(v) => set("hashtags", v)} rows={3} />
        </Field>
        <div className="flex flex-col gap-2">
          <span className="text-sm font-medium">Where you post</span>
          <div className="flex flex-wrap gap-2">
            {PLATFORMS.map((p) => {
              const on = form.platforms.includes(p.key);
              return (
                <button
                  key={p.key}
                  type="button"
                  aria-pressed={on}
                  onClick={() =>
                    set("platforms", on ? form.platforms.filter((k) => k !== p.key) : [...form.platforms, p.key])
                  }
                  className={`rounded-full border px-4 py-1.5 text-sm transition ${
                    on ? "border-accent bg-accent-soft font-medium" : "border-line hover:bg-panel-2"
                  }`}
                >
                  {on ? "✓ " : ""}
                  {p.label}
                </button>
              );
            })}
          </div>
        </div>
      </Section>

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
                {saving ? "Saving…" : "Save profile"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ProfilePage() {
  const { data, error } = useSWR<Profile>("/api/profile", fetcher);
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-4 py-8 sm:px-8">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight">Your profile</h1>
          <p className="mt-1 text-sm text-muted">
            Everything the writing team knows about you. Posts, comments and proposals only use facts
            from this page.
          </p>
        </header>
        {error && <p className="text-danger">Couldn&apos;t load your profile: {error.message}</p>}
        {data && <ProfileForm key={JSON.stringify(data)} initial={data} />}
      </div>
    </div>
  );
}
