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

// Proposals and messages are "sent"; posts are "posted".
const SENT_KINDS = new Set(["proposal", "message", "reply", "delivery", "email", "file_transfer"]);
const isSent = (item: ApprovalItem) => SENT_KINDS.has(item.item_type) || item.platform === "upwork" || item.platform === "fiverr";
// Files, folders and commands on your PC are "done".
const onPc = (item: ApprovalItem) => item.platform === "computer";

function desktopAction(item: ApprovalItem): { kind: string; text: string; key: string } | null {
  if (item.meta.op !== "desktop") return null;
  try {
    const body = JSON.parse(item.text);
    if (body && ["focus", "click", "type", "key"].includes(body.kind)
      && typeof body.text === "string" && typeof body.key === "string") return body;
  } catch {}
  return null;
}

function browserAction(item: ApprovalItem): { kind: string; text: string; url: string } | null {
  if (item.meta.op !== "browser") return null;
  try {
    const body = JSON.parse(item.text);
    if (body && ["navigate", "click", "fill", "download"].includes(body.kind)
      && typeof body.text === "string" && typeof body.url === "string") return body;
  } catch {}
  return null;
}

/** A change to a file on your PC: removed lines red, added lines green. */
function Diff({ diff }: { diff: string }) {
  return (
    <pre aria-label="The change" className="max-h-80 overflow-auto rounded-lg border border-line bg-bg p-2 font-mono text-[12px] leading-relaxed">
      {diff.split("\n").map((line, n) => (
        <div
          key={n}
          className={
            line.startsWith("+") && !line.startsWith("+++")
              ? "bg-ok/10 text-ok"
              : line.startsWith("-") && !line.startsWith("---")
                ? "bg-danger/10 text-danger"
                : line.startsWith("@@")
                  ? "text-muted"
                  : ""
          }
        >
          {line || " "}
        </div>
      ))}
    </pre>
  );
}

const button =
  "rounded-lg border border-line px-3 py-1.5 text-sm font-medium transition hover:bg-panel-2 disabled:opacity-50";
const primary =
  "rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg transition hover:opacity-90 disabled:opacity-50";

