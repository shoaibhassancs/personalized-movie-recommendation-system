# PMRS Architecture

Draft 1 · Nov 12, 2026 · Describes the planned V1 system. Nothing here is built yet. It follows
`PROJECT_GUIDE.md` and `BUILD_PLAN.md`; if they change, this file changes with them.

## 1. System at a glance

```
                  Browser
                     |
          React SPA (Vite, TypeScript)
                     | HTTPS / JSON (JWT in Authorization header)
                     v
        FastAPI service  (routers -> services -> repositories)
          |                         |
          | SQLAlchemy              | imports (same Python process)
          v                         v
    PostgreSQL            pmrs.recommender  (no web dependency)
    users, movies,          |-- baselines / popularity fallback
    ratings, interactions,  |-- content-based
    events                  |-- collaborative (item-kNN, SVD)
                            |-- hybrid + explanations
                            '-- loads fitted artifacts from disk (joblib)

   Offline (laptop, not in the running app):
   MovieLens CSVs -> pmrs.data -> pmrs.split -> fit models -> pmrs.metrics
        -> evaluation report + MLflow runs (local file store) -> serving artifacts
```

Key idea: **one recommender package, two entry points** (evaluation harness/CLI and the API).
The API never reimplements ranking logic.

## 2. Components

| Component | Responsibility | Tech | Notes |
| --- | --- | --- | --- |
| `pmrs.data` | Load, validate, clean MovieLens | pandas | Shared by EDA, seeding, training |
| `pmrs.split` | Interaction matrix, per-user temporal holdout, evaluation groups | scipy.sparse | Ordering, tie, candidate and cold-start isolation tests live here |
| `pmrs.recommender` | Models, hybrid, cold start, explanations, artifact save/load | scikit-learn, numpy | No FastAPI/SQLAlchemy imports |
| `pmrs.metrics`, `pmrs.evaluation` | Ranking/rating/coverage/diversity metrics, harness | numpy, pandas | Offline only |
| `pmrs.api` | HTTP layer, auth, validation | FastAPI, Pydantic | Thin; calls services |
| `pmrs.db` | ORM models, migrations, seed | SQLAlchemy 2, Alembic, psycopg | PostgreSQL |
| `frontend/` | Pages and API client | React, TypeScript, Vite | Thin SPA |
| Tracking | Evaluation/tuning runs | MLflow (local files, git-ignored) | Not part of the running app |

Planned repository layout (created only as each phase needs it):

```
src/pmrs/{data,split,recommender,metrics,evaluation,db,api}/
tests/            mirrors src/pmrs/
frontend/         React app
notebooks/        EDA
docs/             evaluation.md, adr/ (only for meaningful decisions)
data/ models/ mlruns/   git-ignored
Dockerfile(s), compose.yaml, .env.example, pyproject.toml, uv.lock
```

## 3. Recommender design

**Inputs per request:** the user's ratings and interactions (from the database), favourite
genres, strategy name, K.

**Profile at request time.** The fitted artifacts hold item-side data only (item similarity
lists, TF-IDF item vectors, SVD item factors). A user's vector is computed on the fly from their
current ratings. So a new rating changes that user's next list immediately, with no retraining.

| Strategy | Score | Explanation evidence |
| --- | --- | --- |
| popularity | Bayesian-weighted average rating, shrunk by rating count | "Popular with other users" |
| content | Cosine between user profile (rating-centred mean of liked item vectors) and item vectors | Best-matching genre/tag; most similar liked movie |
| collaborative | Item-kNN prediction from the user's rated neighbours; SVD fold-in as second variant | Rated movie that contributed most; neighbour support count |
| hybrid | Weighted blend of per-method normalised scores; weight depends on the user's rating count | Evidence from the dominant component |

**Cold start ladder:** 0 ratings → favourite genres + weighted popularity; a few ratings →
content-heavy blend; many → balanced blend. Already rated/watched movies are always removed.
Explanations are built from the same evidence that produced the score, never written separately.

