import type { ReactNode } from "react";
import { Link } from "react-router";
import { api } from "../api/endpoints";
import type { TrendingOut } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { MovieRow } from "../components/MovieRow";
import { ErrorNotice } from "../components/Notice";
import { RecommendationList } from "../components/RecommendationList";
import {
  BranchBanner,
  ModelNotice,
  RecommendationNotes,
} from "../components/RecommendationNotices";
import { StateBadges } from "../components/StateBadges";
import { useServed } from "../served";

function date(value: string): string {
  return new Date(value).toLocaleDateString();
}

/** Where the trending list comes from, in words. The API's own note follows verbatim. */
export function trendingSource(t: TrendingOut): string {
  const span = `${date(t.window_start)} to ${date(t.window_end)}`;
  if (t.source === "app_activity") {
    return `Activity by registered users of this app in the last ${t.window_days} days (${span}).`;
  }
  if (t.source === "dataset_latest_period") {
    return `MovieLens fallback: the most-rated movies in the final ${t.window_days} days of the MovieLens data (${span}). This is not recent activity in this app, and it does not end today.`;
  }
  return `Source: ${t.source} (${span}).`;
}

function Panel({
  id,
  title,
  children,
}: {
  id: string;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="panel" aria-labelledby={id}>
      <h2 id={id}>{title}</h2>
      {children}
    </section>
  );
}

/** Opening the dashboard makes one request, which includes one serving of ten hybrid
 *  suggestions (ten "served" events). It is not repeated by React's development mode. */
export function DashboardPage() {
  const { user } = useAuth();
  const { data, error, loading } = useServed(`dashboard:${user?.id}`, () =>
    api.dashboard(),
  );

  return (
    <section>
      <h1>Dashboard{user ? `: ${user.display_name}` : ""}</h1>
      {error && <ErrorNotice>{error}</ErrorNotice>}
      {loading && <p role="status">Loading your dashboard…</p>}
      {data && (
        <div className="dash-grid">
          <div className="dash-wide">
            <Panel id="dash-rec" title="Suggested for you">
              <BranchBanner rec={data.recommended} />
              <RecommendationNotes notes={data.recommended.notes} />
              {data.recommended.items.length === 0 ? (
                <p>No suggestions to show right now.</p>
              ) : (
                <RecommendationList
                  items={data.recommended.items}
                  scoreKind={data.recommended.score_kind}
                />
              )}
              <p className="small">
                <Link to="/recommendations">Compare other methods →</Link> Opening this
                page made the API serve {data.recommended.served_events_logged} of these
                movies (&quot;served&quot; means returned, not seen).
              </p>
              <ModelNotice text={data.recommended.model_notice} />
            </Panel>
          </div>

          <Panel id="dash-trending" title="Trending">
            <p className="muted small">{trendingSource(data.trending)}</p>
            <p className="muted small">{data.trending.note}</p>
            {data.trending.items.length === 0 ? (
              <p>Nothing to show.</p>
            ) : (
              <ol className="rows">
                {data.trending.items.map(({ movie, interactions }) => (
                  <MovieRow key={movie.id} movie={movie}>
                    <span className="muted small">
                      {interactions} interactions in the window
                    </span>
                  </MovieRow>
                ))}
              </ol>
            )}
          </Panel>

          <Panel id="dash-popular" title="Popular">
            <p className="muted small">
              Most-rated movies, over every rating in the database (MovieLens and this
              app).
            </p>
            <ol className="rows">
              {data.popular.map((movie) => (
                <MovieRow key={movie.id} movie={movie}>
                  <span className="muted small">{movie.rating_count} ratings</span>
                </MovieRow>
              ))}
            </ol>
          </Panel>

          <Panel id="dash-recent" title="Recent releases">
            <p className="muted small">
              The newest release years in the catalogue, not the newest additions.
            </p>
            <ol className="rows">
              {data.recent_releases.map((movie) => (
                <MovieRow key={movie.id} movie={movie} />
              ))}
            </ol>
          </Panel>

          <Panel id="dash-genres" title="Your genres">
            {data.genres.length === 0 ? (
              <p>
                You have not chosen any.{" "}
                <Link to="/account">Add some in your account.</Link>
              </p>
            ) : (
              <>
                <ul className="badges">
                  {data.genres.map((g) => (
                    <li key={g} className="badge">
                      {g}
                    </li>
                  ))}
                </ul>
                <p className="small">
                  <Link to="/account">Change them</Link>
                </p>
              </>
            )}
          </Panel>

          <Panel id="dash-watchlist" title="Your watchlist">
            {data.watchlist.items.length === 0 ? (
              <p>
                Nothing yet. Open a movie from <Link to="/movies">the catalogue</Link> and
                add it.
              </p>
            ) : (
              <>
                <ol className="rows">
                  {data.watchlist.items.map((movie) => (
                    <MovieRow key={movie.id} movie={movie} />
                  ))}
                </ol>
                <p className="small">
                  <Link to="/watchlist">See all {data.watchlist.total}</Link>
                </p>
              </>
            )}
          </Panel>

          <Panel id="dash-activity" title="Recent activity">
            {data.activity.items.length === 0 ? (
              <p>No activity yet.</p>
            ) : (
              <>
                <ol className="rows">
                  {data.activity.items.map(({ movie, state, last_activity }) => (
                    <MovieRow key={movie.id} movie={movie}>
                      <StateBadges state={state} fallback="Viewed" />
                      <span className="muted small">{date(last_activity)}</span>
                    </MovieRow>
                  ))}
                </ol>
                <p className="small">
                  <Link to="/history">See all history</Link>
                </p>
              </>
            )}
          </Panel>
        </div>
      )}
    </section>
  );
}
