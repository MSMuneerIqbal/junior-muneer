"use client";

import { useState, type FormEvent } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";

type Resource = { path: string; kind: "script" | "reference" | "template"; content: string };
type Skill = { name: string; description: string; instructions: string; for: string[]; revision: string; resources: Resource[] };
type Version = { revision: string; modified_at: string; current: boolean };
const KEY = "/api/skills";
const title = (name: string) => name.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
const inputClass = "w-full rounded-xl border border-line bg-panel px-3 py-2.5 text-sm outline-none focus:border-accent focus:ring-1 focus:ring-accent";
const buttonClass = "rounded-xl border border-line px-4 py-2 text-sm hover:bg-panel-2 disabled:opacity-50";
const empty = (): Skill => ({ name: "", description: "", instructions: "", for: ["junior_muneer"], revision: "", resources: [] });

export default function SkillsSettings() {
  const { data, error, mutate } = useSWR<Skill[]>(KEY, fetcher);
  const [query, setQuery] = useState("");
  const [editing, setEditing] = useState<Skill | null>(null);
  const [original, setOriginal] = useState<Skill | null>(null);
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [discarding, setDiscarding] = useState(false);
  const [notice, setNotice] = useState<{ ok: boolean; text: string } | null>(null);
  const [selectedVersion, setSelectedVersion] = useState("");
  const { data: versions, mutate: mutateVersions } = useSWR<Version[]>(editing?.revision ? `${KEY}/${encodeURIComponent(editing.name)}/versions` : null, fetcher);
  const { data: deleted, mutate: mutateDeleted } = useSWR<{ name: string; revision: string; modified_at: string }[]>("/api/skills-deleted", fetcher);
  const dirty = JSON.stringify(editing) !== JSON.stringify(original);

  function open(skill: Skill) {
    const normalized = { ...skill, resources: skill.resources ?? [] };
    setEditing({ ...normalized, for: [...normalized.for], resources: normalized.resources.map((resource) => ({ ...resource })) });
    setOriginal(normalized);
    setDeleting(false);
    setDiscarding(false);
    setNotice(null);
    setSelectedVersion("");
  }
  function close() {
    setEditing(null);
    setOriginal(null);
    setDeleting(false);
    setDiscarding(false);
    setSelectedVersion("");
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!editing || busy) return;
    setBusy(true);
    setNotice(null);
    try {
      const body = { description: editing.description, instructions: editing.instructions, for: editing.for, resources: editing.resources };
      const saved = editing.revision
        ? await send<Skill>("PUT", `${KEY}/${encodeURIComponent(editing.name)}`, { ...body, revision: editing.revision })
        : await send<Skill>("POST", KEY, { ...body, name: editing.name });
      await mutate((current) => [...(current ?? []).filter((s) => s.name !== saved.name), saved]
        .sort((a, b) => a.name.localeCompare(b.name)), { revalidate: false });
      close();
      void mutateDeleted(); void mutateVersions();
      setNotice({ ok: true, text: `${title(saved.name)} saved. Junior can use it from your next message.` });
    } catch (e) {
      setNotice({ ok: false, text: e instanceof Error ? e.message : "Couldn't save this skill." });
      void mutate(); // refresh the list after a conflict, while preserving the unsaved editor
    } finally { setBusy(false); }
  }
  async function remove() {
    if (!editing?.revision || busy) return;
    setBusy(true);
    setNotice(null);
    try {
      await send("DELETE", `${KEY}/${encodeURIComponent(editing.name)}`, { revision: editing.revision });
      await mutate((current) => current?.filter((s) => s.name !== editing.name), { revalidate: false });
      close();
      void mutateDeleted();
      setNotice({ ok: true, text: `${title(editing.name)} deleted. It will no longer be offered to Junior.` });
    } catch (e) {
      setNotice({ ok: false, text: e instanceof Error ? e.message : "Couldn't delete this skill." });
      void mutate();
    } finally { setBusy(false); }
  }

  async function reviewVersion(name: string, revision: string, restoring = false) {
    setBusy(true); setNotice(null);
    try {
      const old = await fetcher<Skill>(`${KEY}/${encodeURIComponent(name)}/versions/${revision}`);
      if (restoring) {
        setEditing({ ...old, revision: "" }); setOriginal(empty());
        setDeleting(false); setDiscarding(false); setSelectedVersion("");
      } else if (editing) setEditing({ ...old, revision: original?.revision || editing.revision });
      setNotice({ ok: true, text: "Saved version loaded for review. Save skill to restore it." });
    } catch (e) { setNotice({ ok: false, text: e instanceof Error ? e.message : "Couldn't load that version." }); }
    finally { setBusy(false); }
  }

  function addResource() {
    if (!editing || editing.resources.length >= 6) return;
    let number = 1;
    while (editing.resources.some((resource) => resource.path === `references/resource_${number}.md`)) number += 1;
    setEditing({ ...editing, resources: [...editing.resources, { path: `references/resource_${number}.md`, kind: "reference", content: "" }] });
  }

  const filtered = (data ?? []).filter((s) => `${title(s.name)} ${s.name} ${s.description}`.toLowerCase().includes(query.toLowerCase()));
  return (
    <div className="py-5">
      {notice && <p role={notice.ok ? "status" : "alert"} className={`mb-4 rounded-xl p-3 text-sm ${notice.ok ? "bg-accent-soft text-ink" : "bg-danger-soft text-danger"}`}>{notice.text}</p>}
      {error && <div role="alert" className="mb-4 text-sm text-danger">Couldn&apos;t load skills. {error.message} <button type="button" className="underline" onClick={() => void mutate()}>Retry</button></div>}
      {!data && !error && <p role="status" className="text-sm text-muted">Loading skills…</p>}
      {editing ? (
        <form onSubmit={save} className="space-y-5" aria-label="Skill editor">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h3 className="text-base font-semibold">{editing.revision ? `Edit ${title(editing.name)}` : "New skill"}</h3>
            <button type="button" disabled={busy} className={buttonClass} onClick={() => dirty ? setDiscarding(true) : close()}>Back to skills</button>
          </div>
          {discarding && <div className="rounded-xl border border-line p-4 text-sm" role="group" aria-label="Unsaved skill changes">
            <p>You have unsaved changes. Discard them?</p>
            <div className="mt-3 flex gap-2">
              <button type="button" className={buttonClass} onClick={close}>Discard changes</button>
              <button type="button" className={buttonClass} onClick={() => setDiscarding(false)}>Keep editing</button>
            </div>
          </div>}
          <label className="block space-y-2 text-sm font-medium">Skill name
            <input aria-label="Skill name" className={inputClass} required minLength={2} maxLength={50} pattern="[a-z][a-z0-9_]{1,49}"
              title="2–50 lowercase letters, digits or underscores; start with a letter."
              disabled={busy || !!editing.revision} value={editing.name}
              placeholder="weekly_client_report" onChange={(e) => setEditing({ ...editing, name: e.target.value.toLowerCase().replaceAll(" ", "_").replaceAll("-", "_") })} />
            <span className="block text-xs font-normal text-muted">A short name, such as weekly_client_report. The name stays fixed after creation.</span>
          </label>
          <label className="block space-y-2 text-sm font-medium">When to use it
            <textarea className={inputClass} required minLength={10} maxLength={300} rows={3} disabled={busy}
              placeholder="Use when I ask for a weekly client update: completed work, next steps and blockers."
              value={editing.description} onChange={(e) => setEditing({ ...editing, description: e.target.value })} />
          </label>
          <label className="block space-y-2 text-sm font-medium">Used by
            <select className={inputClass} disabled={busy} value={editing.for.join(",")}
              onChange={(e) => setEditing({ ...editing, for: e.target.value ? e.target.value.split(",") : [] })}>
              <option value="junior_muneer">Junior Muneer</option>
              <option value="computer_agent">Computer Agent</option>
              <option value="">All agents with skills</option>
              {!!editing.for.length && !["junior_muneer", "computer_agent"].includes(editing.for.join(",")) &&
                <option value={editing.for.join(",")}>{editing.for.map(title).join(", ")}</option>}
            </select>
          </label>
          <label className="block space-y-2 text-sm font-medium">Instructions
            <textarea aria-label="Instructions" className={`${inputClass} min-h-72 font-mono leading-relaxed`} required minLength={40} maxLength={20000}
              disabled={busy} rows={16} dir="auto" value={editing.instructions}
              placeholder={"## Steps\n1. Read the notes I provide.\n2. Separate completed work, next steps and blockers.\n3. Check every claim against those notes.\n\n## Result\nA short client update, ready for me to review."}
              onChange={(e) => setEditing({ ...editing, instructions: e.target.value })} />
            <span className="block text-xs font-normal text-muted">Write the steps, what to check and what the result should look like. Skills follow your permissions and available tools.</span>
          </label>
          <fieldset className="space-y-3 rounded-xl border border-line p-4" disabled={busy}>
            <legend className="px-1 text-sm font-medium">Resources</legend>
            <p className="text-xs text-muted">Up to six text resources, 8,000 characters each. Junior loads only the resource a task needs. Scripts require an approved computer command to run; loading a skill never executes them. Keep credentials in account/settings connections.</p>
            {editing.resources.map((resource, index) => <div key={index} className="space-y-3 rounded-lg border border-line p-3">
              <div className="flex flex-wrap items-end gap-2">
                <label className="min-w-0 flex-1 text-xs">Resource {index + 1} path
                  <input aria-label={`Resource ${index + 1} path`} className={`${inputClass} mt-1`} required maxLength={90} value={resource.path}
                    onChange={(e) => setEditing({ ...editing, resources: editing.resources.map((item, n) => n === index ? { ...item, path: e.target.value } : item) })} />
                </label>
                <label className="text-xs">Resource {index + 1} type
                  <select aria-label={`Resource ${index + 1} type`} className={`${inputClass} mt-1`} value={resource.kind} onChange={(e) => {
                    const kind = e.target.value as Resource["kind"];
                    const prefix = kind === "script" ? "scripts" : kind === "template" ? "templates" : "references";
                    const stem = resource.path.split("/").at(-1)?.replace(/\.[^.]+$/, "") || `resource_${index + 1}`;
                    setEditing({ ...editing, resources: editing.resources.map((item, n) => n === index ? { ...item, kind, path: `${prefix}/${stem}.${kind === "script" ? "py" : "md"}` } : item) });
                  }}><option value="reference">Reference</option><option value="template">Template</option><option value="script">Script</option></select>
                </label>
                <button type="button" className={buttonClass} onClick={() => setEditing({ ...editing, resources: editing.resources.filter((_, n) => n !== index) })}>Remove resource {index + 1}</button>
              </div>
              <label className="block text-xs">Resource {index + 1} content
                <textarea aria-label={`Resource ${index + 1} content`} className={`${inputClass} mt-1 font-mono text-xs`} required rows={6} maxLength={8000} value={resource.content}
                  onChange={(e) => setEditing({ ...editing, resources: editing.resources.map((item, n) => n === index ? { ...item, content: e.target.value } : item) })} />
              </label>
            </div>)}
            <button type="button" className={buttonClass} disabled={editing.resources.length >= 6} onClick={addResource}>Add resource</button>
          </fieldset>
          {editing.revision && <div role="group" aria-label="Saved skill versions" className="space-y-2 rounded-xl border border-line p-4">
            <p className="text-sm font-medium">Saved versions</p>
            <p className="text-xs text-muted">Up to 20 previous versions, including their resources. Loading a version only changes this editor; Save applies it.</p>
            <label className="block text-xs">Version to review
              <select aria-label="Version to review" className={`${inputClass} mt-1`} value={selectedVersion} onChange={(e) => setSelectedVersion(e.target.value)}>
                <option value="">Choose a version</option>
                {versions?.map((version) => <option key={version.revision} value={version.revision}>{new Date(version.modified_at).toLocaleString()} · {version.revision.slice(0, 8)}{version.current ? " (current)" : ""}</option>)}
              </select>
            </label>
            <button type="button" disabled={busy || dirty || !selectedVersion || selectedVersion === original?.revision} className={buttonClass}
              onClick={() => void reviewVersion(editing.name, selectedVersion)}>Load selected version</button>
            {dirty && <p className="text-xs text-muted">Save or discard your edits before loading another version.</p>}
          </div>}
          <div className="flex flex-wrap items-center gap-3">
            <button type="submit" disabled={busy || !dirty} className="rounded-xl bg-accent px-4 py-2 text-sm font-medium text-accent-fg disabled:opacity-50">{busy ? "Working…" : "Save skill"}</button>
            {editing.revision && <button type="button" disabled={busy} className={`${buttonClass} ml-auto text-danger`} onClick={() => setDeleting(true)}>Delete skill</button>}
          </div>
          {deleting && <div role="group" aria-label="Confirm skill deletion" className="rounded-xl border border-danger p-4 text-sm">
            <p>Delete {title(editing.name)} from Junior&apos;s active skills? Saved versions remain available to restore. Your files and past work stay unchanged.</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <button type="button" disabled={busy} className={`${buttonClass} text-danger`} onClick={remove}>Confirm delete</button>
              <button type="button" disabled={busy} className={buttonClass} onClick={() => setDeleting(false)}>Keep skill</button>
            </div>
          </div>}
        </form>
      ) : data && (
        <>
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <input className={`${inputClass} min-w-0 flex-1`} type="search" aria-label="Search skills" placeholder="Search skills…" value={query} onChange={(e) => setQuery(e.target.value)} />
            <button type="button" onClick={() => open(empty())} className="rounded-xl bg-accent px-4 py-2.5 text-sm font-medium text-accent-fg">Add skill</button>
          </div>
          <p className="mb-4 text-sm text-muted">{data.length} {data.length === 1 ? "skill" : "skills"}. Describe your task naturally; Junior loads the matching instructions when needed.</p>
          <p className="mb-4 text-xs text-muted">Chat commands: /skills, /reload-skills, /memory, or /learn name | when to use it | workflow steps. Learned workflows wait for approval.</p>
          <ul aria-label="Skills" className="space-y-3">
            {filtered.map((skill) => <li key={skill.name} className="rounded-xl border border-line p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="break-words text-sm font-semibold">{title(skill.name)}</h3>
                  <p className="mt-1 break-words text-sm leading-relaxed text-muted">{skill.description}</p>
                  <p className="mt-2 text-xs text-muted">{skill.for.length ? skill.for.map(title).join(" · ") : "All agents with skills"}</p>
                  {!!skill.resources?.length && <p className="mt-1 text-xs text-muted">{skill.resources.length} resources</p>}
                </div>
                <button type="button" aria-label={`Edit ${title(skill.name)}`} className={`${buttonClass} shrink-0`} onClick={() => open(skill)}>Edit</button>
              </div>
            </li>)}
          </ul>
          {!filtered.length && <p className="py-8 text-center text-sm text-muted">{data.length ? "No skills match your search." : "No skills yet. Add your first repeatable task."}</p>}
          {!!deleted?.length && <details className="mt-6 rounded-xl border border-line p-4 text-sm">
            <summary className="cursor-pointer font-medium">Deleted skills</summary>
            <p className="mt-2 text-xs text-muted">Review a saved version, then save it to restore the skill.</p>
            <ul className="mt-3 space-y-2">{deleted.map((skill) => <li key={skill.name} className="flex flex-wrap items-center justify-between gap-2">
              <span>{title(skill.name)}</span><button type="button" disabled={busy} className={buttonClass}
                onClick={() => void reviewVersion(skill.name, skill.revision, true)}>Review restore {title(skill.name)}</button>
            </li>)}</ul>
          </details>}
        </>
      )}
    </div>
  );
}
