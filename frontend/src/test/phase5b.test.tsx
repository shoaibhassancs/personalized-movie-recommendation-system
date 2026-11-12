import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { AppRoutes } from "../App";
import { AuthProvider } from "../auth/AuthContext";
import { clearToken, getToken, saveToken } from "../auth/tokenStore";
import { servedOnce } from "../served";
import {
  MODEL_NOTICE,
  dashboardOut,
  mockApi,
  movie,
  recOut,
  renderApp,
  user,
} from "./helpers";

const loggedIn = () => saveToken("tok", 3600);
const recsCalls = (calls: { path: string; search: string }[]) =>
  calls.filter((c) => c.path === "/me/recommendations");

describe("recommendation branches and notices", () => {
  const cases = [
    {
      branch: "no_ratings",
      count: 0,
      reason: "You have no ratings, so this is not personalised from your history.",
      title: "Not personalised from your ratings",
    },
    {
      branch: "few_ratings",
      count: 4,
      reason:
        "You have 4 rating(s). Up to 10 ratings the hybrid ranks by popularity, so this list is not personalised.",
      title: "Popularity fallback: not personalised",
    },
    {
      branch: "many_ratings",
      count: 12,
      reason: "You have 12 ratings, so the full hybrid blend is used.",
      title: "Blend built from your 12 ratings",
    },
  ];
  for (const c of cases) {
    it(`shows the API's reason word for word for ${c.branch}`, async () => {
      loggedIn();
      mockApi({
        "GET /me": { body: user },
        "GET /me/recommendations": {
          body: recOut({
            branch: c.branch,
            rating_count: c.count,
            branch_reason: c.reason,
          }),
        },
      });
      renderApp("/recommendations");
      const banner = await screen.findByRole("region", {
        name: "How this list was made",
      });
      expect(within(banner).getByRole("heading", { name: c.title })).toBeInTheDocument();
      expect(within(banner).getByText(c.reason)).toBeInTheDocument();
      // the model notice is shown exactly as the API wrote it
      const notice = screen.getByRole("complementary", {
        name: "About these recommendations",
      });
      expect(within(notice).getByText(MODEL_NOTICE)).toBeInTheDocument();
    });
  }

  it("never claims people saw, liked or benefited from a served list", async () => {
    loggedIn();
    mockApi({ "GET /me": { body: user }, "GET /me/recommendations": { body: recOut() } });
    renderApp("/recommendations");
    await screen.findByText(/The API served 2 movies/);
    const text = document.body.textContent ?? "";
    expect(text).toMatch(/served means returned by the API, not that you saw them/i);
    expect(text).not.toMatch(/conversion|accurate|you will love|best for you|proven/i);
  });

  it("shows the notes, each explanation and its source method", async () => {
    loggedIn();
    mockApi({
      "GET /me": { body: user },
      "GET /me/recommendations": {
        body: recOut({
          notes: ["2 rated movie(s) are not in the model and were ignored."],
        }),
      },
    });
    renderApp("/recommendations");
    expect(
      await screen.findByText(/not in the model and were ignored/),
    ).toBeInTheDocument();
    expect(screen.getByText("Similar to movies you rated highly.")).toBeInTheDocument();
    expect(screen.getByText("Method: Content (genres and tags)")).toBeInTheDocument();
    expect(screen.getByText("Method: Item neighbours")).toBeInTheDocument();
    expect(screen.getByText("On watchlist")).toBeInTheDocument(); // the person's own state
  });

  it("links cards to movie pages and adds no action buttons to them", async () => {
    loggedIn();
    mockApi({ "GET /me": { body: user }, "GET /me/recommendations": { body: recOut() } });
    renderApp("/recommendations");
    const link = await screen.findByRole("link", { name: /Toy Story \(1995\)/ });
    expect(link).toHaveAttribute("href", "/movies/1");
    const list = link.closest("ol")!;
    expect(within(list).queryByRole("button")).toBeNull();
  });

  it("keeps raw scores behind a disclosure that names the score kind", async () => {
    loggedIn();
    mockApi({ "GET /me": { body: user }, "GET /me/recommendations": { body: recOut() } });
    renderApp("/recommendations");
    const summary = await screen.findByText("Show raw scores");
    const details = summary.closest("details")!;
    expect(details).not.toHaveAttribute("open");
    expect(within(details).getByText("blend")).toBeInTheDocument(); // score kind
    expect(
      within(details).getByText(/not comparable with another method/),
    ).toBeInTheDocument();
    expect(screen.getByText("0.432")).toBeInTheDocument(); // in the table, inside the closed details
    expect(details.parentElement?.querySelector(".rec-list")?.textContent).not.toContain(
      "0.432",
    );
  });

  it("explains that watched or disliked movies disappear on a refresh", async () => {
    loggedIn();
    mockApi({ "GET /me": { body: user }, "GET /me/recommendations": { body: recOut() } });
    renderApp("/recommendations");
    expect(
      await screen.findByText(/marked watched or disliked will have disappeared/),
    ).toBeInTheDocument();
  });
});

