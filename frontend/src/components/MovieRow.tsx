import type { ReactNode } from "react";
import { Link } from "react-router";
import type { Movie } from "../api/types";
import { Poster } from "./Poster";

/** A compact line for dashboard and analytics lists: poster, title, one detail line. */
export function MovieRow({ movie, children }: { movie: Movie; children?: ReactNode }) {
  const meta = [movie.year ?? null, movie.genres.slice(0, 2).join(" · ") || null]
    .filter((x) => x !== null)
    .join(" · ");
  return (
    <li className="row-item">
      <Link to={`/movies/${movie.id}`} className="row-link">
        <Poster poster={movie.poster} />
        <span className="row-text">
          <span className="row-title">{movie.title}</span>
          {meta && <span className="muted small">{meta}</span>}
          {children}
        </span>
      </Link>
    </li>
  );
}
