"use client";

import { useState } from "react";
import { Markdown } from "@/components/chat/Markdown";
import { BACKEND_URL, send } from "@/lib/api";
import type { MemoryNote, Step } from "@/lib/types";

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
        <div dir="auto" className="whitespace-pre-wrap">
          {audioId && <span aria-label="voice message">🎙 </span>}
          {text}
        </div>
      </div>
    </div>
  );
}

function StepLine({ step }: { step: Step }) {
  return (
    <li className="flex items-center gap-2 text-sm text-muted">
      <span aria-hidden className={step.status === "running" ? "animate-pulse" : "text-ok"}>
        {step.status === "running" ? "●" : "✓"}
      </span>
      <span>
        {step.label}
        {step.status === "running" ? "…" : ""}
      </span>
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
                <StepLine key={s.id} step={s} />
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

function MemoryNoteLine({ note }: { note: MemoryNote }) {
  const [undone, setUndone] = useState(note.undone ?? false);
  const [error, setError] = useState<string | null>(null);

  async function undo() {
    try {
      await send("DELETE", `/api/memories/${note.id}`);
      setUndone(true);
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

export function AssistantMessage({
  text,
  steps,
  cost,
  notes = [],
  streaming = false,
}: {
  text: string;
  steps: Step[];
  cost?: number;
  notes?: MemoryNote[];
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
      {!streaming && cost !== undefined && <ShowWork steps={steps} cost={cost} />}
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
