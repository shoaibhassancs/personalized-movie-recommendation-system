import { clearToken, getToken } from "../auth/tokenStore";

/** API address. Not a secret: it is visible in the browser anyway. */
export const API_URL = (import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000").replace(
  /\/+$/,
  "",
);

/** A cancelled request. Checked by name, not `instanceof DOMException`, so it also works
 *  when the error comes from another realm (e.g. Node's fetch under a test DOM). */
export function isAbort(error: unknown): boolean {
  return (
    typeof error === "object" &&
    error !== null &&
    (error as { name?: unknown }).name === "AbortError"
  );
}

export class ApiError extends Error {
  readonly status: number; // 0 = the API could not be reached
  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type Handler = () => void;
let onUnauthorized: Handler | null = null;
/** The auth context registers what happens when a logged-in request gets a 401. */
export function setUnauthorizedHandler(handler: Handler | null): void {
  onUnauthorized = handler;
}

/** Turn an API error body into one readable sentence. The API never echoes input. */
export function messageFromBody(body: unknown, status: number): string {
  if (typeof body === "object" && body !== null && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      const parts = detail
        .map((d) => {
          if (typeof d !== "object" || d === null) return "";
          const { loc, msg } = d as { loc?: unknown[]; msg?: unknown };
          const field = Array.isArray(loc) ? String(loc[loc.length - 1] ?? "") : "";
          return typeof msg === "string" ? (field ? `${field}: ${msg}` : msg) : "";
        })
        .filter(Boolean);
      if (parts.length) return parts.join("; ");
    }
  }
  return `The server returned an error (${status}).`;
}

interface Options {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
}

export async function request<T>(path: string, options: Options = {}): Promise<T> {
  const { method = "GET", body, query, signal } = options;
  const url = new URL(API_URL + path);
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  const token = getToken();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal,
    });
  } catch (error) {
    if (isAbort(error)) throw error;
    throw new ApiError(
      0,
      "Cannot reach the API. Is it running, and does its FRONTEND_ORIGIN match this page?",
    );
  }
  if (response.status === 204) return undefined as T;
  let parsed: unknown = null;
  try {
    parsed = await response.json();
  } catch {
    // no JSON body
  }
  if (!response.ok) {
    if (response.status === 401 && token) {
      clearToken();
      onUnauthorized?.();
    }
    throw new ApiError(response.status, messageFromBody(parsed, response.status));
  }
  return parsed as T;
}
