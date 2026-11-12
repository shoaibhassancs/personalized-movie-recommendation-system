import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { clearToken, saveToken } from "../auth/tokenStore";
import { emptyState, mockApi, movie, renderApp, user } from "./helpers";

const page = { items: [movie], page: 1, page_size: 20, total: 1 };

describe("catalogue: compact filters", () => {
  it("keeps the extra filters folded away when the address does not use them", async () => {
    clearToken();
    mockApi({ "GET /movies": { body: page } });
    renderApp("/movies?q=toy&genre=Comedy");
    await screen.findByText("Toy Story (1995)");
    const more = screen.getByText("More filters").closest("details");
    expect(more).not.toHaveAttribute("open");
    // the two main boxes and the buttons are outside the folded part
    expect(more).not.toContainElement(screen.getByLabelText("Title contains"));
    expect(more).not.toContainElement(screen.getByLabelText("Genre"));
    expect(more).not.toContainElement(screen.getByRole("button", { name: "Search" }));
  });

  it("opens itself and counts the active extra filters from the address", async () => {
    clearToken();
    mockApi({ "GET /movies": { body: page } });
    renderApp("/movies?year_min=1990&sort=year");
    await screen.findByText("Toy Story (1995)");
    const summary = screen.getByText(/More filters/);
    expect(summary).toHaveTextContent("More filters (2 active)");
    expect(summary.closest("details")).toHaveAttribute("open");
    expect(screen.getByLabelText("Year from")).toHaveValue(1990);
  });
});

describe("history rows", () => {
  it("shows a poster, the title and one badge per status", async () => {
    saveToken("tok", 3600);
    mockApi({
      "GET /me": { body: user },
      "GET /me/history": {
        body: {
          items: [
            {
              movie,
              state: { ...emptyState, rating: 4.5, liked: true, watched: true },
              last_activity: "2026-01-02T00:00:00Z",
            },
            {
              movie: { ...movie, id: 2, title: "Jumanji (1995)" },
              state: emptyState,
              last_activity: "2026-01-01T00:00:00Z",
            },
          ],
          page: 1,
          page_size: 20,
          total: 2,
        },
      },
    });
    renderApp("/history");
    const first = (
      await screen.findByRole("heading", { name: "Toy Story (1995)" })
    ).closest("li")!;
    expect(within(first).getByText("Rated 4.5")).toBeInTheDocument();
    expect(within(first).getByText("Liked")).toBeInTheDocument();
    expect(within(first).getByText("Watched")).toBeInTheDocument();
    expect(within(first).getByRole("link")).toHaveAttribute("href", "/movies/1");
    const second = screen.getByRole("heading", { name: "Jumanji (1995)" }).closest("li")!;
    expect(within(second).getByText("Viewed")).toBeInTheDocument();
  });
});

describe("account danger zone", () => {
  it("keeps the deletion controls inside their own labelled region", async () => {
    saveToken("tok", 3600);
    mockApi({ "GET /me": { body: user } });
    renderApp("/account");
    const zone = await screen.findByRole("region", { name: "Delete your account" });
    expect(
      within(zone).getByRole("button", { name: "Delete my account" }),
    ).toBeDisabled();
    expect(within(zone).getByLabelText(/Type/)).toBeInTheDocument();
    // the ordinary save button is not part of the danger zone
    expect(zone).not.toContainElement(
      screen.getByRole("button", { name: "Save changes" }),
    );
  });
});

describe("header and local-only warning", () => {
  it("shows a small pill at the top and the full warning in the footer", async () => {
    clearToken();
    mockApi({ "GET /movies": { body: page } });
    renderApp("/movies");
    await screen.findByText("Toy Story (1995)");
    expect(screen.getByText("Local build")).toBeInTheDocument();
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent(/do not expose it publicly/i);
    expect(footer).toHaveTextContent(/no rate\s+limiting or HTTPS/);
  });

  it("shows the MovieLens attribution, citation and non-endorsement in the footer", async () => {
    clearToken();
    mockApi({ "GET /movies": { body: page } });
    renderApp("/movies");
    await screen.findByText("Toy Story (1995)");
    const footer = screen.getByRole("contentinfo");
    expect(footer).toHaveTextContent(/MovieLens \(GroupLens, non-commercial\)/);
    expect(footer).toHaveTextContent(/Not endorsed by GroupLens/);
    expect(footer).toHaveTextContent(/Harper and J\. A\. Konstan \(2015\)/);
    expect(footer).toHaveTextContent(/The MovieLens Datasets: History and\s+Context/);
    expect(footer).toHaveTextContent("https://doi.org/10.1145/2827872");
  });

  it("labels the account link and offers Log out as a button", async () => {
    saveToken("tok", 3600);
    mockApi({ "GET /me": { body: user }, "GET /movies": { body: page } });
    renderApp("/movies");
    expect(await screen.findByRole("link", { name: /Account · Ada/ })).toHaveAttribute(
      "href",
      "/account",
    );
    expect(screen.getByRole("button", { name: "Log out" })).toBeInTheDocument();
  });
});

describe("on/off states", () => {
  it("marks every active toggle with aria-pressed and a check, and leaves inactive ones plain", async () => {
    saveToken("tok", 3600);
    mockApi({
      "GET /me": { body: user },
      "GET /movies/1": {
        body: { ...movie, tags: [], me: { ...emptyState, rating: 3.5, liked: true } },
      },
      "POST /movies/1/view": { body: emptyState },
    });
    renderApp("/movies/1");
    const liked = await screen.findByRole("button", { name: "Liked" });
    expect(liked).toHaveAttribute("aria-pressed", "true");
    expect(liked).toHaveTextContent("✓");
    expect(liked).toHaveClass("toggle");
    const watch = screen.getByRole("button", { name: "Add to watchlist" });
    expect(watch).toHaveAttribute("aria-pressed", "false");
    expect(watch).not.toHaveTextContent("✓");
    expect(screen.getByRole("button", { name: "3.5 stars" })).toHaveClass("toggle");
    expect(screen.getByRole("button", { name: "3.5 stars" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "4 stars" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });
});

describe("genre chips", () => {
  it("lets the chosen genres be found by their checked state", async () => {
    saveToken("tok", 3600);
    mockApi({ "GET /me": { body: { ...user, genres: ["Comedy"] } } });
    renderApp("/onboarding/genres");
    const comedy = await screen.findByRole("checkbox", { name: "Comedy" });
    expect(comedy).toBeChecked();
    expect(comedy.closest("label")).toHaveClass("chip");
    expect(screen.getByRole("checkbox", { name: "Drama" })).not.toBeChecked();
  });
});
