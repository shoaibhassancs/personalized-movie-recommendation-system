import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import type { Movie, MovieState, User } from "../api/types";

export interface Call {
  method: string;
  path: string;
  search: string;
  headers: Record<string, string>;
  body: unknown;
}
type Reply =
  | { status?: number; body?: unknown }
  | ((call: Call) => { status?: number; body?: unknown });

/** Replace fetch with a table of "METHOD /path" -> reply. Unlisted routes fail the test. */
export function mockApi(routes: Record<string, Reply>) {
  const calls: Call[] = [];
  const fetchMock = vi.fn(async (input: URL | string, init?: RequestInit) => {
    const url = new URL(String(input));
    const call: Call = {
      method: init?.method ?? "GET",
      path: url.pathname,
      search: url.search,
      headers: (init?.headers ?? {}) as Record<string, string>,
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    };
    calls.push(call);
    const entry = routes[`${call.method} ${call.path}`];
    if (!entry) throw new Error(`unexpected request: ${call.method} ${call.path}`);
    const reply = typeof entry === "function" ? entry(call) : entry;
    const status = reply.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(reply.body ?? {}), {
      status,
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

export function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </MemoryRouter>,
  );
}

export const emptyState: MovieState = {
  rating: null,
  liked: false,
  disliked: false,
  watchlist: false,
  watched: false,
  viewed_at: null,
};
export const user: User = {
  id: 7,
  email: "a@example.com",
  display_name: "Ada",
  genres: [],
  created_at: "2026-01-01T00:00:00Z",
};
export const movie: Movie = {
  id: 1,
  title: "Toy Story (1995)",
  year: 1995,
  genres: ["Animation", "Comedy"],
  average_rating: 3.92,
  rating_count: 215,
  poster: { initials: "TS", hue: 120 },
};
