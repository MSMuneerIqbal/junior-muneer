"use client";

import Link from "next/link";
import { Suspense, useDeferredValue, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { BACKEND_URL, fetcher, send } from "@/lib/api";
import { Markdown } from "@/components/chat/Markdown";

type Folder = { id: number; name: string; note_count: number };
type Note = {
  id: number; title: string; subject: string; class_date: string; summary: string; body: string;
  folder_id: number; folder_name: string; revision: string; archived: boolean;
  warnings: string[]; sources: { id: number; filename: string; mime: string; size: number }[];
};
const isNotesKey = (key: unknown) => typeof key === "string" && (key.startsWith("/api/notes") || key === "/api/note-folders");
const field = "min-w-0 w-full rounded-lg border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent";

function EditNote({ note, folders, done }: { note: Note; folders: Folder[]; done: () => void }) {
  const { mutate } = useSWRConfig();
  const [form, setForm] = useState({ title: note.title, subject: note.subject, class_date: note.class_date,
    summary: note.summary, body: note.body, folder_id: note.folder_id });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setError("");
    try {
      await send("PUT", `/api/notes/${note.id}`, { ...form, revision: note.revision });
      await mutate(isNotesKey);
      done();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't save notes"); }
    finally { setBusy(false); }
  }
  return <form onSubmit={save} className="space-y-4">
    <label className="block text-sm">Title<input aria-label="Note title" required maxLength={200} className={`${field} mt-1`} value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></label>
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="text-sm">Folder<select aria-label="Note folder" className={`${field} mt-1`} value={form.folder_id} onChange={(e) => setForm({ ...form, folder_id: Number(e.target.value) })}>{folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select></label>
      <label className="text-sm">Class date<input aria-label="Note class date" type="date" required className={`${field} mt-1`} value={form.class_date} onChange={(e) => setForm({ ...form, class_date: e.target.value })} /></label>
    </div>
    <label className="block text-sm">Course<input aria-label="Note course" maxLength={120} className={`${field} mt-1`} value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} /></label>
    <label className="block text-sm">Summary<textarea aria-label="Note summary" maxLength={1200} rows={3} className={`${field} mt-1`} value={form.summary} onChange={(e) => setForm({ ...form, summary: e.target.value })} /></label>
    <label className="block text-sm">Notes<textarea aria-label="Note text" required rows={18} maxLength={60000} className={`${field} mt-1 font-mono`} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} /></label>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <div className="flex gap-2"><button disabled={busy} className="rounded-lg bg-accent px-4 py-2 text-sm text-white">{busy ? "Saving…" : "Save notes"}</button><button type="button" disabled={busy} onClick={done} className="rounded-lg border border-line px-4 py-2 text-sm">Cancel</button></div>
  </form>;
}

