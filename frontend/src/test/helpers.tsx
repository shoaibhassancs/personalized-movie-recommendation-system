import { render } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { vi } from "vitest";
import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import type {
  DashboardOut,
  Movie,
  MovieState,
  RecommendationsOut,
  User,
} from "../api/types";

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

export const MODEL_NOTICE =
  "These lists come from the serving model, fitted on all MovieLens data. It has no " +
  "separate quality metric. The Step 16 offline results describe a different, " +
  "separately fitted model, compare methods under one holdout protocol only, and do " +
  "not show that these lists suit you.";

export function recOut(overrides: Partial<RecommendationsOut> = {}): RecommendationsOut {
  return {
    strategy: "hybrid",
    branch: "many_ratings",
    branch_reason: "You have 12 ratings, so the full hybrid blend is used.",
    score_kind: "blend",
    rating_count: 12,
    items: [
      {
        movie,
        score: 0.4321,
        explanation: "Similar to movies you rated highly.",
        source: "content",
        state: emptyState,
      },
      {
        movie: { ...movie, id: 2, title: "Jumanji (1995)" },
        score: 0.3,
        explanation: "Popular with people who rated similar movies.",
        source: "item_knn",
        state: { ...emptyState, watchlist: true },
      },
    ],
    notes: [],
    served_events_logged: 2,
    model_notice: MODEL_NOTICE,
    ...overrides,
  };
}

export function dashboardOut(overrides: Partial<DashboardOut> = {}): DashboardOut {
  const page = { items: [movie], page: 1, page_size: 10, total: 1 };
  return {
    recommended: recOut(),
    trending: {
      source: "app_activity",
      window_start: "2026-10-01T00:00:00Z",
      window_end: "2026-10-31T00:00:00Z",
      window_days: 30,
      note: "Ratings and actions by registered users in the last 30 days.",
      items: [{ movie, interactions: 4 }],
    },
    popular: [movie],
    recent_releases: [{ ...movie, id: 3, title: "Newest Film (2024)" }],
    genres: ["Comedy"],
    watchlist: page,
    activity: {
      items: [
        {
          movie,
          state: { ...emptyState, rating: 4 },
          last_activity: "2026-10-30T00:00:00Z",
        },
      ],
      page: 1,
      page_size: 10,
      total: 1,
    },
    ...overrides,
  };
}
