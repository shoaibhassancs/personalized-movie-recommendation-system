import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { api } from "../api/endpoints";
import { ErrorNotice } from "../components/Notice";
import { MovieCard } from "../components/MovieCard";
import { Pager } from "../components/Pager";
import { useLoad } from "../components/useLoad";
import { GENRES, PAGE_SIZE } from "../constants";

const SORTS = ["title", "year", "rating", "popularity"] as const;
const FILTERS = [
  "q",
  "genre",
  "year_min",
  "year_max",
  "min_rating",
  "sort",
  "order",
] as const;

/** The filters kept under "More filters". */
const MORE = ["year_min", "year_max", "min_rating", "sort", "order"] as const;

function FilterForm({
  initial,
  onApply,
}: {
  initial: Record<string, string>;
  onApply: (values: Record<string, string>) => void;
}) {
  const blank = Object.fromEntries(FILTERS.map((k) => [k, ""]));
  const [form, setForm] = useState(initial);
  const moreActive = MORE.filter((k) => (initial[k] ?? "") !== "").length;
  const set = (name: string, value: string) => setForm((f) => ({ ...f, [name]: value }));
  function submit(event: FormEvent) {
    event.preventDefault();
    onApply(form);
  }
  return (
    <form className="filters" onSubmit={submit} role="search">
      <div className="filters-main">
        <label>
          Title contains
          <input
            value={form.q}
            onChange={(e) => set("q", e.target.value)}
            maxLength={100}
          />
        </label>
        <label>
          Genre
          <select value={form.genre} onChange={(e) => set("genre", e.target.value)}>
            <option value="">Any</option>
            {GENRES.map((g) => (
              <option key={g}>{g}</option>
            ))}
          </select>
        </label>
        <div className="row filters-actions">
          <button type="submit">Search</button>
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setForm(blank);
              onApply({});
            }}
          >
            Reset
          </button>
        </div>
      </div>
      {/* Opens by itself when the address already uses one of these filters. */}
      <details className="more-filters" open={moreActive > 0}>
        <summary>More filters{moreActive > 0 ? ` (${moreActive} active)` : ""}</summary>
        <div className="more-grid">
          <label>
            Year from
            <input
              type="number"
              min={1800}
              max={2100}
              value={form.year_min}
              onChange={(e) => set("year_min", e.target.value)}
            />
          </label>
          <label>
            Year to
            <input
              type="number"
              min={1800}
              max={2100}
              value={form.year_max}
              onChange={(e) => set("year_max", e.target.value)}
            />
          </label>
          <label>
            Minimum average rating
            <select
              value={form.min_rating}
              onChange={(e) => set("min_rating", e.target.value)}
            >
              <option value="">Any</option>
              {[1, 2, 3, 3.5, 4, 4.5].map((v) => (
                <option key={v}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            Sort by
            <select value={form.sort} onChange={(e) => set("sort", e.target.value)}>
              <option value="">Title (default)</option>
              {SORTS.filter((s) => s !== "title").map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label>
            Order
            <select value={form.order} onChange={(e) => set("order", e.target.value)}>
              <option value="">Default for sort</option>
              <option value="asc">Ascending</option>
              <option value="desc">Descending</option>
            </select>
          </label>
        </div>
      </details>
    </form>
  );
}

/** All search state lives in the URL, so back, refresh and sharing a link all work. */
export function CataloguePage() {
  const [params, setParams] = useSearchParams();
  const page = Math.max(1, Number(params.get("page")) || 1);
  const query: Record<string, string | number | undefined> = {
    page,
    page_size: PAGE_SIZE,
  };
  for (const key of FILTERS) query[key] = params.get(key) ?? undefined;
  const key = JSON.stringify(query);
  const { data, error, loading } = useLoad(key, (signal) => api.movies(query, signal));

  const initial = Object.fromEntries(FILTERS.map((k) => [k, params.get(k) ?? ""]));
  // Remounting the form when the filters in the URL change (Back, Forward, a shared
  // link, Reset) re-fills the boxes from the URL. The page number is not part of the key.
  const formKey = JSON.stringify(initial);

  function apply(values: Record<string, string>) {
    const next = new URLSearchParams();
    for (const name of FILTERS) {
      const value = (values[name] ?? "").trim();
      if (value) next.set(name, value);
    }
    setParams(next);
  }
  function goto(next: number) {
    const copy = new URLSearchParams(params);
    copy.set("page", String(next));
    setParams(copy);
    window.scrollTo?.({ top: 0 });
  }

  return (
    <section>
      <h1>Movies</h1>
      <FilterForm key={formKey} initial={initial} onApply={apply} />
      <p className="muted small">
        Ratings combine the MovieLens dataset and ratings made in this app. A rating
        filter or sort only counts movies with at least 5 ratings.
      </p>
      {error && <ErrorNotice>{error}</ErrorNotice>}
      {loading && <p role="status">Loading movies…</p>}
      {data && data.items.length === 0 && <p>No movies match these filters.</p>}
      {data && data.items.length > 0 && (
        <>
          <ul className="cards">
            {data.items.map((m) => (
              <MovieCard key={m.id} movie={m} />
            ))}
          </ul>
          <Pager
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            onPage={goto}
          />
        </>
      )}
    </section>
  );
}
