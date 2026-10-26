"use client";

import { useState } from "react";
import useSWR from "swr";
import { BACKEND_URL, fetcher, send } from "@/lib/api";

type Desktop = { enabled: boolean; apps: string[]; supported: Record<string, string>; available: boolean; simulation: boolean };
type WindowInfo = { handle: number; app: string; title: string; foreground: boolean; minimized: boolean };
type Snapshot = { id: string; image_url: string; window: WindowInfo; controls: { index: number; name: string; type: string }[] };

export default function DesktopSettings() {
  const { data, error: loadError, mutate } = useSWR<Desktop>("/api/computer/desktop", fetcher);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [windows, setWindows] = useState<WindowInfo[] | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);

  async function update(enabled: boolean, apps: string[]) {
    setBusy(true); setError("");
    try {
      await mutate(send<Desktop>("PUT", "/api/computer/desktop", { enabled, apps }), {
        optimisticData: data ? { ...data, enabled, apps } : undefined,
        rollbackOnError: true,
        revalidate: false,
      });
      setWindows(null); setSnapshot(null);
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't change desktop controls."); }
    finally { setBusy(false); }
  }

  async function observe(handle?: number) {
    setBusy(true); setError("");
    try {
      if (handle) setSnapshot(await send<Snapshot>("POST", "/api/computer/desktop/snapshot", { handle }));
      else setWindows(await fetcher<WindowInfo[]>("/api/computer/desktop/windows"));
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't observe that window."); }
    finally { setBusy(false); }
  }

  return (
    <section aria-label="Desktop controls" className="flex min-w-0 flex-col gap-3">
      <h3 className="text-sm font-semibold">Desktop controls</h3>
      <p className="text-xs text-muted">Opt in for the apps below. Junior can observe an app and prepare a focus, click or typing card. Approval can bring that exact app/control into focus. Every input waits for approval.</p>
      <p className="text-xs text-muted">No browsers, terminals, passwords, payments or security screens. Use file tools for saving. Your PC must be on and unlocked.</p>
      <p className="text-xs text-muted">Previews include content visible in the selected app. Choose only apps you want Junior to inspect.</p>
      {(error || loadError) && <p role="alert" className="text-xs text-danger">{error || "Couldn't load desktop settings."}</p>}
      {!data && !loadError && <p role="status" className="text-xs text-muted">Loading desktop controls…</p>}
      {data && <>
        {!data.available && <p className="text-xs text-warn">The Windows PC Helper is required on this host.</p>}
        {data.simulation && <p className="text-xs text-warn">Fake AI uses a simulated desktop. No real windows are controlled.</p>}
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={data.enabled} disabled={busy || !data.available}
            onChange={(e) => void update(e.target.checked, data.apps)} />
          Enable desktop controls
        </label>
        <fieldset disabled={busy} className="grid gap-2 sm:grid-cols-2">
          <legend className="mb-2 text-xs font-medium">Allowed desktop apps</legend>
          {Object.entries(data.supported).map(([app, label]) => (
            <label key={app} className="flex items-center gap-2 text-xs">
              <input type="checkbox" checked={data.apps.includes(app)}
                onChange={(e) => void update(data.enabled, e.target.checked ? [...data.apps, app] : data.apps.filter((a) => a !== app))} />
              {label} <span className="text-muted">({app})</span>
            </label>
          ))}
        </fieldset>
        {data.enabled && <>
          <button type="button" disabled={busy} onClick={() => void observe()}
            className="self-start rounded-md border border-line px-3 py-1.5 text-xs disabled:opacity-50">Refresh app windows</button>
          {windows?.length === 0 && <p className="text-xs text-muted">No allowed app windows are open. Open an allowed app, then refresh.</p>}
          {windows?.map((window) => <div key={window.handle} className="flex flex-wrap items-center gap-2 rounded-lg border border-line p-2 text-xs">
            <span className="min-w-0 flex-1 break-words">{window.title} · {data.supported[window.app]}</span>
            <button type="button" disabled={busy} onClick={() => void observe(window.handle)}
              className="rounded-md border border-line px-2 py-1">Preview {window.title}</button>
          </div>)}
          {snapshot && <figure className="min-w-0 rounded-lg border border-line p-2">
            <figcaption className="mb-2 text-xs">Observed: {snapshot.window.title}. Captures expire after one day and are cleaned up on the next use.</figcaption>
            {snapshot.image_url ? (
              // eslint-disable-next-line @next/next/no-img-element -- local authenticated, expiring window capture
              <img src={`${BACKEND_URL}${snapshot.image_url}`} alt={`Desktop preview: ${snapshot.window.title}`} className="h-auto max-w-full rounded" />
            ) : <p className="text-xs text-muted">The window is minimized. Ask Junior for a focus card to restore it.</p>}
          </figure>}
        </>}
      </>}
    </section>
  );
}
