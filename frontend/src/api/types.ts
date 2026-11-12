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
