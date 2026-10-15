"use client";

import { useState } from "react";
import { toLocalInput, useApprovalItem, whenText } from "@/lib/approvals";
import type { ApprovalItem, ApprovalStatus } from "@/lib/types";
import { BACKEND_URL } from "@/lib/api";
import { urduClass } from "@/lib/urdu";

const STATUS: Record<ApprovalStatus, { label: string; style: string }> = {
  waiting: { label: "Waiting for you", style: "bg-warn-soft text-warn" },
  approved: { label: "Approved", style: "bg-accent-soft text-accent" },
  posted: { label: "Posted", style: "bg-accent-soft text-ok" },
  rejected: { label: "Rejected", style: "bg-panel-2 text-muted" },
  check_manually: { label: "Check manually", style: "bg-danger-soft text-danger" },
};

const button =
  "rounded-lg border border-line px-3 py-1.5 text-sm font-medium transition hover:bg-panel-2 disabled:opacity-50";
const primary =
  "rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg transition hover:opacity-90 disabled:opacity-50";

/** For API items: why it wasn't sent, or what to check. */
function SendState({
  item,
  busy,
  onResolve,
}: {
  item: ApprovalItem;
  busy: boolean;
  onResolve: (posted: boolean) => void;
}) {
  const blocked = Array.isArray(item.meta.blocked) ? (item.meta.blocked as string[]) : [];
  const error = typeof item.meta.last_error === "string" ? item.meta.last_error : "";
  if (item.status === "check_manually") {
    return (
      <div role="alert" className="mx-4 mb-3 rounded-lg bg-warn-soft px-3 py-2 text-xs text-warn">
        <p className="font-medium">We couldn&apos;t tell if it was posted.</p>
        {error && <p className="mt-0.5">{error}</p>}
        <p className="mt-1">Check {item.platform_label}, then tell us:</p>
        <div className="mt-1.5 flex flex-wrap gap-2">
          <button type="button" disabled={busy} onClick={() => onResolve(true)} className="rounded-md bg-warn px-2.5 py-1 font-medium text-white">
            It&apos;s posted
          </button>
          <button type="button" disabled={busy} onClick={() => onResolve(false)} className="rounded-md border border-warn/50 px-2.5 py-1 font-medium">
            It didn&apos;t post
          </button>
        </div>
      </div>
    );
  }
  if (item.status !== "approved") return null;
  if (blocked.length || error) {
    return (
      <p role="note" className="mx-4 mb-3 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">
        Not posted: {blocked[0] ?? error}
      </p>
    );
  }
  if (!item.can_send) {
    return (
      <p className="mx-4 mb-3 text-xs text-muted">
        Approved. {item.platform_label} isn&apos;t connected yet: connect it in Settings, or copy it and post it yourself.
      </p>
    );
  }
  return null;
}

