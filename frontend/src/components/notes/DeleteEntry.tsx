"use client";
import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { send } from "@/lib/api";

type Entry = { id: number; name: string; revision: string; kind: "file" | "note"; local?: boolean };

export function DeleteEntry({ entry, onDeleted, button = false }: { entry: Entry; onDeleted: () => void; button?: boolean }) {
  const { mutate } = useSWRConfig();
  const [open, setOpen] = useState(false);
  const [target, setTarget] = useState<Entry | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const label = entry.kind === "note" ? "Delete notes" : "Delete file";
  useEffect(() => {
    if (!open) return;
    box.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
    function close(event: MouseEvent | KeyboardEvent) {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) {
        setOpen(false);
        if (event instanceof KeyboardEvent) box.current?.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')?.focus();
      }
    }
    document.addEventListener("mousedown", close); document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);
  useEffect(() => {
    if (target) dialog.current?.showModal(); else dialog.current?.close();
  }, [target]);
  function prepare() { setOpen(false); setTarget(entry); setError(""); }
  async function remove(event: React.FormEvent) {
    event.preventDefault(); if (!target) return;
    setBusy(true); setError("");
    try {
      await send("DELETE", target.kind === "file" ? `/api/library/files/${target.id}` : `/api/notes/${target.id}`, { revision: target.revision });
      setTarget(null); onDeleted();
      await mutate((key: unknown) => typeof key === "string" && (key.startsWith("/api/notes") || key.startsWith("/api/library/files") || key.startsWith("/api/approvals") || key === "/api/note-folders"));
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't delete this item"); }
    finally { setBusy(false); }
  }
  return <div ref={box} className="relative shrink-0">
    {button ? <button type="button" onClick={prepare} className="rounded-lg border border-line px-3 py-2 text-sm text-danger">{label}</button>
      : <button type="button" aria-label={`Options for ${entry.name}`} aria-haspopup="menu" aria-expanded={open} onClick={() => setOpen(!open)} className="flex h-9 w-9 items-center justify-center rounded-lg bg-panel text-xl text-muted hover:bg-panel-2">⋯</button>}
    {open && <div role="menu" aria-label={`Actions for ${entry.name}`} className="absolute right-0 top-full z-20 mt-1 w-40 rounded-xl border border-line bg-panel p-1 shadow-xl"><button role="menuitem" type="button" onClick={prepare} className="w-full rounded-lg px-3 py-2 text-left text-sm text-danger hover:bg-panel-2">{label}</button></div>}
    <dialog ref={dialog} aria-label={label} onCancel={(event) => { if (busy) event.preventDefault(); else setTarget(null); }} className="fixed inset-0 m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl border border-line bg-panel p-6 text-ink shadow-xl backdrop:bg-black/40">
      <form onSubmit={remove} className="space-y-4"><h2 className="text-lg font-semibold">{label}?</h2><p dir="auto" className="break-words text-sm font-medium">{target?.name}</p>
        <p className="text-sm leading-relaxed">{target?.local === false ? "Remove this file from Junior's library. Its Google Drive copy stays available."
          : "Remove this item from Junior and move its stored copy to the Recycle Bin. Copies elsewhere on your PC or Google Drive stay available."}{target?.kind === "note" ? " Original source files are kept." : " Notes made from it are kept. Unsent actions using this file will be cancelled."}</p>
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2"><button type="button" disabled={busy} onClick={() => setTarget(null)} className="rounded-lg border border-line px-3 py-2 text-sm">Cancel</button><button disabled={busy} className="rounded-lg bg-danger px-3 py-2 text-sm text-white">{busy ? "Deleting…" : label}</button></div>
      </form>
    </dialog>
  </div>;
}
