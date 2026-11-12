import { useState } from "react";
import { ApiError } from "../api/client";
import { api } from "../api/endpoints";
import type { FlagKind, MovieState } from "../api/types";
import { ErrorNotice } from "./Notice";
import { StarRating } from "./StarRating";

interface Props {
  movieId: number;
  state: MovieState;
  onState: (state: MovieState) => void;
}

const FLAGS: { kind: FlagKind; on: string; off: string; field: keyof MovieState }[] = [
  { kind: "like", on: "Liked", off: "Like", field: "liked" },
  { kind: "dislike", on: "Disliked", off: "Dislike", field: "disliked" },
  { kind: "watchlist", on: "On watchlist", off: "Add to watchlist", field: "watchlist" },
  { kind: "watched", on: "Watched", off: "Mark as watched", field: "watched" },
];

/** Every button shows what the server last returned. Like and dislike exclude each
 *  other because the server removes the other one (D-038); we just display its answer. */
export function MovieControls({ movieId, state, onState }: Props) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<MovieState>) {
    setBusy(true);
    setError(null);
    try {
      onState(await action());
    } catch (e) {
      setError(
        e instanceof ApiError ? e.message : "That did not work. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={busy ? "controls busy" : "controls"}>
      <StarRating
        value={state.rating}
        disabled={busy}
        onChange={(v) => run(() => api.setRating(movieId, v))}
        onClear={() => run(() => api.clearRating(movieId))}
      />
      <div className="row" role="group" aria-label="Your lists">
        {FLAGS.map(({ kind, on, off, field }) => {
          const active = state[field] === true;
          return (
            <button
              key={kind}
              type="button"
              className="toggle"
              aria-pressed={active}
              disabled={busy}
              onClick={() =>
                run(() =>
                  active ? api.clearFlag(movieId, kind) : api.setFlag(movieId, kind),
                )
              }
            >
              {active && <span aria-hidden="true">✓ </span>}
              {active ? on : off}
            </button>
          );
        })}
      </div>
      <p className="muted small">
        Filled buttons are on. Liking a movie removes a dislike, and the other way round.
      </p>
      {error && <ErrorNotice>{error}</ErrorNotice>}
    </div>
  );
}