describe("empty results", () => {
  it("explains an empty single-method list for a person with no ratings", async () => {
    loggedIn();
    mockApi({
      "GET /me": { body: user },
      "GET /me/recommendations": (call) =>
        new URLSearchParams(call.search).get("strategy") === "svd"
          ? {
              body: recOut({
                strategy: "svd",
                branch: null,
                rating_count: 0,
                items: [],
                served_events_logged: 0,
                score_kind: "none",
                branch_reason:
                  "A single method, shown so you can compare it with the hybrid.",
                notes: [
                  "The svd method needs at least one rating, so it returns nothing for you yet.",
                ],
              }),
            }
          : { body: recOut() },
    });
    renderApp("/recommendations");
    await screen.findByText("Similar to movies you rated highly.");
    await userEvent.selectOptions(screen.getByLabelText("Method"), "svd");
    expect(
      await screen.findByText("No suggestions to show for this method right now."),
    ).toBeInTheDocument();
    expect(screen.getByText(/needs at least one rating from you/)).toBeInTheDocument();
    expect(screen.getByText(/returns nothing for you yet/)).toBeInTheDocument();
    expect(screen.queryByText(/The API served/)).toBeNull();
    // the notice still appears even with no items
    expect(
      screen.getByRole("complementary", { name: "About these recommendations" }),
    ).toBeInTheDocument();
  });
});

describe("method picker, refresh and one serving per visit", () => {
  it("opens with hybrid, fetches a method once, reuses it, and refreshes only on request", async () => {
    loggedIn();
    const calls = mockApi({
      "GET /me": { body: user },
      "GET /me/recommendations": (c) => ({
        body: recOut({
          strategy: new URLSearchParams(c.search).get("strategy") ?? "hybrid",
        }),
      }),
    });
    renderApp("/recommendations");
    await screen.findByText("Similar to movies you rated highly.");
    expect(recsCalls(calls)).toHaveLength(1);
    expect(new URLSearchParams(recsCalls(calls)[0]?.search).get("strategy")).toBe(
      "hybrid",
    );
    expect(screen.getByLabelText("Method")).toHaveValue("hybrid");
    // all five approved methods are offered, and only those
    const options = within(screen.getByLabelText("Method"))
      .getAllByRole("option")
      .map((o) => (o as HTMLOptionElement).value);
    expect(options).toEqual(["hybrid", "popularity", "content", "item_knn", "svd"]);

    await userEvent.selectOptions(screen.getByLabelText("Method"), "popularity");
    await waitFor(() => expect(recsCalls(calls)).toHaveLength(2));
    expect(new URLSearchParams(recsCalls(calls)[1]?.search).get("strategy")).toBe(
      "popularity",
    );

    await userEvent.selectOptions(screen.getByLabelText("Method"), "hybrid"); // back: cached
    await screen.findByRole("region", { name: "How this list was made" });
    expect(recsCalls(calls)).toHaveLength(2);

    await userEvent.click(screen.getByRole("button", { name: "Get a fresh list" }));
    await waitFor(() => expect(recsCalls(calls)).toHaveLength(3));
  });

  it("makes exactly one serving request under React Strict Mode", async () => {
    loggedIn();
    const calls = mockApi({
      "GET /me": { body: user },
      "GET /me/recommendations": { body: recOut() },
    });
    render(
      <StrictMode>
        <MemoryRouter initialEntries={["/recommendations"]}>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </MemoryRouter>
      </StrictMode>,
    );
    await screen.findByText("Similar to movies you rated highly.");
    await new Promise((r) => setTimeout(r, 50));
    expect(recsCalls(calls)).toHaveLength(1);
  });

  it("makes exactly one dashboard request under React Strict Mode", async () => {
    loggedIn();
    const calls = mockApi({
      "GET /me": { body: user },
      "GET /me/dashboard": { body: dashboardOut() },
    });
    render(
      <StrictMode>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </MemoryRouter>
      </StrictMode>,
    );
    await screen.findByRole("heading", { name: "Suggested for you" });
    await new Promise((r) => setTimeout(r, 50));
    expect(calls.filter((c) => c.path === "/me/dashboard")).toHaveLength(1);
  });

  it("forgets a failed request so it can be retried", async () => {
    loggedIn();
    let first = true;
    const calls = mockApi({
      "GET /me": { body: user },
      "GET /me/recommendations": () => {
        if (first) {
          first = false;
          return { status: 500, body: {} };
        }
        return { body: recOut() };
      },
    });
    renderApp("/recommendations");
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Get a fresh list" }));
    await screen.findByText("Similar to movies you rated highly.");
    expect(recsCalls(calls)).toHaveLength(2);
  });
});

