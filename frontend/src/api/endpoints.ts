import { request } from "./client";
import type {
  FlagKind,
  HistoryPage,
  MovieDetail,
  MoviePage,
  MovieState,
  TokenOut,
  User,
} from "./types";

export const api = {
  register: (email: string, password: string, display_name: string) =>
    request<User>("/auth/register", {
      method: "POST",
      body: { email, password, display_name },
    }),
  login: (email: string, password: string) =>
    request<TokenOut>("/auth/login", { method: "POST", body: { email, password } }),
  me: (signal?: AbortSignal) => request<User>("/me", { signal }),
  updateName: (display_name: string) =>
    request<User>("/me", { method: "PUT", body: { display_name } }),
  setGenres: (genres: string[]) =>
    request<User>("/me/genres", { method: "PUT", body: { genres } }),
  deleteAccount: () => request<void>("/me", { method: "DELETE" }),
  movies: (query: Record<string, string | number | undefined>, signal?: AbortSignal) =>
    request<MoviePage>("/movies", { query, signal }),
  movie: (id: number, signal?: AbortSignal) =>
    request<MovieDetail>(`/movies/${id}`, { signal }),
  setRating: (id: number, rating: number) =>
    request<MovieState>(`/movies/${id}/rating`, { method: "PUT", body: { rating } }),
  clearRating: (id: number) =>
    request<MovieState>(`/movies/${id}/rating`, { method: "DELETE" }),
  setFlag: (id: number, kind: FlagKind) =>
    request<MovieState>(`/movies/${id}/${kind}`, { method: "PUT" }),
  clearFlag: (id: number, kind: FlagKind) =>
    request<MovieState>(`/movies/${id}/${kind}`, { method: "DELETE" }),
  view: (id: number) => request<MovieState>(`/movies/${id}/view`, { method: "POST" }),
  watchlist: (page: number, signal?: AbortSignal) =>
    request<MoviePage>("/me/watchlist", { query: { page }, signal }),
  history: (page: number, signal?: AbortSignal) =>
    request<HistoryPage>("/me/history", { query: { page }, signal }),
};
