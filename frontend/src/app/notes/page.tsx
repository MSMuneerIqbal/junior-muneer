"use client";

import Link from "next/link";
import { Suspense, useDeferredValue, useLayoutEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR, { useSWRConfig } from "swr";
import { BACKEND_URL, fetcher, send } from "@/lib/api";
import { Markdown } from "@/components/chat/Markdown";
import { ApprovalCard } from "@/components/approvals/ApprovalCard";
import type { ApprovalItem } from "@/lib/types";
import { FolderActions, type NotesFolder } from "@/components/notes/FolderActions";
import { DeleteEntry } from "@/components/notes/DeleteEntry";

type Folder = NotesFolder;
type SavedFile = { id: number; filename: string; mime: string; size: number; folder_id: number; folder_name: string;
  archived: boolean; drive_link: string; created_at: string; revision: string; local: boolean };
type Note = {
  id: number; title: string; subject: string; class_date: string; summary: string; body: string;
  folder_id: number; folder_name: string; revision: string; archived: boolean;
  warnings: string[]; sources: { id: number; filename: string; mime: string; size: number }[];
};
const isNotesKey = (key: unknown) => typeof key === "string" && (key.startsWith("/api/notes") || key.startsWith("/api/library/files") || key === "/api/note-folders");
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

function NoteDetail({ note, folders, onDeleted }: { note: Note; folders: Folder[]; onDeleted: () => void }) {
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
      <DeleteEntry button entry={{ id: note.id, name: note.title, revision: note.revision, kind: "note" }} onDeleted={onDeleted} />
    </div>
    {error && <p role="alert" className="mt-3 text-sm text-danger">{error}</p>}
    <p dir="auto" className="mt-6 text-sm leading-relaxed text-muted">{note.summary}</p>
    <div className="prose-chat mt-5 max-w-none break-words"><Markdown text={note.body} /></div>
    {!!note.warnings.length && <section aria-label="Reading limitations" className="mt-6 rounded-lg border border-line p-3 text-sm"><h3 className="font-medium">Reading limitations</h3><ul className="mt-2 list-disc pl-5">{note.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul></section>}
    {!!note.sources.length && <section aria-label="Source material" className="mt-6 border-t border-line pt-4 text-sm"><h3 className="font-medium">Source material kept with these notes</h3><ul className="mt-2 space-y-1 text-muted">{note.sources.map((s) => <li key={s.id}>{s.filename}</li>)}</ul></section>}
  </article>;
}

function fileType(file: SavedFile) {
  if (file.mime.startsWith("image/")) return "Image";
  if (file.mime.includes("google-apps.document")) return "Google Doc";
  if (file.mime.includes("google-apps.spreadsheet")) return "Google Sheet";
  return file.filename.split(".").pop()?.toUpperCase().slice(0, 8) || "File";
}

function FileCover({ file }: { file: SavedFile }) {
  return <div className="flex aspect-[4/3] items-center justify-center overflow-hidden rounded-lg bg-panel-2">
    {["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.mime) && file.local
      // eslint-disable-next-line @next/next/no-img-element -- private original served by the backend
      ? <img alt={file.filename} src={`${BACKEND_URL}/api/library/files/${file.id}/inline`} loading="lazy" className="h-full w-full object-cover" />
      : <div className="rounded-lg border border-line bg-bg px-5 py-6 text-center"><span className="text-sm font-semibold tracking-wide text-accent">{fileType(file)}</span><div className="mt-3 space-y-1.5"><div className="h-1 w-14 rounded bg-line" /><div className="h-1 w-11 rounded bg-line" /><div className="h-1 w-14 rounded bg-line" /></div></div>}
  </div>;
}

function FileDetail({ file, folders, approval, onPrepared, onDeleted }: { file: SavedFile; folders: Folder[]; approval?: ApprovalItem; onPrepared: (item: ApprovalItem) => void; onDeleted: () => void }) {
  const { mutate } = useSWRConfig();
  const [name, setName] = useState(file.filename);
  const [folder, setFolder] = useState(file.folder_id);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const image = ["image/jpeg", "image/png", "image/webp", "image/gif"].includes(file.mime);
  const [driveFolder, setDriveFolder] = useState("");
  const [access, setAccess] = useState(file.drive_link ? "reader" : "");
  const pdf = file.mime === "application/pdf";
  const { data: preview } = useSWR<{ text: string; message: string }>(file.local && !image && !pdf ? `/api/library/files/${file.id}/preview` : null, fetcher);
  async function save(archived = file.archived) {
    setBusy(true); setError("");
    try { await send("PUT", `/api/library/files/${file.id}`, { filename: name, folder_id: folder, archived, revision: file.revision }); await mutate(isNotesKey); }
    catch (error) { setError(error instanceof Error ? error.message : "Couldn't update file"); }
    finally { setBusy(false); }
  }
  async function drive() {
    setBusy(true); setError("");
    try { const result = await send<ApprovalItem>("POST", `/api/library/files/${file.id}/drive`, { folder: driveFolder, access }); onPrepared(result); await mutate(isNotesKey); }
    catch (error) { setError(error instanceof Error ? error.message : "Couldn't prepare Drive action"); }
    finally { setBusy(false); }
  }
  return <article aria-label="Saved file" className="min-w-0 space-y-5">
    <div><p className="text-xs text-muted">{file.folder_name} · {file.created_at.slice(0, 10)} · {fileType(file)}{file.archived ? " · Archived" : ""}</p><h2 dir="auto" className="mt-2 break-words text-2xl font-semibold">{file.filename}</h2></div>
    <div className="flex flex-wrap gap-2 text-sm"><a className="rounded-lg border border-line px-3 py-2" href={`${BACKEND_URL}/api/library/files/${file.id}/download`}>Download original</a>{file.drive_link && <a className="rounded-lg border border-line px-3 py-2" href={file.drive_link} target="_blank" rel="noopener noreferrer">Open in Drive</a>}<button disabled={busy} onClick={() => save(!file.archived)} className="rounded-lg border border-line px-3 py-2">{file.archived ? "Restore file" : "Archive file"}</button></div>
    {error && <p role="alert" className="text-sm text-danger">{error}</p>}
    <DeleteEntry button entry={{ id: file.id, name: file.filename, revision: file.revision, kind: "file", local: file.local }} onDeleted={onDeleted} />
    {image && file.local &&
      // eslint-disable-next-line @next/next/no-img-element -- selected private file, no AI analysis
      <img alt={file.filename} src={`${BACKEND_URL}/api/library/files/${file.id}/inline`} className="max-h-[32rem] max-w-full rounded-xl object-contain" />}
    {pdf && file.local && <iframe title="PDF preview" src={`${BACKEND_URL}/api/library/files/${file.id}/inline`} className="h-[65vh] w-full rounded-xl border border-line" />}
    {preview?.text && <div aria-label="File text preview" className="prose-chat max-h-[65vh] overflow-auto rounded-xl border border-line p-4"><Markdown text={preview.text} /></div>}
    {preview?.message && <p className="text-sm text-muted">{preview.message}</p>}
    {!file.local && <p className="text-sm text-muted">This file is stored in Google Drive. Open its link to view or edit it.</p>}
    <form className="grid gap-3 rounded-xl border border-line p-4 sm:grid-cols-2" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <label className="text-sm">Filename<input aria-label="Saved filename" required value={name} onChange={(event) => setName(event.target.value)} className={`${field} mt-1`} /></label>
      <label className="text-sm">Folder<select aria-label="Saved file folder" value={folder} onChange={(event) => setFolder(Number(event.target.value))} className={`${field} mt-1`}>{folders.map((f) => <option key={f.id} value={f.id}>{f.name}</option>)}</select></label>
      <button disabled={busy} className="justify-self-start rounded-lg bg-accent px-4 py-2 text-sm text-accent-fg">Save file details</button>
    </form>
    <section aria-label="Drive sharing" className="space-y-3 rounded-xl border border-line p-4"><h3 className="text-sm font-semibold">Google Drive</h3><label className="block text-sm">Drive folder<input aria-label="Drive destination folder" value={driveFolder} onChange={(event) => setDriveFolder(event.target.value)} placeholder={file.drive_link ? "Leave empty to update this link" : "My Drive, or a folder path"} className={`${field} mt-1`} /></label><label className="block text-sm">Link access<select aria-label="File Drive access" value={access} onChange={(event) => setAccess(event.target.value)} className={`${field} mt-1`}>{!file.drive_link && <option value="">Use my Drive sharing setting</option>}<option value="reader">Anyone with the link can view</option><option value="writer">Anyone with the link can edit</option>{!file.drive_link && <option value="private">Private</option>}</select></label>{access === "writer" && <p className="text-xs text-muted">Anyone who gets this link will be able to change the file.</p>}<button disabled={busy} onClick={drive} className="rounded-lg bg-accent px-3 py-2 text-sm text-accent-fg">{file.drive_link ? "Update Drive sharing" : "Save to Drive"}</button></section>
    {approval && <ApprovalCard key={approval.id} item={approval} />}
  </article>;
}

function NotesLibrary() {
  const params = useSearchParams();
  const { mutate } = useSWRConfig();
  const main = useRef<HTMLElement>(null);
  const scrolls = useRef(new Map<string, number>());
  const restore = useRef<{ key: string; top: number } | null>(null);
  const viewKey = params.toString();
  function hrefFor(updates: Record<string, string | number | null>, search = params.toString()) {
    const next = new URLSearchParams(search);
    for (const [key, value] of Object.entries(updates)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, String(value));
    }
    return `/notes${next.size ? `?${next}` : ""}`;
  }
  function navigate(updates: Record<string, string | number | null>, replace = false) {
    scrolls.current.set(viewKey, main.current?.scrollTop ?? 0);
    const href = hrefFor(updates, window.location.search);
    if (href === window.location.pathname + window.location.search) return;
    if (replace) window.history.replaceState({ notesPrevious: window.history.state?.notesPrevious }, "", href);
    else window.history.pushState({ notesPrevious: window.location.pathname + window.location.search }, "", href);
  }
  function openDetail(event: React.MouseEvent, update: Record<string, number | null>) {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button !== 0) return;
    event.preventDefault(); navigate(update);
  }
  const selected = Number(params.get("id")) || 0;
  const selectedFile = Number(params.get("file")) || 0;
  const hasSelection = selected > 0 || selectedFile > 0;
  const query = params.get("q") || "";
  const setQuery = (value: string) => navigate({ q: value }, true);
  const deferred = useDeferredValue(query);
  const day = params.get("date") || "";
  const setDay = (value: string) => navigate({ date: value });
  const folder = params.get("folder") || "";
  const setFolder = (value: string) => navigate({ folder: value, id: null, file: null });
  const archived = params.get("archived") === "true";
  const setArchived = (value: boolean) => navigate({ archived: value ? "true" : null });
  const [folderName, setFolderName] = useState("");
  const [folderError, setFolderError] = useState("");
  const [folderBusy, setFolderBusy] = useState(false);
  const [uploadBusy, setUploadBusy] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const limit = Math.max(200, Math.min(1000, Number(params.get("limit")) || 200));
  const setLimit = (value: number) => navigate({ limit: value }, true);
  const [driveApprovals, setDriveApprovals] = useState<Record<number, ApprovalItem>>({});
  const listKey = `/api/notes?q=${encodeURIComponent(deferred)}&class_date=${day}&archived=${archived}${folder ? `&folder_id=${folder}` : ""}`;
  const { data: notes, error } = useSWR<Omit<Note, "body">[]>(listKey, fetcher, { refreshInterval: 10000 });
  const { data: folders } = useSWR<Folder[]>("/api/note-folders", fetcher, { refreshInterval: 10000 });
  const { data: note, error: detailError } = useSWR<Note>(selected ? `/api/notes/${selected}` : null, fetcher);
  const { data: savedFiles, error: filesError } = useSWR<SavedFile[]>(`/api/library/files?q=${encodeURIComponent(deferred)}&class_date=${day}&archived=${archived}&limit=${limit}${folder ? `&folder_id=${folder}` : ""}`, fetcher, { refreshInterval: 10000 });
  const { data: savedFile, error: fileError } = useSWR<SavedFile>(selectedFile ? `/api/library/files/${selectedFile}` : null, fetcher);
  const currentFolder = folders?.find((f) => String(f.id) === folder);
  const ready = hasSelection ? !!(selected ? note || detailError : savedFile || fileError) : !!(notes && savedFiles);
  useLayoutEffect(() => {
    restore.current = { key: viewKey, top: scrolls.current.get(viewKey) ?? 0 };
  }, [viewKey]);
  useLayoutEffect(() => {
    if (ready && restore.current?.key === viewKey && main.current) {
      main.current.scrollTop = restore.current.top;
      restore.current = null;
    }
  }, [viewKey, ready]);
  function back() {
    const previous = window.history.state?.notesPrevious;
    if (typeof previous === "string" && /^\/notes(?:\?|$)/.test(previous)) {
      scrolls.current.set(viewKey, main.current?.scrollTop ?? 0);
      window.history.back();
    } else if (hasSelection) {
      navigate({ id: null, file: null, folder: folder || savedFile?.folder_id || note?.folder_id || null }, true);
    } else if (folder || query || day || archived) navigate({ folder: null, q: null, date: null, archived: null }, true);
    else window.history.back();
  }
  function folderDeleted(number: number) {
    if (folder === String(number) || note?.folder_id === number || savedFile?.folder_id === number) {
      navigate({ folder: null, id: null, file: null }, true);
    }
  }
  function entryDeleted(kind: "file" | "note", number: number) {
    if ((kind === "file" && selectedFile === number) || (kind === "note" && selected === number)) {
      navigate({ file: null, id: null, folder: folder || (kind === "file" ? savedFile?.folder_id : note?.folder_id) || null }, true);
    }
  }
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setUploadBusy(true); setUploadError("");
    try {
      for (const file of Array.from(files)) {
        const body = new FormData(); body.append("file", file); if (folder) body.append("folder_id", folder);
        const result = await fetch(`${BACKEND_URL}/api/files`, { method: "POST", body });
        if (!result.ok) { const error = await result.json(); throw new Error(error.detail || "Upload failed"); }
      }
      await mutate(isNotesKey);
    } catch (error) { setUploadError(error instanceof Error ? error.message : "Couldn't upload files"); }
    finally { setUploadBusy(false); }
  }
  async function createFolder(e: React.FormEvent) {
    e.preventDefault(); setFolderBusy(true); setFolderError("");
    try {
      const ready = await send<Folder>("POST", "/api/note-folders", { name: folderName });
      await mutate("/api/note-folders"); setFolder(String(ready.id)); setFolderName("");
    } catch (e) { setFolderError(e instanceof Error ? e.message : "Couldn't create folder"); }
    finally { setFolderBusy(false); }
  }
  return <section aria-label="Notes browser" ref={main} onScroll={() => { if (!restore.current) scrolls.current.set(viewKey, main.current?.scrollTop ?? 0); }} className="h-full overflow-y-auto p-4 sm:p-6">
    <button type="button" aria-label="Back to previous view" onClick={back} className="mb-4 rounded-lg border border-line px-3 py-2 text-sm hover:bg-panel-2">← Back</button>
    <header className="flex flex-wrap items-start justify-between gap-4"><div><h1 className="text-2xl font-semibold">Notes</h1><p className="mt-2 max-w-2xl text-sm text-muted">Your folders, original files and class notes. Upload and save files here without AI reading.</p></div><label className="cursor-pointer rounded-lg bg-accent px-4 py-2 text-sm font-medium text-accent-fg">{uploadBusy ? "Uploading…" : "Upload files"}<input aria-label="Upload library files" type="file" multiple disabled={uploadBusy} className="sr-only" onChange={(event) => { void upload(event.target.files); event.target.value = ""; }} /></label></header>
    {uploadError && <p role="alert" className="mt-3 text-sm text-danger">{uploadError}</p>}
    <div className={`mt-6 grid gap-6 ${hasSelection ? "lg:grid-cols-[minmax(14rem,19rem)_minmax(0,1fr)]" : ""}`}>
      <section aria-label="Notes library" className={`${hasSelection ? "hidden lg:block" : ""} min-w-0`}>
        <input aria-label="Search notes" placeholder="Search title, course or notes" className={field} value={query} onChange={(e) => setQuery(e.target.value)} />
        <div className="mt-3 grid grid-cols-2 gap-2"><select aria-label="Notes folder filter" className={field} value={folder} onChange={(e) => setFolder(e.target.value)}><option value="">All folders</option>{folders?.map((f) => <option key={f.id} value={f.id}>{f.name} ({f.note_count + f.file_count})</option>)}</select><input aria-label="Filter class date" type="date" className={field} value={day} onChange={(e) => setDay(e.target.value)} /></div>
        <form onSubmit={createFolder} className="mt-3 flex gap-2"><input aria-label="New Notes folder name" placeholder="New folder name" maxLength={80} required className={`${field} min-w-0`} value={folderName} onChange={(e) => setFolderName(e.target.value)} /><button disabled={folderBusy || !folderName.trim()} className="shrink-0 rounded-lg border border-line px-3 text-xs">Create folder</button></form>
        {folderError && <p role="alert" className="mt-2 text-xs text-danger">{folderError}</p>}
        {folder ? <div className="mt-5 flex flex-wrap items-center gap-2 text-sm"><button onClick={() => setFolder("")} className="text-accent hover:underline">All folders</button><span className="text-muted">/</span><span dir="auto" className="min-w-0 flex-1 break-words font-medium">{currentFolder?.name || "Folder unavailable"}</span>{currentFolder && <FolderActions folder={currentFolder} onDeleted={() => folderDeleted(currentFolder.id)} />}</div> : <section aria-label="Saved folders" className="mt-6"><h2 className="text-sm font-semibold">Folders</h2><div className={`mt-3 grid gap-3 ${hasSelection ? "grid-cols-2" : "grid-cols-2 sm:grid-cols-3 xl:grid-cols-4"}`}>
          <button onClick={() => setFolder("")} className={`rounded-xl border p-4 text-left ${!folder ? "border-accent bg-accent-soft" : "border-line bg-panel"}`}><span className="block text-xl text-accent">▤</span><span className="mt-2 block text-sm font-medium">All files and notes</span></button>
          {folders?.map((f) => <div key={f.id} className="relative min-w-0 rounded-xl border border-line bg-panel hover:bg-panel-2"><div className="absolute right-1 top-1"><FolderActions folder={f} onDeleted={() => folderDeleted(f.id)} /></div><button aria-label={`Open folder ${f.name}`} onClick={() => setFolder(String(f.id))} className="h-full w-full min-w-0 p-4 text-left"><svg viewBox="0 0 24 24" className="h-7 w-7 text-accent" fill="none" stroke="currentColor" strokeWidth="1.6"><path d="M3 7V5a1 1 0 0 1 1-1h6l2 3h8a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7Z" /></svg><span dir="auto" className="mt-2 block break-words text-sm font-medium">{f.name}</span><span className="mt-1 block text-xs text-muted">{f.file_count} files · {f.note_count} notes</span></button></div>)}
        </div></section>}
        <label className="mt-3 flex items-center gap-2 text-sm text-muted"><input type="checkbox" checked={archived} onChange={(e) => setArchived(e.target.checked)} />Show archived notes</label>
        {error && <p role="alert" className="mt-4 text-sm text-danger">{error.message}</p>}
        {!notes && !error && <p className="mt-4 text-sm text-muted">Loading notes…</p>}
        {filesError && <p role="alert" className="mt-3 text-sm text-danger">{filesError.message}</p>}
        {notes?.length === 0 && savedFiles?.length === 0 && <p className="mt-5 text-sm text-muted">Nothing here yet. Upload a file or <Link href="/" className="text-accent underline">ask Junior to make class notes.</Link></p>}
        <h2 className="mt-6 text-sm font-semibold">Files and notes</h2>
        <ul aria-label="File gallery" className={`mt-3 grid gap-3 ${hasSelection ? "grid-cols-1" : "grid-cols-2 sm:grid-cols-3 xl:grid-cols-4"}`}>
          {notes?.map((n) => <li key={`note-${n.id}`} className="relative"><div className="absolute right-3 top-3 z-10"><DeleteEntry entry={{ id: n.id, name: n.title, revision: n.revision, kind: "note" }} onDeleted={() => entryDeleted("note", n.id)} /></div><Link href={hrefFor({ id: n.id, file: null })} onClick={(event) => openDetail(event, { id: n.id, file: null })} className={`block h-full rounded-xl border p-3 ${selected === n.id ? "border-accent bg-accent-soft" : "border-line bg-panel hover:bg-panel-2"}`}><div className="flex aspect-[4/3] items-center justify-center rounded-lg bg-accent-soft text-sm font-semibold text-accent">MD · Class notes</div><p dir="auto" className="mt-3 break-words text-sm font-medium">{n.title}</p><p className="mt-1 text-xs text-muted">{n.class_date} · {n.folder_name}</p>{n.subject && <p className="mt-1 text-xs text-muted">{n.subject}</p>}</Link></li>)}
          {savedFiles?.map((f) => <li key={`file-${f.id}`} className="relative"><div className="absolute right-3 top-3 z-10"><DeleteEntry entry={{ id: f.id, name: f.filename, revision: f.revision, kind: "file", local: f.local }} onDeleted={() => entryDeleted("file", f.id)} /></div><Link href={hrefFor({ file: f.id, id: null })} onClick={(event) => openDetail(event, { file: f.id, id: null })} aria-label={`Open file ${f.filename}`} className={`block h-full rounded-xl border p-3 ${selectedFile === f.id ? "border-accent bg-accent-soft" : "border-line bg-panel hover:bg-panel-2"}`}><FileCover file={f} /><p dir="auto" className="mt-3 break-words text-sm font-medium">{f.filename}</p><p className="mt-1 text-xs text-muted">{fileType(f)} · {f.folder_name}</p><p className="mt-1 text-xs text-muted">{f.created_at.slice(0, 10)}{f.local ? ` · ${Math.max(1, Math.round(f.size / 1024))} KB` : " · Drive"}</p></Link></li>)}
        </ul>
        {savedFiles && savedFiles.length >= limit && limit < 1000 && <button className="mt-4 rounded-lg border border-line px-3 py-2 text-sm" onClick={() => setLimit(limit + 200)}>Load more files</button>}
      </section>
      {hasSelection && <section aria-label="Note detail" className="min-w-0 lg:border-l lg:border-line lg:pl-6">
        <button type="button" onClick={back} className="mb-5 inline-block text-sm text-muted hover:underline">← Back to notes</button>
        {detailError && <p role="alert" className="text-sm text-danger">{detailError.message}</p>}
        {selected > 0 && !note && !detailError && <p className="text-sm text-muted">Loading saved note…</p>}
        {note && selected > 0 && <NoteDetail key={note.revision} note={note} folders={folders ?? []} onDeleted={() => entryDeleted("note", note.id)} />}
        {fileError && <p role="alert" className="text-sm text-danger">{fileError.message}</p>}
        {selectedFile > 0 && !savedFile && !fileError && <p className="text-sm text-muted">Loading file…</p>}
        {savedFile && selectedFile > 0 && <FileDetail key={savedFile.revision} file={savedFile} folders={folders ?? []} approval={driveApprovals[savedFile.id]} onPrepared={(item) => setDriveApprovals((current) => ({ ...current, [savedFile.id]: item }))} onDeleted={() => entryDeleted("file", savedFile.id)} />}
      </section>}
    </div>
  </section>;
}

export default function NotesPage() {
  return <Suspense fallback={<p className="p-6 text-sm text-muted">Loading notes…</p>}><NotesLibrary /></Suspense>;
}
