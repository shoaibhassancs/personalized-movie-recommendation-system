import { Link } from "react-router";
import type { Movie } from "../api/types";
import { Poster } from "./Poster";

export function ratingText(movie: Movie): string {
  if (movie.average_rating === null) return "No ratings yet";
  return `★ ${movie.average_rating.toFixed(2)} (${movie.rating_count} ratings)`;
}

export function MovieCard({ movie }: { movie: Movie }) {
  return (
    <li className="card">
      <Link to={`/movies/${movie.id}`} className="card-link">
        <Poster poster={movie.poster} />
        <div>
          <h3>{movie.title}</h3>
          <p className="muted">{movie.genres.join(" · ") || "No genres listed"}</p>
          <p className="muted">{ratingText(movie)}</p>
        </div>
      </Link>
    </li>
  );
}
