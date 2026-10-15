"use client";

import { useState, useSyncExternalStore } from "react";
import { Markdown } from "@/components/chat/Markdown";
import { MicIcon } from "@/components/icons";
import { BACKEND_URL, send } from "@/lib/api";
import { urduClass } from "@/lib/urdu";
import { speakMessage, stopSpeaking, usePlayer } from "@/lib/player";
import { ApprovalCard } from "@/components/approvals/ApprovalCard";
import type { ApprovalItem, MemoryNote, Step } from "@/lib/types";

export function UserMessage({ text, audioId }: { text: string; audioId?: string | null }) {
  return (
    <div className="flex justify-end">
      <div className="flex max-w-[85%] flex-col items-end gap-1.5 rounded-2xl rounded-br-md bg-user px-4 py-2.5">
        {audioId && (
          <audio
            controls
            preload="none"
            src={`${BACKEND_URL}/api/audio/${audioId}`}
            className="h-8 max-w-full"
            aria-label="Your voice message"
          />
        )}
        <div dir="auto" className={`whitespace-pre-wrap ${urduClass(text)}`}>
          {audioId && (
            <MicIcon
              className="mx-1 inline h-4 w-4 align-[-2px] text-muted"
              title="Voice message"
            />
          )}
          {text}
        </div>
      </div>
    </div>
  );
}

function StepLine({ step, full = false }: { step: Step; full?: boolean }) {
  const team = step.kind === "team";
  return (
    <li className={`flex flex-col text-sm text-muted ${team ? "pl-5" : ""}`}>
      <span className="flex items-center gap-2">
        <span aria-hidden className={step.status === "running" ? "animate-pulse" : "text-ok"}>
          {step.status === "running" ? "●" : team ? "↳" : "✓"}
        </span>
        <span>
          {step.label}
          {step.status === "running" ? "…" : ""}
        </span>
      </span>
      {full && step.notes && step.notes.length > 0 && (
        <ul className="mt-0.5 ml-6 list-disc text-xs">
          {step.notes.map((n, i) => (
            <li key={i}>{n}</li>
          ))}
        </ul>
      )}
      {full && step.detail && (
        <details className="mt-0.5 ml-6 text-xs">
          <summary className="cursor-pointer hover:text-ink">See the text</summary>
          <p dir="auto" className={`mt-1 whitespace-pre-wrap rounded-md bg-panel px-2 py-1.5 text-ink ${urduClass(step.detail)}`}>
            {step.detail}
          </p>
        </details>
      )}
    </li>
  );
}

function ShowWork({ steps, cost }: { steps: Step[]; cost: number }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="mt-2 text-sm">
      <button
        onClick={() => setOpen(!open)}
        className="text-muted hover:text-ink"
        aria-expanded={open}
      >
        {open ? "▾" : "▸"} Show work
      </button>
      {open && (
        <div className="mt-1.5 rounded-lg border border-line bg-panel-2 px-3 py-2">
          {steps.length ? (
            <ul className="flex flex-col gap-1">
              {steps.map((s) => (
                <StepLine key={s.id} step={s} full />
              ))}
            </ul>
          ) : (
            <p className="text-muted">Answered directly, no tools used.</p>
          )}
          <p className="mt-1.5 text-muted">Cost: ${cost.toFixed(4)}</p>
        </div>
      )}
    </div>
  );
}

// Memories undone this session: a small shared store, because the note under a live
// answer is replaced by the saved answer's note when the answer finishes (even while
// an Undo is still being sent).
const undoneMemories = new Set<number>();
const undoneListeners = new Set<() => void>();
function markUndone(id: number) {
  undoneMemories.add(id);
  undoneListeners.forEach((l) => l());
}
function subscribeUndone(listener: () => void) {
  undoneListeners.add(listener);
  return () => undoneListeners.delete(listener);
}

function MemoryNoteLine({ note }: { note: MemoryNote }) {
  const undone = useSyncExternalStore(
    subscribeUndone,
    () => Boolean(note.undone) || undoneMemories.has(note.id),
    () => Boolean(note.undone),
  );
  const [error, setError] = useState<string | null>(null);

  async function undo() {
    try {
      await send("DELETE", `/api/memories/${note.id}`);
      markUndone(note.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Undo failed");
    }
  }

  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-2 rounded-lg bg-accent-soft px-3 py-1.5 text-sm">
      <span aria-hidden>🧠</span>
      <span dir="auto" className={undone ? "line-through opacity-60" : ""}>
        {note.action === "saved" ? "Memory updated" : "Memory removed"}: {note.content}
      </span>
      {note.action === "saved" &&
        (undone ? (
          <span className="text-muted">Undone</span>
        ) : (
          <button onClick={undo} className="font-medium text-accent hover:underline">
            Undo
          </button>
        ))}
      {error && <span className="text-danger">{error}</span>}
    </div>
  );
}

function ListenButton({ messageId }: { messageId: number }) {
  const player = usePlayer();
  const mine = player.messageId === messageId;
  const label = mine && player.status === "playing" ? "■ Stop" : mine && player.status === "loading" ? "Loading…" : "🔊 Listen";
  return (
    <span className="flex items-center gap-2">
      <button
        onClick={() => (mine && player.status !== "idle" ? stopSpeaking() : speakMessage(messageId))}
        className="text-muted hover:text-ink"
        aria-label={mine && player.status === "playing" ? "Stop reading aloud" : "Read aloud"}
      >
        {label}
      </button>
      {mine && player.error && <span className="text-xs text-warn">{player.error}</span>}
    </span>
  );
}

export function AssistantMessage({
  messageId,
  text,
  steps,
  cost,
  notes = [],
  approvals = [],
  streaming = false,
}: {
  messageId?: number;
  text: string;
  steps: Step[];
  cost?: number;
  notes?: MemoryNote[];
  approvals?: ApprovalItem[];
  streaming?: boolean;
}) {
  return (
    <div className="flex flex-col">
      <div className="mb-1 text-xs font-medium text-muted">Junior Muneer</div>
      {streaming && steps.length > 0 && (
        <ul className="mb-2 flex flex-col gap-1">
          {steps.map((s) => (
            <StepLine key={s.id} step={s} />
          ))}
        </ul>
      )}
      <div className={`prose-chat ${streaming ? "stream-cursor" : ""}`}>
        {text ? <Markdown text={text} /> : streaming && !steps.length ? <span className="text-muted">Thinking</span> : null}
      </div>
      {notes.map((n) => (
        <MemoryNoteLine key={`${n.action}-${n.id}`} note={n} />
      ))}
      {approvals.length > 0 && (
        <div className="mt-3 flex flex-col gap-3">
          {approvals.map((a) => (
            <ApprovalCard key={a.id} item={a} />
          ))}
        </div>
      )}
      {!streaming && cost !== undefined && (
        <div className="flex flex-wrap items-start gap-x-4">
          <ShowWork steps={steps} cost={cost} />
          {messageId !== undefined && text && (
            <div className="mt-2 text-sm">
              <ListenButton messageId={messageId} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ErrorNotice({ message }: { message: string }) {
  return (
    <div role="alert" className="rounded-lg bg-danger-soft px-4 py-2.5 text-sm text-danger">
      {message}
    </div>
  );
}
