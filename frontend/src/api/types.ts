/** Hand-written to match src/pmrs/api/schemas.py. Only what 5A uses. */
export interface Poster {
  initials: string;
  hue: number;
}
export interface Movie {
  id: number;
  title: string;
  year: number | null;
  genres: string[];
  average_rating: number | null;
  rating_count: number;
  poster: Poster;
}
export interface MovieState {
  rating: number | null;
  liked: boolean;
  disliked: boolean;
  watchlist: boolean;
  watched: boolean;
  viewed_at: string | null;
}
export interface MovieDetail extends Movie {
  tags: string[];
  me: MovieState | null;
}
export interface MoviePage {
  items: Movie[];
  page: number;
  page_size: number;
  total: number;
}
export interface HistoryItem {
  movie: Movie;
  state: MovieState;
  last_activity: string;
}
export interface HistoryPage {
  items: HistoryItem[];
  page: number;
  page_size: number;
  total: number;
}
export interface User {
  id: number;
  email: string;
  display_name: string;
  genres: string[];
  created_at: string;
}
export interface TokenOut {
  access_token: string;
  token_type: string;
  expires_in: number;
}
export type FlagKind = "like" | "dislike" | "watchlist" | "watched";

/** Phase 5B: recommendations, dashboard, analytics (src/pmrs/api/schemas.py). */
export type Strategy = "hybrid" | "popularity" | "content" | "item_knn" | "svd";

export interface RecommendationItem {
  movie: Movie;
  score: number | null; // units of score_kind; not comparable across methods
  explanation: string;
  source: string;
  state: MovieState;
}
export interface RecommendationsOut {
  strategy: string;
  branch: string | null; // hybrid only: no_ratings, few_ratings, many_ratings
  branch_reason: string;
  score_kind: string;
  rating_count: number;
  items: RecommendationItem[];
  notes: string[];
  served_events_logged: number; // "served" events: returned by the API, not seen
  model_notice: string;
}
export interface TrendingItem {
  movie: Movie;
  interactions: number;
}
export interface TrendingOut {
  source: string; // "app_activity" or "dataset_latest_period"
  window_start: string;
  window_end: string;
  window_days: number;
  note: string;
  items: TrendingItem[];
}
export interface DashboardOut {
  recommended: RecommendationsOut;
  trending: TrendingOut;
  popular: Movie[];
  recent_releases: Movie[];
  genres: string[];
  watchlist: MoviePage;
  activity: HistoryPage;
}
export interface CountSplit {
  total: number;
  movielens: number;
  app: number;
}
export interface SummaryOut {
  movies: number;
  users: CountSplit;
  ratings: CountSplit;
  interactions: Record<string, number>;
  recommendation_events: Record<string, number>;
  note: string;
}
export interface RatingBucket {
  rating: number;
  total: number;
  movielens: number;
  app: number;
}
export interface RatingDistributionOut {
  buckets: RatingBucket[];
  note: string;
}
export interface StrategyEngagement {
  strategy: string;
  served: number;
  acted: number;
  acted_per_served: number | null;
  users: number;
}
export interface EngagementOut {
  served: number;
  acted: number;
  users: number;
  by_strategy: StrategyEngagement[];
  note: string;
}
