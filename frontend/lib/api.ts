// API base: env override, or relative paths (works behind reverse proxy).
// When behind nginx, leave NEXT_PUBLIC_API_BASE unset and /api/* will hit the same origin.
// For local dev without proxy, set NEXT_PUBLIC_API_BASE=http://127.0.0.1:8003
// Cache-bust: force-new-hash-2026-07-16-1500
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE || "") as string;

export class ApiError extends Error {
  constructor(public status: number, public body: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Cache buster 2026-07-16: ensure all clients get fresh chunks
  const url = `${API_BASE}${path}`;
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });
  if (!res.ok) {
    const body = await res.text();
    throw new ApiError(res.status, body, `${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, opts?: { params?: Record<string, string | number | undefined> }) => {
    if (opts?.params) {
      const search = new URLSearchParams();
      for (const [k, v] of Object.entries(opts.params)) {
        if (v !== undefined) search.set(k, String(v));
      }
      const qs = search.toString();
      if (qs) path += (path.includes("?") ? "&" : "?") + qs;
    }
    return request<T>(path);
  },
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
};
