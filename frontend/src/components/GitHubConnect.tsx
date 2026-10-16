"use client";

import { useEffect, useRef, useState } from "react";
import { send } from "@/lib/api";

type Started = { flow_id: string; user_code: string; verification_uri: string; interval: number; expires_in: number };
type Checked = { status: "pending" | "connected" | "expired" | "denied" | "error"; account: string; message: string; interval?: number };

/**
 * Connect GitHub with GitHub's device login: a code to type at github.com/login/device, then
 * Approve. Used in Settings and in the chat when an agent needs GitHub.
 */
export function GitHubConnect({ onConnected }: { onConnected?: (account: string) => void }) {
  const [flow, setFlow] = useState<Started | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const stopped = useRef(false);

  useEffect(() => {
    stopped.current = false;
    if (!flow) return;
    let timer: ReturnType<typeof setTimeout>;
    const check = async (wait: number) => {
      timer = setTimeout(async () => {
        if (stopped.current) return;
        try {
          const r = await send<Checked>("POST", `/api/github/connect/${flow.flow_id}`);
          if (r.status === "pending") return check(r.interval ?? wait);
          setFlow(null);
          setMessage(r.message);
          if (r.status === "connected") onConnected?.(r.account);
        } catch (e) {
          setFlow(null);
          setMessage(e instanceof Error ? e.message : "Couldn't check with GitHub");
        }
      }, wait * 1000);
    };
    void check(flow.interval);
    return () => {
      stopped.current = true;
      clearTimeout(timer);
    };
  }, [flow, onConnected]);

  async function start() {
    setBusy(true);
    setMessage(null);
    try {
      setFlow(await send<Started>("POST", "/api/github/connect"));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Couldn't start");
    } finally {
      setBusy(false);
    }
  }

  async function copy(code: string) {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* the code is on screen to type */
    }
  }

  if (flow) {
    return (
      <div role="group" aria-label="Connect GitHub" className="flex flex-col gap-2 rounded-xl border border-line bg-panel-2 p-3 text-sm">
        <p>1. Copy this code:</p>
        <div className="flex items-center gap-2">
          <code data-testid="github-code" className="rounded-lg bg-panel px-3 py-1.5 font-mono text-lg font-semibold tracking-widest">
            {flow.user_code}
          </code>
          <button type="button" onClick={() => copy(flow.user_code)} className="rounded-lg border border-line px-2.5 py-1 text-xs hover:bg-panel">
            {copied ? "Copied ✓" : "Copy code"}
          </button>
        </div>
        <p>
          2.{" "}
          <a href={flow.verification_uri} target="_blank" rel="noopener noreferrer" className="font-medium text-accent hover:underline">
            Open GitHub ↗
          </a>
          , paste the code and press <b>Authorize</b>.
        </p>
        <p className="text-xs text-muted" role="status">
          Waiting for you to approve on GitHub…
        </p>
        <button
          type="button"
          onClick={() => {
            stopped.current = true;
            setFlow(null);
          }}
          className="self-start text-xs text-muted hover:text-ink"
        >
          Cancel
        </button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={start}
        disabled={busy}
        className="self-start rounded-lg bg-accent px-3 py-1.5 text-sm font-semibold text-accent-fg hover:opacity-90 disabled:opacity-60"
      >
        {busy ? "Starting…" : "Connect GitHub"}
      </button>
      {message && (
        <p className="text-xs text-muted" role="status">
          {message}
        </p>
      )}
    </div>
  );
}
