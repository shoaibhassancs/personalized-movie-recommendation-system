/** The 19 real MovieLens genres (the "(no genres listed)" marker is not a genre).
 *  There is no genres endpoint (owner decision: a frontend constant). The API still
 *  checks every genre and answers 422 for an unknown one. Taken from
 *  data/raw/ml-latest-small/movies.csv. */
export const GENRES = [
  "Action",
  "Adventure",
  "Animation",
  "Children",
  "Comedy",
  "Crime",
  "Documentary",
  "Drama",
  "Fantasy",
  "Film-Noir",
  "Horror",
  "IMAX",
  "Musical",
  "Mystery",
  "Romance",
  "Sci-Fi",
  "Thriller",
  "War",
  "Western",
] as const;

export const PASSWORD_MIN = 15;
export const PASSWORD_MAX = 128;
export const PAGE_SIZE = 20;
export const DELETE_PHRASE = "delete my account";