describe("dashboard", () => {
  it("shows all seven panels", async () => {
    loggedIn();
    mockApi({ "GET /me": { body: user }, "GET /me/dashboard": { body: dashboardOut() } });
    renderApp("/dashboard");
    for (const name of [
      "Suggested for you",
      "Trending",
      "Popular",
      "Recent releases",
      "Your genres",
      "Your watchlist",
      "Recent activity",
    ]) {
      expect(await screen.findByRole("heading", { name })).toBeInTheDocument();
    }
    // the recommended panel carries the same honesty as the recommendations page
    const rec = screen.getByRole("region", { name: "Suggested for you" });
    expect(
      within(rec).getByRole("region", { name: "How this list was made" }),
    ).toBeInTheDocument();
    expect(within(rec).getByText(MODEL_NOTICE)).toBeInTheDocument();
    expect(
      within(rec).getByText(/Opening this page made the API serve 2 of these movies/),
    ).toBeInTheDocument();
    expect(screen.getByText("Newest Film (2024)")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Your genres" })).toHaveTextContent(
      "Comedy",
    );
  });

  it("says where trending comes from: app activity", async () => {
    loggedIn();
    mockApi({ "GET /me": { body: user }, "GET /me/dashboard": { body: dashboardOut() } });
    renderApp("/dashboard");
    const trending = await screen.findByRole("region", { name: "Trending" });
    expect(trending).toHaveTextContent(
      /Activity by registered users of this app in the last 30 days/,
    );
    expect(trending).toHaveTextContent(
      "Ratings and actions by registered users in the last 30 days.",
    );
  });

  it("says plainly when trending is the MovieLens fallback, with the API's note", async () => {
    loggedIn();
    const note =
      "No registered-user activity in the last 30 days, so this shows the most-rated movies in the final 365 days of the MovieLens data.";
    mockApi({
      "GET /me": { body: user },
      "GET /me/dashboard": {
        body: dashboardOut({
          trending: {
            source: "dataset_latest_period",
            window_start: "2017-09-01T00:00:00Z",
            window_end: "2018-09-01T00:00:00Z",
            window_days: 365,
            note,
            items: [{ movie, interactions: 90 }],
          },
        }),
      },
    });
    renderApp("/dashboard");
    const trending = await screen.findByRole("region", { name: "Trending" });
    expect(trending).toHaveTextContent(/MovieLens fallback/);
    expect(trending).toHaveTextContent(
      /not recent activity in this app, and it does not end today/,
    );
    expect(within(trending).getByText(note)).toBeInTheDocument();
  });

  it("shows honest empty states", async () => {
    loggedIn();
    const empty = { items: [], page: 1, page_size: 10, total: 0 };
    mockApi({
      "GET /me": { body: user },
      "GET /me/dashboard": {
        body: dashboardOut({
          recommended: recOut({ items: [], served_events_logged: 0 }),
          genres: [],
          watchlist: empty,
          activity: empty,
        }),
      },
    });
    renderApp("/dashboard");
    expect(
      await screen.findByText("No suggestions to show right now."),
    ).toBeInTheDocument();
    expect(screen.getByText(/You have not chosen any/)).toBeInTheDocument();
    expect(screen.getByText(/Nothing yet\. Open a movie/)).toBeInTheDocument();
    expect(screen.getByText("No activity yet.")).toBeInTheDocument();
  });
});

