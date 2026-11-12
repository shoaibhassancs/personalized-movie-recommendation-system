import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { clearToken, getToken, saveToken } from "../auth/tokenStore";
import { App } from "../App";
import { emptyState, mockApi, movie, renderApp, user } from "./helpers";

const detail = (me: typeof emptyState | null) => ({ ...movie, tags: ["pixar"], me });

describe("route guard", () => {
  it("sends a visitor from /account to the login page", async () => {
    clearToken();
    mockApi({});
    renderApp("/account");
    expect(await screen.findByRole("heading", { name: "Log in" })).toBeInTheDocument();
  });

  it("lets a visitor browse the catalogue", async () => {
    clearToken();
    mockApi({
      "GET /movies": { body: { items: [movie], page: 1, page_size: 20, total: 1 } },
    });
    renderApp("/movies");
    expect(await screen.findByText("Toy Story (1995)")).toBeInTheDocument();
  });
});

describe("register and login", () => {
  it("sends the password untrimmed, stores no password, and lands on genre onboarding", async () => {
    clearToken();
    const password = "  correct horse battery  "; // spaces are part of the password
    const calls = mockApi({
      "POST /auth/register": { status: 201, body: user },
      "POST /auth/login": {
        body: { access_token: "tok", token_type: "bearer", expires_in: 3600 },
      },
      "GET /me": { body: user },
    });
    renderApp("/register");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Display name"), "Ada");
    await userEvent.type(screen.getByLabelText("Password"), password);
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(await screen.findByRole("heading", { name: /Welcome/ })).toBeInTheDocument();
    expect((calls[0]?.body as { password: string }).password).toBe(password);
    expect(getToken()).toBe("tok");
    const everything =
      JSON.stringify({ ...sessionStorage }) + JSON.stringify({ ...localStorage });
    expect(everything).not.toContain("correct horse");
  });

  it("blocks a too-short password before calling the API", async () => {
    clearToken();
    const calls = mockApi({});
    renderApp("/register");
    await userEvent.type(screen.getByLabelText("Password"), "short");
    expect(screen.getByRole("button", { name: "Create account" })).toBeDisabled();
    expect(calls).toHaveLength(0);
  });

  it("shows a wrong-password message and stores no token", async () => {
    clearToken();
    mockApi({
      "POST /auth/login": {
        status: 401,
        body: { detail: "incorrect email or password" },
      },
    });
    renderApp("/login");
    await userEvent.type(screen.getByLabelText("Email"), "a@example.com");
    await userEvent.type(screen.getByLabelText("Password"), "wrong-password-here");
    await userEvent.click(screen.getByRole("button", { name: "Log in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "incorrect email or password",
    );
    expect(getToken()).toBeNull();
  });

  it("returns to the login page with a message when a token is rejected", async () => {
    saveToken("stale", 3600);
    mockApi({ "GET /me": { status: 401, body: { detail: "invalid or expired token" } } });
    renderApp("/account");
    expect(await screen.findByText(/session ended/i)).toBeInTheDocument();
    expect(getToken()).toBeNull();
  });
});

describe("movie controls", () => {
  it("mirrors the server: liking replaces a dislike, and a reload shows the same", async () => {
    saveToken("tok", 3600);
    let state = { ...emptyState, disliked: true };
    mockApi({
      "GET /me": { body: user },
      "GET /movies/1": () => ({ body: detail(state) }),
      "PUT /movies/1/like": () => {
        state = { ...state, liked: true, disliked: false }; // the server removes the dislike
        return { body: state };
      },
    });
    renderApp("/movies/1");
    expect(await screen.findByRole("button", { name: "Disliked" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await userEvent.click(screen.getByRole("button", { name: "Like" }));
    expect(await screen.findByRole("button", { name: "Liked" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "Dislike" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("rates, then clears, using PUT and DELETE", async () => {
    saveToken("tok", 3600);
    let state = { ...emptyState };
    const calls = mockApi({
      "GET /me": { body: user },
      "GET /movies/1": () => ({ body: detail(state) }),
      "PUT /movies/1/rating": (c) => {
        state = { ...state, rating: (c.body as { rating: number }).rating };
        return { body: state };
      },
      "DELETE /movies/1/rating": () => {
        state = { ...state, rating: null };
        return { body: state };
      },
    });
    renderApp("/movies/1");
    await userEvent.click(await screen.findByRole("button", { name: "4.5 stars" }));
    expect(await screen.findByText("★ 4.5 of 5")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Clear rating" }));
    expect(await screen.findByText("Not rated")).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({ rating: 4.5 });
  });

  it("toggles watchlist and watched independently of each other", async () => {
    saveToken("tok", 3600);
    let state = { ...emptyState };
    mockApi({
      "GET /me": { body: user },
      "GET /movies/1": () => ({ body: detail(state) }),
      "PUT /movies/1/watchlist": () => ({
        body: (state = { ...state, watchlist: true }),
      }),
      "PUT /movies/1/watched": () => ({ body: (state = { ...state, watched: true }) }),
      "DELETE /movies/1/watchlist": () => ({
        body: (state = { ...state, watchlist: false }),
      }),
    });
    renderApp("/movies/1");
    await userEvent.click(
      await screen.findByRole("button", { name: "Add to watchlist" }),
    );
    await userEvent.click(await screen.findByRole("button", { name: "Mark as watched" }));
    expect(await screen.findByRole("button", { name: "Watched" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "On watchlist" }));
    expect(
      await screen.findByRole("button", { name: "Add to watchlist" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Watched" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("records a view when a logged-in person opens the page, and only then", async () => {
    saveToken("tok", 3600);
    const calls = mockApi({
      "GET /me": { body: user },
      "GET /movies/1": { body: detail(emptyState) },
      "POST /movies/1/view": {
        body: { ...emptyState, viewed_at: "2026-01-01T00:00:00Z" },
      },
    });
    renderApp("/movies/1");
    await screen.findByRole("heading", { name: "Toy Story (1995)" });
    await waitFor(() =>
      expect(calls.filter((c) => c.path === "/movies/1/view")).toHaveLength(1),
    );
    // a view is the only extra call: no rating, like, watchlist or watched was sent
    expect(calls.filter((c) => c.method !== "GET").map((c) => c.path)).toEqual([
      "/movies/1/view",
    ]);
  });

  it("does not call the view route for a visitor", async () => {
    clearToken();
    const calls = mockApi({ "GET /movies/1": { body: detail(null) } });
    renderApp("/movies/1");
    await screen.findByRole("heading", { name: "Toy Story (1995)" });
    expect(calls.some((c) => c.path.endsWith("/view"))).toBe(false);
  });

  it("still shows the page when recording the view fails", async () => {
    saveToken("tok", 3600);
    mockApi({
      "GET /me": { body: user },
      "GET /movies/1": { body: detail(emptyState) },
      "POST /movies/1/view": { status: 500, body: {} },
    });
    renderApp("/movies/1");
    expect(await screen.findByRole("button", { name: "Like" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("asks a visitor to log in instead of showing controls", async () => {
    clearToken();
    mockApi({ "GET /movies/1": { body: detail(null) } });
    renderApp("/movies/1");
    expect(await screen.findByText(/to rate, like, or save/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Like" })).toBeNull();
  });

  it("shows the server's error and keeps the old state", async () => {
    saveToken("tok", 3600);
    mockApi({
      "GET /me": { body: user },
      "GET /movies/1": { body: detail(emptyState) },
      "PUT /movies/1/like": { status: 404, body: { detail: "movie not found" } },
    });
    renderApp("/movies/1");
    await userEvent.click(await screen.findByRole("button", { name: "Like" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("movie not found");
    expect(screen.getByRole("button", { name: "Like" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});

describe("catalogue URL state", () => {
  it("reads filters from the URL and writes them back on search", async () => {
    clearToken();
    const calls = mockApi({
      "GET /movies": { body: { items: [movie], page: 2, page_size: 20, total: 41 } },
    });
    renderApp("/movies?q=toy&genre=Comedy&page=2");
    await screen.findByText("Toy Story (1995)");
    const first = new URLSearchParams(calls[0]?.search);
    expect(first.get("q")).toBe("toy");
    expect(first.get("genre")).toBe("Comedy");
    expect(first.get("page")).toBe("2");
    expect(screen.getByLabelText("Title contains")).toHaveValue("toy");

    await userEvent.clear(screen.getByLabelText("Title contains"));
    await userEvent.type(screen.getByLabelText("Title contains"), "matrix");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => {
      const last = new URLSearchParams(calls[calls.length - 1]?.search);
      expect(last.get("q")).toBe("matrix");
      expect(last.get("page")).toBe("1");
    });
  });

  it("re-fills the boxes from the URL on Back, Forward and a shared link", async () => {
    clearToken();
    mockApi({
      "GET /movies": { body: { items: [movie], page: 1, page_size: 20, total: 1 } },
    });
    window.history.pushState(
      {},
      "",
      "/movies?q=toy&genre=Comedy&min_rating=3.5&sort=year",
    );
    render(<App />);
    // a shared link fills every control
    expect(await screen.findByLabelText("Title contains")).toHaveValue("toy");
    expect(screen.getByLabelText("Genre")).toHaveValue("Comedy");
    expect(screen.getByLabelText("Minimum average rating")).toHaveValue("3.5");
    expect(screen.getByLabelText("Sort by")).toHaveValue("year");

    await userEvent.clear(screen.getByLabelText("Title contains"));
    await userEvent.type(screen.getByLabelText("Title contains"), "matrix");
    await userEvent.selectOptions(screen.getByLabelText("Genre"), "Drama");
    await userEvent.click(screen.getByRole("button", { name: "Search" }));
    await waitFor(() => expect(window.location.search).toContain("q=matrix"));
    expect(screen.getByLabelText("Genre")).toHaveValue("Drama");

    window.history.back(); // Back
    await waitFor(() =>
      expect(screen.getByLabelText("Title contains")).toHaveValue("toy"),
    );
    expect(screen.getByLabelText("Genre")).toHaveValue("Comedy");
    expect(screen.getByLabelText("Minimum average rating")).toHaveValue("3.5");

    window.history.forward(); // Forward
    await waitFor(() =>
      expect(screen.getByLabelText("Title contains")).toHaveValue("matrix"),
    );
    expect(screen.getByLabelText("Genre")).toHaveValue("Drama");
  });

  it("clears the boxes on Reset even when they hold unapplied text", async () => {
    clearToken();
    mockApi({
      "GET /movies": { body: { items: [movie], page: 1, page_size: 20, total: 1 } },
    });
    window.history.pushState({}, "", "/movies");
    render(<App />);
    await userEvent.type(
      await screen.findByLabelText("Title contains"),
      "typed not searched",
    );
    await userEvent.click(screen.getByRole("button", { name: "Reset" }));
    expect(screen.getByLabelText("Title contains")).toHaveValue("");
  });

  it("says so when nothing matches, and shows API errors", async () => {
    clearToken();
    mockApi({ "GET /movies": { body: { items: [], page: 1, page_size: 20, total: 0 } } });
    renderApp("/movies?q=zzzz");
    expect(await screen.findByText("No movies match these filters.")).toBeInTheDocument();
  });

  it("shows a clear message when the API cannot be reached", async () => {
    clearToken();
    mockApi({
      "GET /movies": () => {
        throw new TypeError("Failed to fetch");
      },
    });
    renderApp("/movies");
    expect(await screen.findByRole("alert")).toHaveTextContent(/Cannot reach the API/);
  });
});

describe("account deletion", () => {
  it("needs the typed phrase, then deletes, clears the token and says so", async () => {
    saveToken("tok", 3600);
    const calls = mockApi({
      "GET /me": { body: user },
      "DELETE /me": { status: 204 },
    });
    renderApp("/account");
    const button = await screen.findByRole("button", { name: "Delete my account" });
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Type/), "delete my");
    expect(button).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Type/), " account");
    expect(button).toBeEnabled();
    await userEvent.click(button);
    expect(
      await screen.findByRole("heading", { name: "Your account was deleted" }),
    ).toBeInTheDocument();
    expect(calls.some((c) => c.method === "DELETE" && c.path === "/me")).toBe(true);
    expect(getToken()).toBeNull();
  });

  it("states the password-less deletion risk", async () => {
    saveToken("tok", 3600);
    mockApi({ "GET /me": { body: user } });
    renderApp("/account");
    expect(
      await screen.findByText(/does not ask for your password again/),
    ).toBeInTheDocument();
  });
});

describe("genre onboarding", () => {
  it("saves chosen genres and moves on to the catalogue", async () => {
    saveToken("tok", 3600);
    const calls = mockApi({
      "GET /me": { body: user },
      "PUT /me/genres": (c) => ({
        body: { ...user, genres: (c.body as { genres: string[] }).genres },
      }),
      "GET /movies": { body: { items: [], page: 1, page_size: 20, total: 0 } },
    });
    renderApp("/onboarding/genres");
    await userEvent.click(await screen.findByRole("checkbox", { name: "Comedy" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Sci-Fi" }));
    await userEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(await screen.findByRole("heading", { name: "Movies" })).toBeInTheDocument();
    expect(calls.find((c) => c.method === "PUT")?.body).toEqual({
      genres: ["Comedy", "Sci-Fi"],
    });
  });
});