/** A draft waiting for your OK: the same card in the chat and on the Approvals page. */
export function ApprovalCard({ item: initial }: { item: ApprovalItem }) {
  const { item, act } = useApprovalItem(initial);
  const [editing, setEditing] = useState<string | null>(null);
  const [planning, setPlanning] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const waiting = item.status === "waiting";
  const status = STATUS[item.status];

  async function run(action: Parameters<typeof act>[0], body?: Parameters<typeof act>[1]) {
    setBusy(true);
    setError(null);
    try {
      await act(action, body);
      if (action === "edit") setEditing(null);
      if (action === "plan") setPlanning(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't work");
    } finally {
      setBusy(false);
    }
  }

  async function copy() {
    try {
      await navigator.clipboard.writeText(item.text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError("Couldn't copy. Select the text and copy it yourself.");
    }
  }

  return (
    <article
      aria-label={`${item.platform_label} ${item.item_type}: ${item.title}`}
      className="rounded-2xl border border-line bg-panel shadow-sm"
    >
      <header className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-2.5">
        <span className="text-sm font-semibold">{item.platform_label}</span>
        <span className="text-sm capitalize text-muted">{item.item_type}</span>
        {item.meta.score !== undefined && (
          <span className="text-xs text-muted" title="Checker score">
            · {item.meta.score}/10
          </span>
        )}
        {item.due ? (
          <span className="ml-auto rounded-full bg-danger-soft px-2 py-0.5 text-[11px] font-medium text-danger" data-testid="planned">
            ⏰ Time to post
          </span>
        ) : item.planned_at && (item.status === "waiting" || item.status === "approved") ? (
          <span className="ml-auto rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-medium text-accent" data-testid="planned">
            📅 {whenText(item.planned_at)}
          </span>
        ) : null}
        <span className={`${item.planned_at && (item.status === "waiting" || item.status === "approved") ? "" : "ml-auto"} rounded-full px-2 py-0.5 text-[11px] font-medium ${status.style}`} data-testid="approval-status">
          {status.label}
        </span>
      </header>

      <div className="px-4 py-3">
        {item.title && item.title !== item.text.split("\n")[0] && (
          <p className="mb-1.5 text-xs font-medium text-muted">{item.title}</p>
        )}
        {editing !== null ? (
          <textarea
            aria-label="Edit draft"
            dir="auto"
            rows={Math.min(14, Math.max(4, editing.split("\n").length + 1))}
            value={editing}
            onChange={(e) => setEditing(e.target.value)}
            className={`w-full resize-y rounded-xl border border-line bg-bg px-3 py-2 text-sm leading-relaxed outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 ${urduClass(editing)}`}
          />
        ) : (
          <p dir="auto" className={`whitespace-pre-wrap text-sm leading-relaxed ${urduClass(item.text)}`}>
            {item.text}
          </p>
        )}
        {item.images.length > 0 && (
          <ul aria-label="Images" className="mt-3 flex flex-wrap gap-2">
            {item.images.map((img) => (
              <li key={img.id} className="group relative">
                <a href={`${BACKEND_URL}${img.url}`} target="_blank" rel="noopener noreferrer" title={`${img.name}: open full size to save it`}>
                  {/* eslint-disable-next-line @next/next/no-img-element -- served by the local backend */}
                  <img
                    src={`${BACKEND_URL}${img.url}`}
                    alt={img.name}
                    className="h-24 w-24 rounded-lg border border-line object-cover"
                  />
                </a>
                {waiting && (
                  <button
                    type="button"
                    aria-label={`Remove ${img.name}`}
                    disabled={busy}
                    onClick={() => run("remove_image", img.id)}
                    className="absolute -top-2 -right-2 flex h-6 w-6 items-center justify-center rounded-full border border-line bg-panel text-xs text-muted shadow hover:text-danger"
                  >
                    ✕
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        {item.meta.image_idea && <p className="mt-2 text-xs text-muted">🖼 Image idea: {item.meta.image_idea}</p>}
        {waiting && item.needs_image && (
          <p className="mt-2 text-xs font-medium text-warn">{item.platform_label} posts need an image: add one before posting.</p>
        )}
        {waiting && item.meta.issues && item.meta.issues.length > 0 && (
          <div className="mt-2 rounded-lg bg-warn-soft px-3 py-2 text-xs text-warn">
            <p className="font-medium">Checker&apos;s notes</p>
            <ul className="mt-0.5 list-disc pl-4">
              {item.meta.issues.map((i, n) => (
                <li key={n}>{i}</li>
              ))}
            </ul>
          </div>
        )}
        <p className="mt-2 text-xs text-muted">
          {item.kind === "copy" ? "You send this yourself. " : ""}
          {item.from_outside && "Made from outside content, so it always waits for you. "}
          {item.edits.length > 0 && `Edited ${item.edits.length}×.`}
        </p>
      </div>

      {item.kind === "api" && <SendState item={item} busy={busy} onResolve={(posted) => run("resolve", { posted })} />}

      {planning !== null && (
        <div className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5 text-sm">
          <label className="flex items-center gap-2">
            <span className="text-muted">Post on</span>
            <input
              type="datetime-local"
              aria-label="Planned time"
              value={planning}
              onChange={(e) => setPlanning(e.target.value)}
              className="rounded-lg border border-line bg-bg px-2 py-1 outline-none focus:border-accent"
            />
          </label>
          <button
            type="button"
            className={primary}
            disabled={busy || !planning}
            onClick={() => run("plan", { planned_at: new Date(planning).toISOString() })}
          >
            Save
          </button>
          {item.planned_at && (
            <button type="button" className={button} disabled={busy} onClick={() => run("plan", { planned_at: null })}>
              Clear
            </button>
          )}
          <button type="button" className={button} onClick={() => setPlanning(null)}>
            Cancel
          </button>
          <span className="w-full text-xs text-muted">You get a reminder then. Real auto-posting comes in phase 3.</span>
        </div>
      )}

      <footer className="flex flex-wrap items-center gap-2 border-t border-line px-4 py-2.5">
        {editing !== null ? (
          <>
            <button type="button" className={primary} disabled={busy} onClick={() => run("edit", { text: editing })}>
              Save
            </button>
            <button type="button" className={button} disabled={busy} onClick={() => setEditing(null)}>
              Cancel
            </button>
          </>
        ) : (
          <>
            {(item.kind === "copy" || item.status !== "posted") && (
              <>
                <button type="button" className={waiting && item.kind === "copy" ? primary : button} onClick={copy}>
                  {copied ? "Copied ✓" : "Copy"}
                </button>
                {item.open_url && (
                  <a href={item.open_url} target="_blank" rel="noopener noreferrer" className={button}>
                    {item.open_url === item.meta.source_url ? "Open original" : `Open ${item.platform_label}`} ↗
                  </a>
                )}
              </>
            )}
            {item.kind === "api" && item.status === "approved" && item.can_send && (
              <button type="button" className={primary} disabled={busy} onClick={() => run("send")}>
                {busy
                  ? "Posting…"
                  : item.meta.last_error || (Array.isArray(item.meta.blocked) && item.meta.blocked.length)
                    ? "Try again"
                    : "Post now"}
              </button>
            )}
            {item.status === "posted" && typeof item.meta.post_url === "string" && item.meta.post_url && (
              <a href={item.meta.post_url} target="_blank" rel="noopener noreferrer" className={button}>
                View post ↗
              </a>
            )}
            {waiting && item.kind === "api" && (
              <>
                <button type="button" className={primary} disabled={busy} onClick={() => run("approve")}>
                  {busy && item.can_send ? "Posting…" : item.can_send ? "Approve & post" : "Approve"}
                </button>
                {item.can_always_allow && (
                  <button
                    type="button"
                    className={button}
                    disabled={busy}
                    title="Approve, and let this kind of action run by itself from now on"
                    onClick={() => run("approve", { always_allow: true })}
                  >
                    Approve + always allow
                  </button>
                )}
              </>
            )}
            {waiting && (
              <>
                <button type="button" className={button} disabled={busy} onClick={() => setEditing(item.text)}>
                  Edit
                </button>
                <button
                  type="button"
                  className={button}
                  disabled={busy}
                  onClick={() => setPlanning(toLocalInput(item.planned_at))}
                >
                  📅 {item.planned_at ? "Change time" : "Plan"}
                </button>
                <label className={`${button} cursor-pointer`}>
                  🖼 Add image
                  <input
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    multiple
                    className="sr-only"
                    aria-label="Add image"
                    disabled={busy}
                    onChange={async (e) => {
                      const files = Array.from(e.target.files ?? []);
                      e.target.value = "";
                      for (const f of files) await run("add_image", f);
                    }}
                  />
                </label>
                {item.kind === "copy" && (
                  <button
                    type="button"
                    className={button}
                    disabled={busy || item.needs_image}
                    title={item.needs_image ? "Add an image first" : undefined}
                    onClick={() => run("posted")}
                  >
                    Mark as posted
                  </button>
                )}
                <button
                  type="button"
                  className={`${button} ml-auto text-muted hover:text-danger`}
                  disabled={busy}
                  onClick={() => run("reject")}
                >
                  Reject
                </button>
              </>
            )}
            {item.status === "rejected" && (
              <button type="button" className={`${button} ml-auto`} disabled={busy} onClick={() => run("restore")}>
                Undo reject
              </button>
            )}
          </>
        )}
        {error && (
          <p role="alert" className="w-full text-xs text-danger">
            {error}
          </p>
        )}
      </footer>
    </article>
  );
}