const summary = {
  movies: 9742,
  users: { total: 611, movielens: 610, app: 1 },
  ratings: { total: 100_840, movielens: 100_836, app: 4 },
  interactions: { like: 2, dislike: 0, watchlist: 1, watched: 1, viewed: 3 },
  recommendation_events: { shown: 20, acted: 2 },
  note: "MovieLens figures are historical data imported from the public dataset; app figures come from registered users of this app.",
};
const distribution = {
  buckets: [0.5, 1, 1.5, 2, 2.5, 3, 3.5, 4, 4.5, 5].map((r, i) => ({
    rating: r,
    total: 1000 * (i + 1) + (r === 4 ? 3 : 0),
    movielens: 1000 * (i + 1),
    app: r === 4 ? 3 : 0,
  })),
  note: "Counts of ratings at each half-star value; MovieLens and app separate.",
};
const engagement = {
  served: 20,
  acted: 2,
  users: 1,
  by_strategy: [
    { strategy: "hybrid", served: 10, acted: 2, acted_per_served: 0.2, users: 1 },
    { strategy: "svd", served: 10, acted: 0, acted_per_served: 0, users: 1 },
  ],
  note: "Served = returned by the API in a list (not necessarily seen). Acted = a later rating, like, dislike, watchlist or watched on a served movie, counted once per serving. These counts do not show that recommendations caused the actions.",
};
const analyticsRoutes = (over: Record<string, unknown> = {}) => ({
  "GET /me": { body: user },
  "GET /analytics/summary": { body: summary },
  "GET /analytics/popular": { body: [{ ...movie, rating_count: 215 }] },
  "GET /analytics/ratings-distribution": { body: distribution },
  "GET /analytics/engagement": { body: engagement },
  ...over,
});

describe("analytics", () => {
  it("keeps MovieLens and app numbers in separate columns", async () => {
    loggedIn();
    mockApi(analyticsRoutes());
    renderApp("/analytics");
    const totals = await screen.findByRole("table", {
      name: /MovieLens \(historical\) and app \(registered\) are separate/,
    });
    const headers = within(totals)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual([
      "",
      "All",
      "MovieLens (historical data)",
      "This app (registered users)",
    ]);
    const ratings = within(totals).getByRole("row", { name: /Ratings/ });
    expect(
      within(ratings)
        .getAllByRole("cell")
        .map((c) => c.textContent),
    ).toEqual(["100,840", "100,836", "4"]);
    expect(
      screen.getByText(/historical data imported from the public dataset/),
    ).toBeInTheDocument();
  });

  it("shows the small-user-count privacy note and the app-only activity", async () => {
    loggedIn();
    mockApi(analyticsRoutes());
    renderApp("/analytics");
    expect(
      await screen.findByText(
        /with very few users an app total can come close to describing one person/,
      ),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("table", { name: "App interactions by kind" }),
    ).toHaveTextContent("Marked watched");
  });

  it("pairs each chart with a text table of the same numbers", async () => {
    loggedIn();
    mockApi(analyticsRoutes());
    renderApp("/analytics");
    const table = await screen.findByRole("table", {
      name: "Ratings at each half-star value",
    });
    expect(within(table).getAllByRole("row")).toHaveLength(11); // header + 10 buckets
    expect(within(table).getByRole("row", { name: /^4 ★/ })).toHaveTextContent("8,003");
    // charts exist but are hidden from assistive technology (the table is the text version)
    const figures = document.querySelectorAll("figure.chart");
    expect(figures.length).toBeGreaterThanOrEqual(2);
    figures.forEach((f) =>
      expect(f.querySelector("ul.bars")).toHaveAttribute("aria-hidden", "true"),
    );
  });

  it("describes served and acted counts without calling them conversion or effect", async () => {
    loggedIn();
    mockApi(analyticsRoutes());
    renderApp("/analytics");
    expect(await screen.findByText(engagement.note)).toBeInTheDocument();
    expect(screen.getByText(/not a conversion rate/)).toBeInTheDocument();
    const table = screen.getByRole("table", {
      name: "Served and acted counts by method",
    });
    expect(within(table).getByRole("row", { name: /Hybrid/ })).toHaveTextContent("0.20");
    expect(
      screen.getByRole("heading", { name: "Recommendations served and acted on" }),
    ).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(
      /effectiveness|success rate|click-through/i,
    );
  });

  it("says so when nothing has been served yet", async () => {
    loggedIn();
    mockApi(
      analyticsRoutes({
        "GET /analytics/engagement": {
          body: { ...engagement, served: 0, acted: 0, users: 0, by_strategy: [] },
        },
      }),
    );
    renderApp("/analytics");
    expect(
      await screen.findByText(/No recommendations have been served yet/),
    ).toBeInTheDocument();
  });

  it("sends a visitor to the login page", async () => {
    clearToken();
    mockApi({});
    renderApp("/analytics");
    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
  });
});

