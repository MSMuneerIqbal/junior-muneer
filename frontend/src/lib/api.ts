/** Talking to the backend (FastAPI). */

export const BACKEND_URL = (
  process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

export const WS_URL = BACKEND_URL.replace(/^http/, "ws") + "/ws/chat";

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
