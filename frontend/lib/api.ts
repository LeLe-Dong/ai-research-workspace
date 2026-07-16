// API base: env override, or relative paths (works behind reverse proxy).
// When behind nginx, leave NEXT_PUBLIC_API_BASE unset and /api/* will hit the same origin.
// For local dev without proxy, set NEXT_PUBLIC_API_BASE=http://127.0.0.1:8003
export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "";

export class ApiError extends Error {
  constructor(public status: number, public body: string, message: string) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
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
