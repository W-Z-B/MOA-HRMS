/**
 * Minimal API client: same-origin fetch, JSON, CSRF header for unsafe methods, typed errors.
 * No third-party dependency; TanStack Query can wrap this later per ADR 0001.
 */

export class ApiError extends Error {
  status: number;
  code: string;
  detail: string;
  fields?: Record<string, string[]>;

  constructor(status: number, code: string, detail: string, fields?: Record<string, string[]>) {
    super(detail);
    this.status = status;
    this.code = code;
    this.detail = detail;
    this.fields = fields;
  }
}

/**
 * Fired on window when the server says the person is no longer signed in: an idle or expired session,
 * or one ended from another device. The detail is the server's sentence for an expiry, else empty.
 */
export const SIGNED_OUT_EVENT = "hrms:signed-out";

function csrfToken(): string | undefined {
  return document.cookie
    .split("; ")
    .find((row) => row.startsWith("csrftoken="))
    ?.split("=")[1];
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const token = csrfToken();
    if (token) headers.set("X-CSRFToken", token);
  }
  const response = await fetch(`/api/v1${path}`, { ...init, method, headers, credentials: "same-origin" });
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => ({}));
  if (!response.ok) {
    const fields = typeof body === "object" && !("detail" in body) ? body : undefined;
    const code = body.code ?? "error";
    const ended =
      (response.status === 401 && code === "session_expired") ||
      (response.status === 403 && code === "not_authenticated");
    if (ended && !path.startsWith("/auth/login")) {
      const reason = code === "session_expired" ? body.detail : "";
      window.dispatchEvent(new CustomEvent(SIGNED_OUT_EVENT, { detail: reason }));
    }
    throw new ApiError(response.status, code, body.detail ?? "Request failed", fields);
  }
  return body as T;
}

const encode = (data: unknown) => (data instanceof FormData ? data : JSON.stringify(data));

export const get = <T>(path: string) => api<T>(path);

/** Every page of a list, following `next` (up to `pages` pages): for short reference lists. */
export async function getAll<T>(path: string, pages = 20): Promise<T[]> {
  const rows: T[] = [];
  let next: string | null = path;
  for (let page = 0; next && page < pages; page++) {
    const answer: { results: T[]; next: string | null } = await get(next);
    rows.push(...answer.results);
    const url = answer.next ? new URL(answer.next, window.location.origin) : null;
    next = url ? `${url.pathname.replace(/^\/api\/v1/, "")}${url.search}` : null;
  }
  return rows;
}
export const post = <T>(path: string, data?: unknown) =>
  api<T>(path, { method: "POST", body: data === undefined ? undefined : encode(data) });
export const patch = <T>(path: string, data: unknown) => api<T>(path, { method: "PATCH", body: encode(data) });
export const remove = (path: string) => api<void>(path, { method: "DELETE" });

/** The message alone, without the field name in front: for rules that speak in whole sentences. */
export function plainMessage(err: unknown, fallback: string): string {
  if (!(err instanceof ApiError)) return fallback;
  const field = err.fields ? Object.values(err.fields).flat()[0] : undefined;
  return field ?? err.detail;
}

/** First human-readable message from an API error, preferring field errors. */
export function errorMessage(err: unknown, fallback = "Something went wrong."): string {
  if (err instanceof ApiError) {
    const field = err.fields ? Object.entries(err.fields)[0] : undefined;
    return field ? `${field[0].replace(/_/g, " ")}: ${[field[1]].flat()[0]}` : err.detail;
  }
  return fallback;
}