describe("401 handling on the new pages", () => {
  for (const [name, path, routes] of [
    [
      "recommendations",
      "/recommendations",
      { "GET /me/recommendations": { status: 401, body: { detail: "invalid token" } } },
    ],
    [
      "dashboard",
      "/dashboard",
      { "GET /me/dashboard": { status: 401, body: { detail: "invalid token" } } },
    ],
    [
      "analytics",
      "/analytics",
      analyticsRoutes({
        "GET /analytics/summary": { status: 401, body: { detail: "invalid token" } },
      }),
    ],
  ] as const) {
    it(`logs out with a message when the ${name} request is rejected`, async () => {
      loggedIn();
      mockApi({ "GET /me": { body: user }, ...routes });
      renderApp(path);
      expect(await screen.findByText(/session ended/i)).toBeInTheDocument();
      expect(getToken()).toBeNull();
    });
  }
});

describe("landing", () => {
  it("sends a logged-in person from / to the dashboard", async () => {
    loggedIn();
    mockApi({ "GET /me": { body: user }, "GET /me/dashboard": { body: dashboardOut() } });
    renderApp("/");
    expect(
      await screen.findByRole("heading", { name: /^Dashboard/ }),
    ).toBeInTheDocument();
  });

  it("sends a visitor from / to the catalogue", async () => {
    clearToken();
    mockApi({
      "GET /movies": { body: { items: [movie], page: 1, page_size: 20, total: 1 } },
    });
    renderApp("/");
    expect(await screen.findByRole("heading", { name: "Movies" })).toBeInTheDocument();
  });

  it("lands on the dashboard after logging in", async () => {
    clearToken();
    mockApi({
      "POST /auth/login": {
        body: { access_token: "tok", token_type: "bearer", expires_in: 3600 },
      },
      "GET /me": { body: user },
      "GET /me/dashboard": { body: dashboardOut() },
    });
    renderApp("/login");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "a long passphrase here");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(
      await screen.findByRole("heading", { name: /^Dashboard/ }),
    ).toBeInTheDocument();
  });

  it("shows the new pages in the navigation only when logged in", async () => {
    loggedIn();
    mockApi({ "GET /me": { body: user }, "GET /me/dashboard": { body: dashboardOut() } });
    renderApp("/dashboard");
    await screen.findByRole("heading", { name: /^Dashboard/ });
    const nav = screen.getByRole("navigation", { name: "Main" });
    for (const name of ["Dashboard", "Recommendations", "Catalogue", "Analytics"]) {
      expect(within(nav).getByRole("link", { name })).toBeInTheDocument();
    }
  });

  it("forgets every cached request when the person logs out", async () => {
    loggedIn();
    mockApi({
      "GET /me": { body: user },
      "GET /movies": { body: { items: [], page: 1, page_size: 20, total: 0 } },
    });
    renderApp("/movies");
    await screen.findByRole("button", { name: "Log out" });
    let fetched = 0;
    await servedOnce("someone-elses-list", async () => ++fetched);
    await servedOnce("someone-elses-list", async () => ++fetched);
    expect(fetched).toBe(1); // cached while logged in
    await userEvent.click(screen.getByRole("button", { name: "Log out" }));
    await waitFor(() => expect(getToken()).toBeNull());
    await servedOnce("someone-elses-list", async () => ++fetched);
    expect(fetched).toBe(2); // logging out cleared the cache
  });
});

describe("restoring a session under React Strict Mode", () => {
  it("is not logged out when the first, cancelled /me request fails with an abort error", async () => {
    loggedIn();
    let calls = 0;
    // Strict Mode mounts twice, so the first request is cancelled. The cancelled request
    // fails with an error that only has the name "AbortError" (it is not a DOMException of
    // this page's realm, as with Node's fetch under a test DOM).
    vi.stubGlobal(
      "fetch",
      (_url: unknown, init?: RequestInit) =>
        new Promise<Response>((resolve, reject) => {
          calls += 1;
          init?.signal?.addEventListener("abort", () => {
            const error = new Error("cancelled");
            error.name = "AbortError";
            reject(error);
          });
          setTimeout(
            () => resolve(new Response(JSON.stringify(user), { status: 200 })),
            20,
          );
        }),
    );
    render(
      <StrictMode>
        <MemoryRouter initialEntries={["/account"]}>
          <AuthProvider>
            <AppRoutes />
          </AuthProvider>
        </MemoryRouter>
      </StrictMode>,
    );
    expect(
      await screen.findByRole("heading", { name: "Your account" }),
    ).toBeInTheDocument();
    expect(calls).toBeGreaterThanOrEqual(2); // the cancelled one and the real one
    expect(getToken()).not.toBeNull();
  });
});
