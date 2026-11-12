import { useEffect } from "react";
import { Link, useParams } from "react-router";
import { api } from "../api/endpoints";
import { useAuth } from "../auth/AuthContext";
import { MovieControls } from "../components/MovieControls";
import { ErrorNotice, InfoNotice } from "../components/Notice";
import { Poster } from "../components/Poster";
import { useLoad } from "../components/useLoad";
import { ratingText } from "../components/MovieCard";
import type { MovieDetail, MovieState } from "../api/types";

export function MovieDetailPage() {
  const id = Number(useParams().id);
  const { status } = useAuth();
  // reload when the login state changes so `me` appears or disappears
  const { data, error, loading, setData } = useLoad<MovieDetail>(
    `${id}:${status}`,
    (signal) => api.movie(id, signal),
  );

  // Opening the page records a "viewed" interaction for a logged-in person. The API
  // does not treat a view as an explicit action, so it logs no "acted" event (D-042).
  // Best effort: a failure here must not break the page. Repeats only refresh the time.
  useEffect(() => {
    if (status === "authenticated" && Number.isInteger(id) && id > 0) {
      api.view(id).catch(() => undefined);
    }
  }, [id, status]);

  if (!Number.isInteger(id) || id < 1)
    return <ErrorNotice>That is not a movie link.</ErrorNotice>;
  if (loading || status === "loading") return <p role="status">Loading movie…</p>;
  if (error) return <ErrorNotice>{error}</ErrorNotice>;
  if (!data) return null;
  const movie = data;
  const setState = (me: MovieState) => setData({ ...movie, me });

  return (
    <article className="detail">
      <Link to="/movies">← All movies</Link>
      <div className="detail-head">
        <Poster poster={movie.poster} large />
        <div>
          <h1>{movie.title}</h1>
          <p className="muted">{movie.genres.join(" · ") || "No genres listed"}</p>
          <p>{ratingText(movie)}</p>
          <p className="muted small">
            Average and count include MovieLens ratings and ratings made in this app.
          </p>
        </div>
      </div>
      {movie.tags.length > 0 && (
        <p>
          <strong>Tags:</strong> {movie.tags.join(", ")}
        </p>
      )}
      {movie.me ? (
        <MovieControls movieId={movie.id} state={movie.me} onState={setState} />
      ) : (
        <InfoNotice>
          <Link to="/login" state={{ from: `/movies/${movie.id}` }}>
            Log in
          </Link>{" "}
          to rate, like, or save this movie.
        </InfoNotice>
      )}
    </article>
  );
}
