"use client";

import { useEffect, useRef, useState } from "react";
import { useSWRConfig } from "swr";
import { send } from "@/lib/api";

export type NotesFolder = { id: number; name: string; note_count: number; file_count: number;
  total_notes: number; total_files: number; revision: string };

export function FolderActions({ folder, onDeleted }: { folder: NotesFolder; onDeleted: () => void }) {
  const { mutate } = useSWRConfig();
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState<"rename" | "delete" | null>(null);
  const [target, setTarget] = useState(folder);
  const box = useRef<HTMLDivElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState(folder.name);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    box.current?.querySelector<HTMLButtonElement>('[role="menuitem"]')?.focus();
    function close(event: MouseEvent | KeyboardEvent) {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !box.current?.contains(event.target as Node)) {
        setOpen(false);
        if (event instanceof KeyboardEvent) box.current?.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')?.focus();
      }
    }
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => { document.removeEventListener("mousedown", close); document.removeEventListener("keydown", close); };
  }, [open]);

  useEffect(() => {
    if (action) dialog.current?.showModal();
    else dialog.current?.close();
  }, [action]);

  function choose(next: "rename" | "delete") {
    setOpen(false); setTarget(folder); setName(folder.name); setError(""); setAction(next);
  }
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      await send(action === "rename" ? "PUT" : "DELETE", `/api/note-folders/${target.id}`,
        { revision: target.revision, ...(action === "rename" ? { name } : {}) });
      setAction(null);
      if (action === "delete") onDeleted();
      await mutate((key: unknown) => typeof key === "string" && (key.startsWith("/api/notes") || key.startsWith("/api/library/files") || key === "/api/note-folders"));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't update folder");
      await mutate("/api/note-folders");
    } finally { setBusy(false); }
  }
  const menuItem = "block w-full rounded-lg px-3 py-2 text-left text-sm hover:bg-panel-2 focus:bg-panel-2 focus:outline-none";
  return <div ref={box} className="relative shrink-0">
    <button type="button" aria-label={`Folder options for ${folder.name}`} aria-haspopup="menu" aria-expanded={open}
      onClick={() => setOpen(!open)} className="flex h-9 w-9 items-center justify-center rounded-lg text-xl text-muted hover:bg-panel-2 hover:text-ink">⋯</button>
    {open && <div role="menu" aria-label={`Actions for ${folder.name}`} className="absolute right-0 top-full z-20 mt-1 w-44 rounded-xl border border-line bg-panel p-1 shadow-xl"
      onKeyDown={(event) => {
        const items = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="menuitem"]'));
        const index = items.indexOf(document.activeElement as HTMLButtonElement);
        if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          items[event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowUp" ? -1 : 1) + items.length) % items.length]?.focus();
        }
      }}>
      <button role="menuitem" type="button" className={menuItem} onClick={() => choose("rename")}>Rename folder</button>
      <button role="menuitem" type="button" className={`${menuItem} text-danger`} onClick={() => choose("delete")}>Delete folder</button>
    </div>}
    <dialog ref={dialog} aria-label={action === "rename" ? "Rename folder" : "Delete folder"} onCancel={(event) => { if (busy) event.preventDefault(); else setAction(null); }}
      className="fixed inset-0 m-auto w-[calc(100%-2rem)] max-w-md rounded-2xl border border-line bg-panel p-6 text-ink shadow-xl backdrop:bg-black/40">
      <form onSubmit={submit} className="space-y-4">
        <h2 className="text-lg font-semibold">{action === "rename" ? "Rename folder" : "Delete folder?"}</h2>
        {action === "rename" ? <label className="block text-sm">Folder name<input autoFocus aria-label="Folder name" required maxLength={80} value={name}
          onChange={(event) => setName(event.target.value)} className="mt-2 w-full rounded-lg border border-line bg-bg px-3 py-2 outline-none focus:border-accent" /></label>
          : <p className="break-words text-sm leading-relaxed">Remove “{target.name}” from Notes? Its {target.total_files} files and {target.total_notes} notes, including archived items, will be kept in {target.name.toLowerCase() === "unfiled" ? "Unfiled (2)" : "Unfiled"}.</p>}
        {error && <p role="alert" className="text-sm text-danger">{error}</p>}
        <div className="flex justify-end gap-2">
          <button type="button" disabled={busy} onClick={() => setAction(null)} className="rounded-lg border border-line px-3 py-2 text-sm">Cancel</button>
          <button disabled={busy || (action === "rename" && !name.trim())} className={`rounded-lg px-3 py-2 text-sm ${action === "delete" ? "bg-danger text-white" : "bg-accent text-accent-fg"}`}>{busy ? "Saving…" : action === "rename" ? "Save changes" : "Delete folder"}</button>
        </div>
      </form>
    </dialog>
  </div>;
}