**Artifact contents:** item neighbour lists, item feature matrix, SVD item factors, popularity
table, id maps, and metadata (data version, seed, config, creation date).

## 4. Data model (PostgreSQL)

| Table | Key columns |
| --- | --- |
| `users` | id, email (unique), password_hash, display_name, is_historical, created_at |
| `movies` | id (MovieLens id), title, year, genres, tag_text |
| `user_genres` | user_id, genre |
| `ratings` | user_id, movie_id, rating, rated_at; unique (user_id, movie_id) |
| `interactions` | user_id, movie_id, kind (like, dislike, watchlist, watched, viewed), created_at; unique per kind |
| `recommendation_events` | id, user_id, movie_id, strategy, kind (shown, acted), created_at |

MovieLens' 610 users load as `is_historical` rows with no password and cannot log in. They feed
collaborative filtering and the popularity numbers. Registered users get new ids. Schema changes go through Alembic migrations.

## 5. API surface (planned)

| Area | Endpoints |
| --- | --- |
| Auth/profile | `POST /auth/register`, `POST /auth/login`, `GET/PUT /me`, `PUT /me/genres` |
| Catalogue | `GET /movies` (search, genre, year, rating, sort, page), `GET /movies/{id}` |
| Interactions | `PUT /movies/{id}/rating`, `PUT/DELETE /movies/{id}/like`, `.../watchlist`, `.../watched`; `GET /me/history`, `GET /me/watchlist` |
| Recommendations | `GET /recommendations?strategy=content\|collaborative\|hybrid&k=` |
| Dashboard | `GET /me/dashboard` (recommended, trending, popular, recent, genres, watchlist, activity) |
| Analytics | `GET /analytics/summary`, `/analytics/popular`, `/analytics/ratings-distribution`, `/analytics/engagement` |

Exact paths may change during Phase 4; the plan step records any change.

## 6. Security and privacy

- Passwords hashed with a standard slow hash; JWT access tokens with expiry; secrets only in
  environment variables (`.env` git-ignored, `.env.example` committed with no values).
- Every user-scoped endpoint takes the user id from the token, never from the request.
- Input validated by Pydantic (rating range and step, pagination caps). CORS limited to the
  frontend origin.
- Analytics return aggregates only. No real personal data is required for the demo.

## 7. Runtime and deployment

- **Local:** `docker compose up` starts Postgres, the API (with artifacts mounted or baked in),
  and the built frontend. A seed command loads MovieLens.
- **Cloud (V1):** one platform, chosen at Step 33 after reading current limits; secrets set in
  the platform. Non-commercial demo with MovieLens citation visible.
- **Resources:** the data is tiny (about 100k ratings; the sparse matrix fits in memory easily).
  Artifacts are loaded once at API start. Disk, not RAM, is the local limit.
- **Observability (V1, minimal):** request logging and recorded response-time measurements for
  `/recommendations`; no latency claim without a measured number.

## 8. Key design decisions and trade-offs

| Decision | Why | Cost |
| --- | --- | --- |
| Recommender package independent of the web layer | One tested implementation for evaluation and the API | Needs an explicit data-in/data-out interface |
| Item-based CF as the primary collaborative method | Works for new ratings without retraining | Less accurate than modern implicit-feedback methods (V2) |
| Models fitted offline, not retrained live | Avoids job infrastructure | Item similarities stay fixed between refits |
| Postgres plus joblib files (not a model server) | Simple, reproducible, enough for this scale | Not horizontally scalable; fine for a demo |
| Placeholder posters | TMDB terms conflict with ML use | Less visual polish |
| React SPA with a thin page set | Specification asks for it; auth and routing fit | More effort than Streamlit |

## 9. Known limits

Data ends in 2018 and covers 610 users; user tags are sparse; scikit-learn lacks ALS; in-app
engagement numbers reflect only this app's own usage and start empty; offline metrics compare
methods and are not benchmark results.
