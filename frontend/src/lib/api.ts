/** Talking to the backend (FastAPI). */

// "same-origin" (the server build, behind Caddy): the API is at the dashboard's own address.
const configured = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000";
export const BACKEND_URL = (configured === "same-origin" ? "" : configured).replace(/\/$/, "");

/** The chat's WebSocket address (on the server: this page's own address, wss:// over HTTPS). */
export function wsUrl(): string {
  if (BACKEND_URL) return BACKEND_URL.replace(/^http/, "ws") + "/ws/chat";
  const { protocol, host } = window.location;
  return `${protocol === "https:" ? "wss" : "ws"}://${host}/ws/chat`;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(BACKEND_URL + path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError(0, "Can't reach the backend. Is it running? (start.bat starts it)");
  }
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
    } catch {}
    throw new ApiError(response.status, detail);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

/** SWR fetcher: the key is the API path. */
export const fetcher = <T>(path: string) => api<T>(path);

export const send = <T>(method: string, path: string, body?: unknown) =>
  api<T>(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
