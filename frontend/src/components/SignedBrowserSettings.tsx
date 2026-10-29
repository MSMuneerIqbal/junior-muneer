"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, send } from "@/lib/api";

type Connection = { connected: boolean; media_enabled: boolean; extension_folder: string };
type Pairing = Connection & { pairing_code: string };

export default function SignedBrowserSettings() {
  const { data, error, mutate } = useSWR<Connection>("/api/computer/signed-browser", fetcher, { refreshInterval: 5000 });
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState("");

  async function selectMode(enabled: boolean) {
    setBusy(true); setProblem("");
    try { await mutate(await send<Connection>("PUT", "/api/computer/signed-browser/media", { enabled }), false); }
    catch (e) { setProblem(e instanceof Error ? e.message : "Couldn't change the player."); }
    finally { setBusy(false); }
  }
  async function pair() {
    setBusy(true); setProblem(""); setCode("");
    try {
      const result = await send<Pairing>("POST", "/api/computer/signed-browser/pair", {});
      setCode(result.pairing_code);
      await mutate({ connected: result.connected, media_enabled: result.media_enabled, extension_folder: result.extension_folder }, false);
    }
    catch (e) { setProblem(e instanceof Error ? e.message : "Couldn't create a pairing code."); }
    finally { setBusy(false); }
  }
  async function disconnect() {
    setBusy(true); setProblem(""); setCode("");
    try { await mutate(await send<Connection>("POST", "/api/computer/signed-browser/disconnect", {}), false); }
    catch (e) { setProblem(e instanceof Error ? e.message : "Couldn't disconnect Chrome."); }
    finally { setBusy(false); }
  }

  return <section aria-label="Signed-in Chrome player" className="rounded-lg border border-line p-3 text-xs">
    <h4 className="font-medium">YouTube player browser</h4>
    <p className="mt-2 text-muted">Use your signed-in Chrome for YouTube, or Junior&apos;s separate temporary player. General website actions still use Junior&apos;s separate browser. Your Chrome uses its normal network connection, not the separate browser&apos;s network protections.</p>
    {(problem || error) && <p role="alert" className="mt-2 text-danger">{problem || "The Chrome connection is available only on this computer."}</p>}
    {data && <>
      <label className="mt-3 flex flex-col gap-1">YouTube browser
        <select aria-label="YouTube browser" value={data.media_enabled ? "chrome" : "separate"} disabled={busy}
          onChange={(e) => void selectMode(e.target.value === "chrome")}
          className="rounded-md border border-line bg-bg px-2 py-1.5 text-sm">
          <option value="separate">Junior&apos;s separate browser</option>
          <option value="chrome">My Chrome profile (YouTube only)</option>
        </select>
      </label>
      <p aria-live="polite" className="mt-2">{data.connected ? "Chrome extension connected" : "Chrome extension not connected"}</p>
      <p className="mt-2 text-muted">In Chrome, open Extensions → Manage extensions, turn on Developer mode, and choose Load unpacked. Select this folder:</p>
      <p className="mt-1 break-all font-mono">{data.extension_folder}</p>
      <p className="mt-2 text-muted">Generate a code, then paste it into the Junior Muneer extension. The code grants access to Junior&apos;s local browser connection; keep it private.</p>
      <div className="mt-2 flex flex-wrap gap-2">
        <button type="button" disabled={busy} onClick={() => void pair()} className="rounded-md border border-line px-3 py-1.5 disabled:opacity-50">Generate pairing code</button>
        <button type="button" disabled={busy} onClick={() => void disconnect()} className="rounded-md border border-line px-3 py-1.5 disabled:opacity-50">Disconnect Chrome</button>
      </div>
      {code && <label className="mt-2 flex flex-col gap-1">Pairing code
        <input readOnly value={code} onFocus={(e) => e.currentTarget.select()} className="w-full rounded-md border border-line bg-bg px-2 py-1.5 font-mono" />
      </label>}
    </>}
  </section>;
}
