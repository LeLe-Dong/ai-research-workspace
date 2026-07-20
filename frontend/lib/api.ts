// API base resolution:
//   1. Build-time env var: NEXT_PUBLIC_API_BASE (e.g. "http://127.0.0.1:8003")
//   2. Runtime: default to window.location.origin so the page hits the SAME host it's on
//      (works behind nginx, or when next.js proxies /api/*)
//
// This means: when accessed from http://10.6.69.20/ → /api/* goes to
// http://10.6.69.20/api/*. No more "Failed to fetch" because 127.0.0.1 doesn't exist
// on the user's machine.
// Cache-bust: force-new-hash-2026-07-17-1030
function resolveApiBase(): string {
  const envBase = process.env.NEXT_PUBLIC_API_BASE;
  if (envBase && envBase.length > 0) return envBase;
  if (typeof window !== "undefined") return window.location.origin;
  return ""; // SSR fallback (won't be hit since pages use "use client")
}
export const API_BASE = resolveApiBase();

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
  delete: <T>(path: string) => request<T>(path, { method: "DELETE" }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: body ? JSON.stringify(body) : undefined }),
};