/** A proposal's screening questions: each answer has its own box on Upwork, so its own Copy. */
function ScreeningAnswers({ answers }: { answers: { question: string; answer: string }[] }) {
  const [copied, setCopied] = useState<number | null>(null);
  return (
    <section aria-label="Screening answers" className="mt-3 flex flex-col gap-2">
      <p className="text-xs font-medium text-muted">Screening questions: paste each answer in its own box</p>
      {answers.map((a, n) => (
        <div key={n} className="rounded-lg border border-line bg-bg px-3 py-2">
          <p className="text-xs font-medium">{a.question}</p>
          <p dir="auto" className={`mt-1 whitespace-pre-wrap text-sm leading-relaxed ${urduClass(a.answer)}`}>
            {a.answer}
          </p>
          <button
            type="button"
            className="mt-1.5 rounded-md border border-line px-2 py-0.5 text-xs hover:bg-panel-2"
            onClick={async () => {
              await navigator.clipboard.writeText(a.answer);
              setCopied(n);
              setTimeout(() => setCopied(null), 2000);
            }}
          >
            {copied === n ? "Copied ✓" : `Copy answer ${n + 1}`}
          </button>
        </div>
      ))}
    </section>
  );
}

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
        {onPc(item) ? "Not done" : item.platform === "skills" ? "Not saved" : "Not posted"}: {blocked[0] ?? error}
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
  const desktop = desktopAction(item);
  const browser = browserAction(item);

  async function run(action: Parameters<typeof act>[0], body?: Parameters<typeof act>[1]) {
    setBusy(true);
    setError(null);
    try {
      if (action === "edit" && (desktop?.kind === "type" || browser?.kind === "fill") && body && typeof body === "object" && "text" in body) {
        body = { ...body, text: JSON.stringify({ ...JSON.parse(item.text), text: body.text }, null, 2) };
      }
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
        <span className="text-sm capitalize text-muted">{item.item_type.replaceAll("_", " ")}</span>
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
          {item.status === "posted" && item.item_type === "update" ? "Queued" : item.status === "posted" && item.platform === "skills" ? "Saved" : item.status === "posted" && onPc(item)
            ? item.meta.op === "start_job" ? "Started" : "Done"
            : item.status === "posted" && isSent(item) ? "Sent" : status.label}
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
            className={`w-full resize-y rounded-xl border border-line bg-bg px-3 py-2 text-sm leading-relaxed outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 ${onPc(item) ? "font-mono text-[13px]" : urduClass(editing)}`}
          />
        ) : onPc(item) ? (
          <>
            {typeof item.meta.diff === "string" && item.meta.diff && <Diff diff={item.meta.diff} />}
            {item.meta.op === "desktop" && typeof item.meta.preview_url === "string"
              && /^\/api\/computer\/desktop\/captures\/[a-f0-9]{32}$/.test(item.meta.preview_url) && (
                <figure className="mb-2">
                  <figcaption className="mb-1 text-xs text-muted">Window observed for this action</figcaption>
                  {/* eslint-disable-next-line @next/next/no-img-element -- expiring local window capture */}
                  <img src={`${BACKEND_URL}${item.meta.preview_url}`} alt="Window observed for the desktop approval"
                    className="max-h-72 max-w-full rounded-lg border border-line object-contain" />
                </figure>
              )}
            {desktop ? (
              <div className="space-y-2 text-sm">
                <p>{desktop.kind === "focus" ? "Bring this app to the front."
                  : desktop.kind === "type" ? `Focus the selected editor and type into ${item.meta.target_label || "the document"}:`
                  : desktop.kind === "key" ? `Press ${desktop.key.toUpperCase()} in ${item.meta.target_label || "the editor"}.`
                  : `Click ${item.meta.target_label || "the selected control"}.`}</p>
                {desktop.kind === "type" && <pre className="max-h-72 overflow-auto whitespace-pre-wrap break-words rounded-lg border border-line p-2 font-sans text-sm">{desktop.text}</pre>}
              </div>
            ) : browser ? (
              <div className="space-y-2 text-sm">
                <p className="break-words">{browser.kind === "navigate" ? `Open ${browser.url}`
                  : `${browser.kind === "fill" ? "Enter text into" : browser.kind === "download" ? "Download from" : "Click"} ${item.meta.target_label || "the selected control"}`}</p>
                {typeof item.meta.page_url === "string" && <p className="break-words text-xs text-muted">Page: {item.meta.page_url}</p>}
                {typeof item.meta.target_href === "string" && item.meta.target_href && <p className="break-words text-xs text-muted">Link: {item.meta.target_href}</p>}
                {browser.kind === "fill" && <pre className="max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-md border border-line p-2 font-sans">{browser.text}</pre>}
                {!!item.meta.form && typeof item.meta.form === "object" && <p className="break-words text-xs text-muted">Form destination: {String((item.meta.form as Record<string, unknown>).action || "current page")}</p>}
              </div>
            ) : item.item_type === "file" ? (
              <details open={!item.meta.diff} className="mt-1.5">
                <summary className="cursor-pointer text-xs text-muted">{item.meta.diff ? "The whole new text" : "The text"}</summary>
                <pre className="mt-1 max-h-80 overflow-auto rounded-lg border border-line bg-bg p-2 font-mono text-[12px] leading-relaxed whitespace-pre-wrap">
                  {item.text}
                </pre>
              </details>
            ) : (
              <p className="font-mono text-[13px] whitespace-pre-wrap">{item.text}</p>
            )}
            {item.status === "posted" && typeof item.meta.result === "string" &&
              (item.item_type === "command" ? (
                <pre
                  role="status"
                  aria-label="Output"
                  className="mt-1.5 max-h-80 overflow-auto rounded-lg bg-[#1e1e1e] p-2 font-mono text-[12px] leading-relaxed whitespace-pre-wrap text-[#e5e5e5]"
                >
                  {item.meta.result}
                </pre>
              ) : (
                <p role="status" className="mt-1.5 text-xs text-ok">
                  ✓ {item.meta.result}
                </p>
              ))}
          </>
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
        {item.item_type === "file_transfer" && typeof item.meta.snapshot_id === "number" && (
          <a href={`${BACKEND_URL}/api/files/${item.meta.snapshot_id}/download`} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block text-sm text-accent underline">Download prepared file</a>
        )}
        {(item.meta.sharing_role === "reader" || item.meta.sharing_role === "writer") && <p className="mt-3 rounded-lg border border-line p-2 text-sm font-medium">Anyone with the link can {item.meta.sharing_role === "writer" ? "edit this file" : "view this file"}.</p>}
        {Array.isArray(item.meta.answers) && item.meta.answers.length > 0 && (
          <ScreeningAnswers answers={item.meta.answers as { question: string; answer: string }[]} />
        )}
        {item.meta.warnings && item.meta.warnings.length > 0 && item.status !== "posted" && item.status !== "rejected" && (
          <div
            role="note"
            aria-label="Warning signs from the client"
            className="mt-2 rounded-lg bg-warn-soft px-3 py-2 text-xs text-warn"
          >
            <p className="font-medium">⚠ The client&apos;s message has warning signs. Keep everything on {item.platform_label}:</p>
            <ul className="mt-0.5 list-disc pl-4">
              {item.meta.warnings.map((w, n) => (
                <li key={n}>{w}</li>
              ))}
            </ul>
          </div>
        )}
        {item.meta.image_idea && <p className="mt-2 text-xs text-muted">🖼 Image idea: {item.meta.image_idea}</p>}
        {typeof item.meta.attachment === "string" && item.meta.attachment && (
          <p className="mt-2 text-xs text-muted" title={typeof item.meta.pc_file === "string" ? item.meta.pc_file : undefined}>
            📎 {item.meta.attachment} (from your PC)
          </p>
        )}
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

      {item.red_lines.length > 0 && item.status !== "posted" && item.status !== "rejected" && (
        <div role="alert" aria-label={`${item.platform_label}'s rules`} className="mx-4 mb-3 rounded-lg bg-danger-soft px-3 py-2 text-xs text-danger">
          <p className="font-medium">⚠ This breaks {item.platform_label}&apos;s rules. Fix it before you send it:</p>
          <ul className="mt-0.5 list-disc pl-4">
            {item.red_lines.map((r, n) => (
              <li key={n}>{r}</li>
            ))}
          </ul>
        </div>
      )}

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
                  {copied ? "Copied ✓" : item.red_lines.length > 0 ? "Copy anyway" : "Copy"}
                </button>
                {item.open_url && (
                  <a href={item.open_url} target="_blank" rel="noopener noreferrer" className={button}>
                    {item.open_url === item.meta.source_url
                      ? item.item_type === "proposal"
                        ? "Open the job"
                        : item.meta.order_id
                          ? "Open the order"
                          : item.item_type === "reply" && (item.platform === "upwork" || item.platform === "fiverr")
                          ? "Open the conversation"
                          : "Open original"
                      : `Open ${item.platform_label}`}{" "}
                    ↗
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
                {item.item_type === "file_transfer" ? "Open file ↗" : "View post ↗"}
              </a>
            )}
            {waiting && item.kind === "api" && (
              <>
                <button type="button" className={primary} disabled={busy} onClick={() => run("approve")}>
                  {busy && item.can_send ? "Working…" : item.can_send ? (item.item_type === "file_transfer"
                    ? item.platform === "computer" ? "Approve & copy" : item.platform === "google" ? "Approve & save" : "Approve & send"
                    : item.item_type === "update" ? "Approve & update" : onPc(item) ? "Approve & run" : item.platform === "skills" ? "Approve & save" : "Approve & post") : "Approve"}
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
                <button type="button" className={button} disabled={busy || item.platform === "maintenance" || item.item_type === "file_transfer" || (!!desktop && desktop.kind !== "type") || (!!browser && browser.kind !== "fill")}
                  onClick={() => setEditing(desktop?.kind === "type" ? desktop.text : browser?.kind === "fill" ? browser.text : item.text)}>
                  Edit
                </button>
                {item.item_type === "post" && (
                  // Posting times and images are for posts, not proposals, replies or messages.
                  <>
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
                  </>
                )}
                {item.kind === "copy" && (
                  <button
                    type="button"
                    className={button}
                    disabled={busy || item.needs_image}
                    title={item.needs_image ? "Add an image first" : undefined}
                    onClick={() => run("posted")}
                  >
                    {isSent(item) ? "Mark as sent" : "Mark as posted"}
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
