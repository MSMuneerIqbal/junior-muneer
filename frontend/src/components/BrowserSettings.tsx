"use client";

import { useState } from "react";
import useSWR from "swr";
import { BACKEND_URL, fetcher, send } from "@/lib/api";

type Browser = { enabled: boolean; sites: string[]; allow_all: boolean; connected: boolean; simulation: boolean; url: string;
  adapter: string; transport_connected: boolean; peer_port: number;
  expires_seconds: number; downloads: { file_id: number; name: string; url: string }[] };
type Snapshot = { title: string; url: string; text: string; controls: { index: number; tag: string; name: string }[] };

export default function BrowserSettings() {
  const { data, error: loadError, mutate } = useSWR<Browser>("/api/computer/browser", fetcher, { refreshInterval: 5000 });
  const [sites, setSites] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<Snapshot | null>(null);
  const [port, setPort] = useState("9222");

  async function update(enabled: boolean, all = data?.allow_all ?? false) {
    if (!data) return;
    setBusy(true); setError("");
    try {
      const nextSites = all ? ["*"] : sites === null ? data.sites.filter((s) => s !== "*") : sites.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
      await mutate(send<Browser>("PUT", "/api/computer/browser", { enabled, sites: nextSites }), {
        optimisticData: { ...data, enabled, sites: nextSites, allow_all: all, connected: false, url: "" },
        rollbackOnError: true, revalidate: false,
      });
      setSites(null); setPreview(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't save browser settings."); }
    finally { setBusy(false); }
  }

  async function act(action: "snapshot" | "disconnect") {
    setBusy(true); setError("");
    try {
      if (action === "snapshot") setPreview(await send<Snapshot>("POST", "/api/computer/browser/snapshot", {}));
      else { await mutate(await send<Browser>("POST", "/api/computer/browser/disconnect", {}), false); setPreview(null); }
    } catch (e) { setError(e instanceof Error ? e.message : "Browser couldn't complete that request."); }
    finally { setBusy(false); }
  }

  async function connect() {
    setBusy(true); setError("");
    try {
      await mutate(await send<Browser>("POST", "/api/computer/browser/connect", { port: Number(port) }), false);
      setPreview(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't connect that debugging browser."); }
    finally { setBusy(false); }
  }

  return <section aria-label="Browser controls" className="flex min-w-0 flex-col gap-3">
    <h3 className="text-sm font-semibold">Browser controls</h3>
    <p className="text-xs text-muted">Junior opens pages in a background browser with a temporary profile, separate from your signed-in browser. Choose allowed websites, ask Junior to open a page and approve it. Then ask: “Read the current browser page.” Every navigation, click, text entry and download waits for your approval.</p>
    <p className="text-xs text-muted">Sessions close after 15 minutes, Pause, Plan mode or Computer off. No passwords, payments or private networks. Page snapshots use no vision calls. Downloads up to 20 MB appear in the Downloads gallery.</p>
    {(error || loadError) && <p role="alert" className="text-xs text-danger">{error || "Couldn't load browser settings."}</p>}
    {!data && !loadError && <p className="text-xs text-muted">Loading browser settings…</p>}
    {data && <>
      {data.simulation && <p className="text-xs text-warn">Fake AI uses a simulated browser. No websites are contacted.</p>}
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={data.enabled} disabled={busy}
        onChange={(e) => void update(e.target.checked)} />Enable browser controls</label>
      <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={data.allow_all} disabled={busy}
        onChange={(e) => void update(data.enabled, e.target.checked)} />Allow all public websites</label>
      <p className="text-xs text-muted">All public websites includes their subdomains and page resources. Local and private networks remain blocked. Switching scope clears the individual list and closes the current session.</p>
      {!data.allow_all && <>
      <label className="flex flex-col gap-1 text-xs">Allowed website origins (one per line)
        <textarea value={sites ?? data.sites.join("\n")} onChange={(e) => setSites(e.target.value)} rows={3}
          placeholder="https://example.com" className="w-full rounded-md border border-line bg-bg p-2 text-sm" />
      </label>
      <p className="text-xs text-muted">Include required subdomains separately. Saving scope closes the current session. Personal browser cookies are not loaded.</p>
      <button type="button" disabled={busy || sites === null} onClick={() => void update(data.enabled)}
        className="self-start rounded-md border border-line px-3 py-1.5 text-xs disabled:opacity-50">Save websites</button>
      </>}
      <p role="status" className="break-words text-xs">{data.connected ? `Connected · ${data.url} · ${Math.ceil(data.expires_seconds / 60)} min remaining`
        : data.transport_connected ? `Debugging browser attached · 127.0.0.1:${data.peer_port}` : "Browser disconnected"}</p>
      {data.adapter === "cdp" && data.transport_connected && <p className="text-xs text-muted">Attached to running browser on 127.0.0.1:{data.peer_port}. {data.connected ? "Junior is using its own temporary session." : "Ask Junior to open an allowed website; navigation still needs approval."}</p>}
      {(data.connected || data.transport_connected) && <div className="flex flex-wrap gap-2">
        {data.connected && <button type="button" disabled={busy} onClick={() => void act("snapshot")} className="rounded-md border border-line px-3 py-1.5 text-xs">Preview page</button>}
        <button type="button" disabled={busy} onClick={() => void act("disconnect")} className="rounded-md border border-line px-3 py-1.5 text-xs">Disconnect browser</button>
      </div>}
      <details className="rounded-lg border border-line p-3 text-xs">
        <summary className="cursor-pointer font-medium">Connect a running Chrome or Edge browser</summary>
        <p className="mt-2 text-muted">Requires a dedicated debugging profile with Junior&apos;s network protections (see README → Browser connection setup). Junior creates a temporary context in that browser. Existing personal pages and cookies stay separate. Disconnect closes Junior&apos;s context and leaves your browser open.</p>
        <p className="mt-2 text-muted">The debugging port must stay on this computer. Remote/cloud browser connections and the VPS PC Helper require separate setup.</p>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1">Local debugging port
            <input type="number" min={1024} max={65535} value={port} onChange={(e) => setPort(e.target.value)}
              className="w-28 rounded-md border border-line bg-bg px-2 py-1.5 text-sm" />
          </label>
          <button type="button" disabled={busy || !data.enabled || !data.sites.length || !/^\d{4,5}$/.test(port)} onClick={() => void connect()}
            className="rounded-md border border-line px-3 py-1.5 disabled:opacity-50">Connect debugging browser</button>
        </div>
      </details>
      {preview && <div className="min-w-0 rounded-lg border border-line p-3 text-xs">
        <p className="font-medium">{preview.title}</p>
        <pre className="mt-2 max-h-60 overflow-auto whitespace-pre-wrap break-words font-sans">{preview.text}</pre>
        <p className="mt-2 text-muted">{preview.controls.length} observed controls. Website content is outside data.</p>
      </div>}
      {data.downloads.map((file) => <a key={file.file_id} href={`${BACKEND_URL}${file.url}`} className="break-words text-xs text-accent underline">Download {file.name}</a>)}
    </>}
  </section>;
}
