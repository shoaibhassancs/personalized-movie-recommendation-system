import { Link } from "react-router";
import type { RecommendationItem } from "../api/types";
import { RatingLine } from "./MovieCard";
import { Poster } from "./Poster";
import { StateBadges } from "./StateBadges";

const SOURCE_LABELS: Record<string, string> = {
  popularity: "Popularity",
  content: "Content (genres and tags)",
  item_knn: "Item neighbours",
  svd: "SVD",
  hybrid: "Hybrid",
};

/** "item_knn" -> a readable label; unknown sources are tidied, not hidden. */
export function sourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, " ");
}

/** Suggested movies. Each card links to the movie page (no inline actions). Raw scores
 *  are hidden by default; the disclosure names their kind and says they cannot be
 *  compared between methods. */
export function RecommendationList({
  items,
  scoreKind,
}: {
  items: RecommendationItem[];
  scoreKind: string;
}) {
  const scored = items.filter((i) => i.score !== null);
  return (
    <>
      <ol className="cards rec-list">
        {items.map(({ movie, explanation, source, state }, index) => (
          <li key={movie.id} className="card">
            <Link to={`/movies/${movie.id}`} className="card-link rec-link">
              <Poster poster={movie.poster} />
              <div className="card-body">
                <p className="muted small rec-rank">Suggestion {index + 1}</p>
                <h3 className="card-title">{movie.title}</h3>
                <p className="card-genres">
                  {movie.genres.join(" · ") || "No genres listed"}
                </p>
                <RatingLine movie={movie} />
                <p className="rec-why">{explanation}</p>
                <p className="badges">
                  <span className="badge badge-source">
                    Method: {sourceLabel(source)}
                  </span>
                </p>
                <StateBadges state={state} />
              </div>
            </Link>
          </li>
        ))}
      </ol>
      {scored.length > 0 && (
        <details className="scores">
          <summary>Show raw scores</summary>
          <p className="muted small">
            Score kind: <strong>{scoreKind}</strong>. Scores come from one method and are
            not comparable with another method&apos;s. They are not a probability that you
            will like a movie.
          </p>
          <table>
            <caption className="visually-hidden">Raw scores ({scoreKind})</caption>
            <thead>
              <tr>
                <th scope="col">Movie</th>
                <th scope="col">Score ({scoreKind})</th>
              </tr>
            </thead>
            <tbody>
              {scored.map(({ movie, score }) => (
                <tr key={movie.id}>
                  <th scope="row">{movie.title}</th>
                  <td>{score?.toFixed(3)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </>
  );
}