function NoteDetail({ note, folders }: { note: Note; folders: Folder[] }) {
  const { mutate } = useSWRConfig();
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function archive() {
    setBusy(true); setError("");
    try {
      await send("POST", `/api/notes/${note.id}/archive`, { archived: !note.archived, revision: note.revision });
      await mutate(isNotesKey);
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't update notes"); }
    finally { setBusy(false); }
  }
  if (editing) return <EditNote note={note} folders={folders} done={() => setEditing(false)} />;
  return <article aria-label="Saved note" className="min-w-0">
    <p className="text-xs text-muted">{note.folder_name} · {note.class_date}{note.subject ? ` · ${note.subject}` : ""}{note.archived ? " · Archived" : ""}</p>
    <h2 dir="auto" className="mt-2 break-words text-2xl font-semibold">{note.title}</h2>
    <div className="mt-4 flex flex-wrap gap-2 text-sm">
      <button onClick={() => setEditing(true)} className="rounded-lg border border-line px-3 py-1.5">Edit notes</button>
      <a href={`${BACKEND_URL}/api/notes/${note.id}/download`} className="rounded-lg border border-line px-3 py-1.5">Download Markdown</a>
      <button onClick={archive} disabled={busy} className="rounded-lg border border-line px-3 py-1.5 text-muted">{note.archived ? "Restore notes" : "Archive notes"}</button>
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
    <p dir="auto" className="mt-6 text-sm leading-relaxed text-muted">{note.summary}</p>
    <div className="prose-chat mt-5 max-w-none break-words"><Markdown text={note.body} /></div>
    {!!note.warnings.length && <section aria-label="Reading limitations" className="mt-6 rounded-lg border border-line p-3 text-sm"><h3 className="font-medium">Reading limitations</h3><ul className="mt-2 list-disc pl-5">{note.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></section>}
    {!!note.sources.length && <section aria-label="Source material" className="mt-6 border-t border-line pt-4 text-sm"><h3 className="font-medium">Source material kept with these notes</h3><ul className="mt-2 space-y-1 text-muted">{note.sources.map((s) => <li key={s.id}>{s.filename}</li>)}</ul></section>}
  </article>;
}

function NotesLibrary() {
  const params = useSearchParams();
  const { mutate } = useSWRConfig();
  const selected = Number(params.get("id")) || 0;
  const [query, setQuery] = useState("");
  const deferred = useDeferredValue(query);
  const [day, setDay] = useState("");
  const [folder, setFolder] = useState("");
  const [archived, setArchived] = useState(false);
  const [folderName, setFolderName] = useState("");
  const [folderError, setFolderError] = useState("");
  const [folderBusy, setFolderBusy] = useState(false);
  const listKey = `/api/notes?q=${encodeURIComponent(deferred)}&class_date=${day}&archived=${archived}${folder ? `&folder_id=${folder}` : ""}`;
  const { data: notes, error } = useSWR<Omit<Note, "body">[]>(listKey, fetcher, { refreshInterval: 10000 });
  const { data: folders } = useSWR<Folder[]>("/api/note-folders", fetcher, { refreshInterval: 10000 });
  const { data: note, error: detailError } = useSWR<Note>(selected ? `/api/notes/${selected}` : null, fetcher);
  async function createFolder(e: React.FormEvent) {
    e.preventDefault(); setFolderBusy(true); setFolderError("");
    try {
      const ready = await send<Folder>("POST", "/api/note-folders", { name: folderName });
      await mutate("/api/note-folders"); setFolder(String(ready.id)); setFolderName("");
    } catch (e) { setFolderError(e instanceof Error ? e.message : "Couldn't create folder"); }
    finally { setFolderBusy(false); }
  }
  return <main className="h-full overflow-y-auto p-4 sm:p-6">
    <header><h1 className="text-2xl font-semibold">Notes</h1><p className="mt-2 max-w-2xl text-sm text-muted">Your class notes, organized by folder and date. Send Junior your text, photos, slides or documents and ask him to make class notes.</p></header>
    <div className="mt-6 grid gap-6 lg:grid-cols-[minmax(14rem,19rem)_minmax(0,1fr)]">
      <section aria-label="Notes library" className={`${selected ? "hidden lg:block" : ""} min-w-0`}>
        <input aria-label="Search notes" placeholder="Search title, course or notes" className={field} value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="mt-3 grid grid-cols-2 gap-2"><select aria-label="Notes folder filter" className={field} value={folder} onChange={(e) => setFolder(e.target.value)}><option value="">All folders</option>{folders?.map((f) => <option key={f.id} value={f.id}>{f.name} ({f.note_count})</option>)}</select><input aria-label="Filter class date" type="date" className={field} value={day} onChange={(e) => setDay(e.target.value)} /></div>
        <form onSubmit={createFolder} className="mt-3 flex gap-2"><input aria-label="New Notes folder name" placeholder="New folder name" maxLength={80} required className={`${field} min-w-0`} value={folderName} onChange={(e) => setFolderName(e.target.value)} /><button disabled={folderBusy || !folderName.trim()} className="shrink-0 rounded-lg border border-line px-3 text-xs">Create folder</button></form>
        {folderError && <p role="alert" className="mt-2 text-xs text-danger">{folderError}</p>}
        <label className="mt-3 flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Show archived notes</label>
        {error && <p role="alert" className="mt-4 text-sm text-danger">{error.message}</p>}
        {!notes && !error && <p className="mt-4 text-sm text-muted">Loading notes…</p>}
        {notes?.length === 0 && <p className="mt-5 text-sm text-muted">No notes here yet. <Link href="/" className="text-accent underline">Ask Junior to make class notes.</Link></p>}
        <ul className="mt-4 space-y-2">{notes?.map((n) => <li key={n.id}><Link href={`/notes?id=${n.id}`} className={`block rounded-lg border p-3 ${selected === n.id ? "border-accent bg-accent-soft" : "border-line hover:bg-panel-2"}`}><p dir="auto" className="break-words text-sm font-medium">{n.title}</p><p className="mt-1 text-xs text-muted">{n.class_date} · {n.folder_name}</p>{n.subject && <p className="mt-1 text-xs text-muted">{n.subject}</p>}</Link></li>)}</ul>
      </section>
      <section aria-label="Note detail" className="min-w-0 lg:border-l lg:border-line lg:pl-6">
        {selected > 0 && <Link href="/notes" className="mb-5 inline-block text-sm text-muted hover:underline">← Back to notes</Link>}
        {detailError && <p role="alert" className="text-sm text-danger">{detailError.message}</p>}
        {selected > 0 && !note && !detailError && <p className="text-sm text-muted">Loading saved note…</p>}
        {note && selected > 0 && <NoteDetail key={note.revision} note={note} folders={folders ?? []} />}
        {!selected && <p className="hidden py-12 text-center text-sm text-muted lg:block">Choose a note to read or edit it.</p>}
      </section>
    </div>
  </main>;
}

export default function NotesPage() {
  return <Suspense fallback={<p className="p-6 text-sm text-muted">Loading notes…</p>}><NotesLibrary /></Suspense>;
}
