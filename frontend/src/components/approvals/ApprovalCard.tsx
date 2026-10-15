"use client";

import { useState } from "react";
import { useApprovalItem } from "@/lib/approvals";
import type { ApprovalItem, ApprovalStatus } from "@/lib/types";
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

/** A draft waiting for your OK: the same card in the chat and on the Approvals page. */
export function ApprovalCard({ item: initial }: { item: ApprovalItem }) {
  const { item, act } = useApprovalItem(initial);
  const [editing, setEditing] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const waiting = item.status === "waiting";
  const status = STATUS[item.status];

  async function run(action: Parameters<typeof act>[0], body?: object) {
    setBusy(true);
    setError(null);
    try {
      await act(action, body);
      if (action === "edit") setEditing(null);
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
        <span className={`ml-auto rounded-full px-2 py-0.5 text-[11px] font-medium ${status.style}`} data-testid="approval-status">
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
        {item.meta.image_idea && <p className="mt-2 text-xs text-muted">🖼 Image idea: {item.meta.image_idea}</p>}
        <p className="mt-2 text-xs text-muted">
          {item.kind === "copy" ? "You send this yourself. " : ""}
          {item.from_outside && "Made from outside content, so it always waits for you. "}
          {item.edits.length > 0 && `Edited ${item.edits.length}×.`}
        </p>
      </div>

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
            {item.kind === "copy" && (
              <>
                <button type="button" className={waiting ? primary : button} onClick={copy}>
                  {copied ? "Copied ✓" : "Copy"}
                </button>
                {item.open_url && (
                  <a href={item.open_url} target="_blank" rel="noopener noreferrer" className={button}>
                    Open {item.platform_label} ↗
                  </a>
                )}
              </>
            )}
            {waiting && item.kind === "api" && (
              <>
                <button type="button" className={primary} disabled={busy} onClick={() => run("approve")}>
                  Approve
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
                {item.kind === "copy" && (
                  <button type="button" className={button} disabled={busy} onClick={() => run("posted")}>
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
