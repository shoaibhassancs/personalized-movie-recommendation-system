import type { MovieState } from "../api/types";

/** Small status labels from the person's own state for a movie. `fallback` is shown
 *  when there is nothing else to say (History uses "Viewed"). */
export function stateLabels(s: MovieState): string[] {
  const parts: string[] = [];
  if (s.rating !== null) parts.push(`Rated ${s.rating}`);
  if (s.liked) parts.push("Liked");
  if (s.disliked) parts.push("Disliked");
  if (s.watchlist) parts.push("On watchlist");
  if (s.watched) parts.push("Watched");
  return parts;
}

export function StateBadges({
  state,
  fallback,
}: {
  state: MovieState;
  fallback?: string;
}) {
  const labels = stateLabels(state);
  const shown = labels.length ? labels : fallback ? [fallback] : [];
  if (shown.length === 0) return null;
  return (
    <p className="badges">
      {shown.map((label) => (
        <span key={label} className="badge">
          {label}
        </span>
      ))}
    </p>
  );
}
