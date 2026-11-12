import { api } from "../api/endpoints";
import type {
  EngagementOut,
  Movie,
  RatingDistributionOut,
  SummaryOut,
} from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { BarChart, DataTable } from "../components/BarChart";
import { MovieRow } from "../components/MovieRow";
import { ErrorNotice, InfoNotice } from "../components/Notice";
import { sourceLabel } from "../components/RecommendationList";
import { useServed } from "../served";

const KINDS: Record<string, string> = {
  like: "Likes",
  dislike: "Dislikes",
  watchlist: "On a watchlist",
  watched: "Marked watched",
  viewed: "Movies opened (viewed)",
};

/** Login-only (the route guard and the API both require it). Aggregates only. Numbers
 *  from the imported MovieLens users and from this app's registered users are always
 *  shown in separate columns and never added together as if they were one audience. */
export function AnalyticsPage() {
  const { user } = useAuth();
  const { data, error, loading } = useServed<Data>(`analytics:${user?.id}`, () =>
    Promise.all([
      api.analyticsSummary(),
      api.analyticsPopular(10),
      api.analyticsRatings(),
      api.analyticsEngagement(),
    ]),
  );

  return (
    <section>
      <h1>Analytics</h1>
      <InfoNotice>
        <strong>Small numbers, handle with care.</strong> The app figures come from the
        few people who registered in this local app. Every logged-in person sees these
        totals, and with very few users an app total can come close to describing one
        person.
      </InfoNotice>
      {error && <ErrorNotice>{error}</ErrorNotice>}
      {loading && <p role="status">Loading analytics…</p>}
      {data && <Report data={data} />}
    </section>
  );
}

type Data = [SummaryOut, Movie[], RatingDistributionOut, EngagementOut];

function Report({ data }: { data: Data }) {
  const [summary, popular, ratings, engagement] = data;
  return (
    <div className="stack">
      <section className="panel" aria-labelledby="an-summary">
        <h2 id="an-summary">Totals</h2>
        <DataTable
          caption="Users and ratings: MovieLens (historical) and app (registered) are separate"
          head={["", "All", "MovieLens (historical data)", "This app (registered users)"]}
          rows={[
            ["Users", summary.users.total, summary.users.movielens, summary.users.app],
            [
              "Ratings",
              summary.ratings.total,
              summary.ratings.movielens,
              summary.ratings.app,
            ],
          ]}
        />
        <p className="muted small">
          Movies in the catalogue: {summary.movies.toLocaleString()}.
        </p>
        <p className="muted small">{summary.note}</p>
        <h3>Activity in this app only</h3>
        <DataTable
          caption="App interactions by kind"
          head={["Kind", "Count"]}
          rows={Object.entries(summary.interactions).map(([k, v]) => [KINDS[k] ?? k, v])}
        />
      </section>

      <section className="panel" aria-labelledby="an-popular">
        <h2 id="an-popular">Most-rated movies</h2>
        <p className="muted small">
          Counted over every rating in the database, MovieLens and this app together.
        </p>
        <ol className="rows">
          {popular.map((movie) => (
            <MovieRow key={movie.id} movie={movie}>
              <span className="muted small">
                {movie.rating_count.toLocaleString()} ratings
              </span>
            </MovieRow>
          ))}
        </ol>
      </section>

      <section className="panel" aria-labelledby="an-dist">
        <h2 id="an-dist">Ratings distribution</h2>
        <p className="muted small">{ratings.note}</p>
        <div className="chart-pair">
          <BarChart
            title="MovieLens ratings by half-star value"
            unit="ratings"
            bars={ratings.buckets.map((b) => ({
              label: `${b.rating} ★`,
              value: b.movielens,
            }))}
          />
          <BarChart
            title="App ratings by half-star value (its own scale)"
            unit="ratings"
            bars={ratings.buckets.map((b) => ({ label: `${b.rating} ★`, value: b.app }))}
          />
        </div>
        <DataTable
          caption="Ratings at each half-star value"
          head={["Rating", "All", "MovieLens", "This app"]}
          rows={ratings.buckets.map((b) => [
            `${b.rating} ★`,
            b.total,
            b.movielens,
            b.app,
          ])}
        />
      </section>

      <section className="panel" aria-labelledby="an-engagement">
        <h2 id="an-engagement">Recommendations served and acted on</h2>
        <p>{engagement.note}</p>
        <p className="muted small">
          These are descriptive counts from this app only. They have no comparison group,
          so they do not show that recommendations worked, and &ldquo;acted per
          served&rdquo; is not a conversion rate.
        </p>
        {engagement.served === 0 ? (
          <p>No recommendations have been served yet, so there is nothing to count.</p>
        ) : (
          <>
            <div className="chart-pair">
              <BarChart
                title="Movies served, by method"
                unit="served"
                bars={engagement.by_strategy.map((s) => ({
                  label: sourceLabel(s.strategy),
                  value: s.served,
                }))}
              />
              <BarChart
                title="Acted on after being served, by method"
                unit="acted"
                bars={engagement.by_strategy.map((s) => ({
                  label: sourceLabel(s.strategy),
                  value: s.acted,
                }))}
              />
            </div>
            <DataTable
              caption="Served and acted counts by method"
              head={[
                "Method",
                "Served",
                "Acted",
                "Acted per served (descriptive)",
                "People",
              ]}
              rows={[
                ...engagement.by_strategy.map((s) => [
                  sourceLabel(s.strategy),
                  s.served,
                  s.acted,
                  s.acted_per_served === null ? "n/a" : s.acted_per_served.toFixed(2),
                  s.users,
                ]),
                [
                  "All methods",
                  engagement.served,
                  engagement.acted,
                  "",
                  engagement.users,
                ],
              ]}
            />
          </>
        )}
      </section>
    </div>
  );
}
