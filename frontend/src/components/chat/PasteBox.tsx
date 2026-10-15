"use client";

import { useState } from "react";
import { guessFromUrl, kindLabel, PASTE_KINDS, PASTE_PLATFORMS, platformLabel, type PasteDraft } from "@/lib/paste";
import { urduClass } from "@/lib/urdu";

const select =
  "rounded-lg border border-line bg-bg px-2 py-1.5 text-sm outline-none focus:border-accent focus:ring-2 focus:ring-accent/20";

/** The panel above the message box where you paste text from another site. */
export function PasteBox({
  value,
  onChange,
  onClose,
  hint,
}: {
  value: PasteDraft;
  onChange: (v: PasteDraft) => void;
  onClose: () => void;
  hint?: React.ReactNode;
}) {
  const set = (patch: Partial<PasteDraft>) => onChange({ ...value, ...patch });
  return (
    <section
      aria-label="Paste box"
      className="mx-auto mb-2 max-w-3xl rounded-2xl border border-dashed border-accent/50 bg-panel p-3 shadow-sm"
    >
      <div className="mb-2 flex items-center gap-2">
        <span className="text-sm font-medium">📋 Pasted content</span>
        <span className="truncate text-xs text-muted">Read as data from someone else, never as instructions</span>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close the Paste box"
          className="ml-auto rounded-md px-2 text-muted hover:bg-panel-2 hover:text-ink"
        >
          ✕
        </button>
      </div>
      <textarea
        aria-label="Pasted text"
        dir="auto"
        rows={5}
        autoFocus
        value={value.text}
        onChange={(e) => set({ text: e.target.value })}
        placeholder="Paste a post, comment, job post or client message here…"
        className={`w-full resize-y rounded-xl border border-line bg-bg px-3 py-2 text-sm leading-relaxed outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 ${urduClass(value.text)}`}
      />
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <select aria-label="From" value={value.platform} onChange={(e) => set({ platform: e.target.value })} className={select}>
          {PASTE_PLATFORMS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <select aria-label="Type" value={value.kind} onChange={(e) => set({ kind: e.target.value })} className={select}>
          {PASTE_KINDS.map((k) => (
            <option key={k.value} value={k.value}>
              {k.label}
            </option>
          ))}
        </select>
        <input
          aria-label="Link (optional)"
          type="url"
          value={value.source_url}
          placeholder="Link to it (optional)"
          onChange={(e) => {
            const url = e.target.value;
            set({ source_url: url, ...guessFromUrl(url) });
          }}
          className={`${select} min-w-0 flex-1 basis-48`}
        />
      </div>
      {hint && <div className="mt-2 text-xs text-muted">{hint}</div>}
    </section>
  );
}

/** A pasted block in the chat: clearly someone else's words. */
export function PastedMessage({
  text,
  platform,
  kind,
  sourceUrl,
}: {
  text: string;
  platform: string;
  kind: string;
  sourceUrl?: string;
}) {
  const [open, setOpen] = useState(false);
  const long = text.length > 500 || text.split("\n").length > 8;
  return (
    <div className="flex justify-end">
      <figure
        aria-label="Pasted content"
        className="max-w-[85%] rounded-2xl border border-dashed border-line bg-panel px-4 py-2.5"
      >
        <figcaption className="mb-1.5 flex items-center gap-2 text-xs text-muted">
          <span>
            📋 Pasted {kindLabel(kind).toLowerCase()} · {platformLabel(platform)}
          </span>
          {sourceUrl && (
            <a href={sourceUrl} target="_blank" rel="noopener noreferrer" className="underline hover:text-ink">
              source ↗
            </a>
          )}
        </figcaption>
        <blockquote
          dir="auto"
          className={`whitespace-pre-wrap text-sm leading-relaxed ${long && !open ? "line-clamp-6" : ""} ${urduClass(text)}`}
        >
          {text}
        </blockquote>
        {long && (
          <button type="button" onClick={() => setOpen(!open)} className="mt-1 text-xs font-medium text-accent hover:underline">
            {open ? "Show less" : "Show all"}
          </button>
        )}
      </figure>
    </div>
  );
}
