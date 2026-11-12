import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/endpoints";
import { ErrorNotice } from "../components/Notice";
import { MovieCard } from "../components/MovieCard";
import { Pager } from "../components/Pager";
import { Poster } from "../components/Poster";
import { useLoad } from "../components/useLoad";

export function WatchlistPage() {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useLoad(`w${page}`, (s) => api.watchlist(page, s));
  return (
    <section>
      <h1>Your watchlist</h1>
      {error && <ErrorNotice>{error}</ErrorNotice>}
      {loading && <p role="status">Loading…</p>}
      {data && data.items.length === 0 && (
        <p>
          Nothing here yet. Open a movie from <Link to="/movies">the catalogue</Link> and
          add it.
        </p>
      )}
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
            onPage={setPage}
          />
        </>
      )}
    </section>
  );
}

function badges(s: {
  rating: number | null;
  liked: boolean;
  disliked: boolean;
  watchlist: boolean;
  watched: boolean;
}): string[] {
  const parts: string[] = [];
  if (s.rating !== null) parts.push(`Rated ${s.rating}`);
  if (s.liked) parts.push("Liked");
  if (s.disliked) parts.push("Disliked");
  if (s.watchlist) parts.push("On watchlist");
  if (s.watched) parts.push("Watched");
  return parts.length ? parts : ["Viewed"];
}

export function HistoryPage() {
  const [page, setPage] = useState(1);
  const { data, error, loading } = useLoad(`h${page}`, (s) => api.history(page, s));
  return (
    <section>
      <h1>Your history</h1>
      <p className="muted small">Movies you rated or marked, newest activity first.</p>
      {error && <ErrorNotice>{error}</ErrorNotice>}
      {loading && <p role="status">Loading…</p>}
      {data && data.items.length === 0 && <p>No activity yet.</p>}
      {data && data.items.length > 0 && (
        <>
          <ul className="history">
            {data.items.map(({ movie, state, last_activity }) => (
              <li key={movie.id} className="card">
                <Link to={`/movies/${movie.id}`} className="card-link">
                  <Poster poster={movie.poster} />
                  <div>
                    <h3>{movie.title}</h3>
                    <p className="badges">
                      {badges(state).map((b) => (
                        <span key={b} className="badge">
                          {b}
                        </span>
                      ))}
                    </p>
                    <p className="muted small">
                      {new Date(last_activity).toLocaleDateString()}
                    </p>
                  </div>
                </Link>
              </li>
            ))}
          </ul>
          <Pager
            page={data.page}
            pageSize={data.page_size}
            total={data.total}
            onPage={setPage}
          />
        </>
      )}
    </section>
  );
}
