import { Link } from "react-router";
import type { Movie } from "../api/types";
import { Poster } from "./Poster";

/** Average rating with a star, and how many ratings it rests on. */
export function RatingLine({ movie }: { movie: Movie }) {
  if (movie.average_rating === null) {
    return <p className="rating-line muted">No ratings yet</p>;
  }
  return (
    <p className="rating-line">
      <span className="star" aria-hidden="true">
        ★
      </span>
      <strong>{movie.average_rating.toFixed(2)}</strong>
      <span className="muted"> ({movie.rating_count} ratings)</span>
    </p>
  );
}

export function MovieCard({ movie }: { movie: Movie }) {
  return (
    <li className="card">
      <Link to={`/movies/${movie.id}`} className="card-link">
        <Poster poster={movie.poster} />
        <div className="card-body">
          <h3 className="card-title">{movie.title}</h3>
          <p className="card-genres">{movie.genres.join(" · ") || "No genres listed"}</p>
          <RatingLine movie={movie} />
        </div>
      </Link>
    </li>
  );
}
