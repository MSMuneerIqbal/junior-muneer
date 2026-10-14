"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";
import { MEMORIES_KEY } from "@/lib/keys";
import type { Memory } from "@/lib/types";

function MemoryRow({ memory, onChange }: { memory: Memory; onChange: () => Promise<unknown> }) {
  const [mode, setMode] = useState<"view" | "edit" | "delete">("view");
  const [text, setText] = useState(memory.content);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setError(null);
    try {
      await action();
      await onChange();
      setMode("view");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  const save = () =>
    text.trim() && text.trim() !== memory.content
      ? run(() => send("PATCH", `/api/memories/${memory.id}`, { content: text.trim() }))
      : setMode("view");

  return (
    <li className="rounded-lg border border-line bg-panel px-4 py-3">
      {mode === "edit" ? (
        <div className="flex flex-col gap-2">
          <textarea
            autoFocus
            dir="auto"
            value={text}
            onChange={(e) => setText(e.target.value)}
            aria-label="Edit memory"
            rows={2}
            className="w-full resize-y rounded-md border border-accent bg-bg px-3 py-2 outline-none"
          />
          <div className="flex gap-2 text-sm">
            <button onClick={save} className="rounded-md bg-accent px-3 py-1 text-accent-fg">
              Save
            </button>
            <button
              onClick={() => {
                setText(memory.content);
                setMode("view");
              }}
              className="rounded-md px-3 py-1 hover:bg-panel-2"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-start gap-3">
          <p dir="auto" className="flex-1">
            {memory.content}
          </p>
          {mode === "delete" ? (
            <div className="flex items-center gap-2 text-sm">
              <span>Delete?</span>
              <button
                onClick={() => run(() => send("DELETE", `/api/memories/${memory.id}`))}
                className="rounded-md bg-danger px-2 py-1 text-white"
              >
                Delete
              </button>
              <button onClick={() => setMode("view")} className="rounded-md px-2 py-1 hover:bg-panel-2">
                Cancel
              </button>
            </div>
          ) : (
            <div className="flex gap-1 text-sm">
              <button
                onClick={() => setMode("edit")}
                className="rounded-md px-2 py-1 text-muted hover:bg-panel-2 hover:text-ink"
                aria-label={`Edit: ${memory.content}`}
              >
                Edit
              </button>
              <button
                onClick={() => setMode("delete")}
                className="rounded-md px-2 py-1 text-muted hover:bg-danger-soft hover:text-danger"
                aria-label={`Delete: ${memory.content}`}
              >
                Delete
              </button>
            </div>
          )}
        </div>
      )}
      <p className="mt-1 text-xs text-muted">
        {memory.source_message_id ? "Saved from your chat" : "Added by you"} ·{" "}
        {new Date(memory.updated_at).toLocaleDateString()}
      </p>
      {error && <p className="mt-1 text-sm text-danger">{error}</p>}
    </li>
  );
}

export default function MemoryPage() {
  const { data, error, mutate } = useSWR<Memory[]>(MEMORIES_KEY, fetcher);
  const [text, setText] = useState("");
  const [addError, setAddError] = useState<string | null>(null);

  async function add() {
    if (!text.trim()) return;
    setAddError(null);
    try {
      await send("POST", MEMORIES_KEY, { content: text.trim() });
      setText("");
      await mutate();
    } catch (e) {
      setAddError(e instanceof Error ? e.message : "Failed");
    }
  }

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-3xl flex-col gap-5 px-4 py-6 sm:px-6">
        <header>
          <h1 className="text-2xl font-semibold">Memory</h1>
          <p className="mt-1 text-muted">
            What Junior Muneer remembers about you. He saves things only from your own messages;
            you can add, edit or delete anything here.
          </p>
        </header>

        <div className="flex gap-2">
          <input
            dir="auto"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="Add something, e.g. “I prefer short proposals”"
            aria-label="New memory"
            className="flex-1 rounded-lg border border-line bg-panel px-3 py-2 outline-none focus:border-accent"
          />
          <button
            onClick={add}
            disabled={!text.trim()}
            className="rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-fg disabled:opacity-40"
          >
            Add
          </button>
        </div>
        {addError && <p className="text-sm text-danger">{addError}</p>}

        {error && <p className="text-danger">Couldn&apos;t load memories: {error.message}</p>}
        {data && !data.length && (
          <p className="rounded-lg border border-dashed border-line px-4 py-8 text-center text-muted">
            Nothing yet. Tell him about yourself in a chat (“my rate is $25/hr”), or add it above.
          </p>
        )}
        {data && data.length > 0 && (
          <>
            <p className="text-sm text-muted">{data.length} memories</p>
            <ul className="flex flex-col gap-2">
              {data.map((m) => (
                <MemoryRow key={`${m.id}-${m.updated_at}`} memory={m} onChange={() => mutate()} />
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}
