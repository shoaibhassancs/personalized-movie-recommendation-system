import { useState } from "react";
import { Link } from "react-router";
import { api } from "../api/endpoints";
import type { Strategy } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { ErrorNotice } from "../components/Notice";
import { RecommendationList } from "../components/RecommendationList";
import {
  BranchBanner,
  ModelNotice,
  RecommendationNotes,
} from "../components/RecommendationNotices";
import { useServed } from "../served";

const K = 10;
const METHODS: { id: Strategy; label: string; help: string; needsRatings: boolean }[] = [
  {
    id: "hybrid",
    label: "Hybrid (default)",
    help: "The app's main method. It chooses how to rank according to how many ratings you have.",
    needsRatings: false,
  },
  {
    id: "popularity",
    label: "Popularity",
    help: "The most-rated movies: the same ranking for everyone.",
    needsRatings: false,
  },
  {
    id: "content",
    label: "Content",
    help: "Movies similar to ones you rated, by genres and tags.",
    needsRatings: true,
  },
  {
    id: "item_knn",
    label: "Item neighbours",
    help: "Movies that people who rated your movies also rated similarly.",
    needsRatings: true,
  },
  {
    id: "svd",
    label: "SVD",
    help: "A latent-factor model of rating patterns.",
    needsRatings: true,
  },
];

/** The page makes one request when it is opened, and another only when the person picks a
 *  method or asks for a fresh list. Each request makes the API log one "served" event per
 *  movie returned. "Served" means returned by the API, not that anyone saw it. */
export function RecommendationsPage() {
  const { user } = useAuth();
  const [strategy, setStrategy] = useState<Strategy>("hybrid");
  const { data, error, loading, refreshing, refresh } = useServed(
    `rec:${user?.id}:${strategy}:${K}`,
    () => api.recommendations(strategy, K),
  );
  const method = METHODS.find((m) => m.id === strategy) ?? METHODS[0]!;

  return (
    <section>
      <h1>Recommendations</h1>
      <p className="muted">
        Suggestions from the app&apos;s models, fitted on the MovieLens data. Movies you
        have marked watched or disliked are left out.
      </p>

      <div className="panel method-picker">
        <label>
          Method
          <select
            value={strategy}
            onChange={(e) => setStrategy(e.target.value as Strategy)}
            disabled={refreshing}
          >
            {METHODS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
        <p className="muted small">{method.help}</p>
        {method.needsRatings && (
          <p className="muted small">
            In the offline comparison this method was only evaluated for people with many
            ratings, and it returns nothing until you have rated at least one movie. It is
            here so you can compare it with the hybrid.
          </p>
        )}
        <div className="row">
          <button
            type="button"
            className="secondary"
            onClick={refresh}
            disabled={refreshing}
          >
            {refreshing ? "Getting a new list…" : "Get a fresh list"}
          </button>
          <span className="muted small">
            A fresh list is a new request, counted as another serving. Movies you have
            since marked watched or disliked will have disappeared from it.
          </span>
        </div>
      </div>

      {error && <ErrorNotice>{error}</ErrorNotice>}
      {loading && <p role="status">Getting suggestions…</p>}
      {data && (
        <>
          <BranchBanner rec={data} />
          <RecommendationNotes notes={data.notes} />
          {data.items.length === 0 ? (
            <div className="empty">
              <p>
                <strong>No suggestions to show for this method right now.</strong>
              </p>
              {data.rating_count === 0 && method.needsRatings ? (
                <p>
                  This method needs at least one rating from you.{" "}
                  <Link to="/movies">Browse the catalogue</Link>, rate a few movies, or
                  switch to Hybrid or Popularity.
                </p>
              ) : (
                <p>
                  Everything the method ranked highly may already be marked watched or
                  disliked. Try another method.
                </p>
              )}
            </div>
          ) : (
            <>
              <p className="muted small" role="status">
                The API served {data.served_events_logged} movies in this list. Served
                means returned by the API, not that you saw them, and it is logged as a
                count, not as interest.
              </p>
              <RecommendationList items={data.items} scoreKind={data.score_kind} />
            </>
          )}
          <ModelNotice text={data.model_notice} />
        </>
      )}
    </section>
  );
}
