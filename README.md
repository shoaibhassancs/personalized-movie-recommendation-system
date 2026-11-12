# PMRS: Personalized Movie Recommendation System

A solo, non-commercial portfolio project. A web app (React + FastAPI + PostgreSQL) where you
register, rate movies, and get ranked, explained recommendations from content-based,
collaborative and hybrid methods fitted on the MovieLens `ml-latest-small` dataset, with an
offline evaluation against baselines.

**Status:** runs on one machine only. There is **no hosted deployment and no public URL**,
and none is approved. The API is not safe to expose to the internet (see
[Known limits](#known-limits)).

| Item | State |
|---|---|
| Code licence | **Not chosen yet.** No licence file exists, so no one is granted reuse rights. The owner must pick one. |
| Screenshots | **None yet.** To be taken by the owner. |
| Hosted demo | **None.** See [docs/hosting-gate.md](docs/hosting-gate.md) for what would have to be true first. |
| Docker run | Files written; **not yet built or run** (NOT RUN). See [Run with Docker](#run-with-docker). |
| CI | Workflow written; **never run** (it only runs on GitHub after a push). See [CI](#continuous-integration). |

## What it does
- Accounts (Argon2id password hashes, 60-minute bearer tokens), favourite genres, profile.
- Catalogue of 9,742 movies with search, genre/year/rating filters and a detail page with
  generated placeholder posters (no outside images).
- Rate (0.5-5), like/dislike, watchlist, watched, history.
- Recommendations from one of: hybrid, SVD, item-kNN, content, popularity, with a fixed
  explanation sentence built from the method's own evidence.
  Routing for the hybrid: 0 ratings = genre/popularity mix, 1-10 = popularity, 11+ = full hybrid.
- A seven-panel dashboard and a login-only analytics page. Events say **served** (returned by
  the API; not necessarily seen) and **acted** (a rating/like/dislike/watchlist/watched change on
  a served movie). They do not show that recommendations caused anything.

## Architecture (short)
`frontend/` (React 19, TypeScript, Vite, plain CSS) calls the FastAPI app in `src/pmrs/api/`.
The API reads PostgreSQL (SQLAlchemy, Alembic migrations in `migrations/`) and loads one frozen
model artifact at startup, after checking its SHA-256 manifest. The recommender code
(`src/pmrs/recommender/`) has no web dependency and is shared with the evaluation harness
(`src/pmrs/evaluation/`). Details: `project-notes/ARCHITECTURE.md` if you have the notes folder.

## Results (offline, one dataset)
Under the same per-user holdout protocol, for warm users (453), NDCG@10 [95% interval]:
hybrid 0.064 [0.052, 0.077], SVD 0.055, popularity 0.047, Bayesian average 0.032, item-kNN
0.021, content 0.007, random 0.002. Hybrid minus popularity is +0.017 [+0.006, +0.029]; minus
SVD +0.009 [+0.001, +0.017] (small). Full tables, the cold-start simulation and caveats:
[docs/evaluation.md](docs/evaluation.md). Model details: [MODEL_CARD.md](MODEL_CARD.md).

**What this does and does not show.** These results support only *methods compared under the same
per-user holdout protocol*. They do **not** show the evaluation is leakage-safe or that it
predicts future behaviour: the models are fitted once and still see other users' later ratings
and tags. Intervals cover sampling noise between users only. Absolute scores are low; most
top-10 lists contain no movie the user rated highly. The cold-start result is a simulation. The
model the app serves (`serving_all_data`) is fitted on all the data and has **no quality metric
of its own**; the Step 16 numbers apply to the separate `evaluated_step16` fit only.

## Run it from source (the verified way)
You need Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22+, and Docker (for Postgres).

```bash
cp .env.example .env              # then fill in values; .env is git-ignored. Never commit it.
uv sync                           # Python packages from uv.lock
uv run python -m pmrs.data.download   # fetches MovieLens ml-latest-small into data/raw/
docker compose up -d db           # Postgres on 127.0.0.1:5433
uv run alembic upgrade head       # create tables
uv run python -m pmrs.db.seed     # load MovieLens, then verify against the CSVs
uv run uvicorn pmrs.api.app:create_app --factory   # API on http://127.0.0.1:8000
cd frontend && npm install --no-audit && npm run dev # app on http://localhost:5173
```

`.env` needs `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `DATABASE_URL`,
`JWT_SECRET` (32+ characters; generate one with
`python -c "import secrets; print(secrets.token_urlsafe(48))"`) and optionally
`FRONTEND_ORIGIN`. Use `localhost`, not `127.0.0.1`, for the frontend (the API allows exactly one
origin).

**The model artifacts are not in the repository** (they are git-ignored). The API refuses to
start without `data/processed/artifacts/serving_all_data`. `uv run python -m pmrs.evaluation.serving build`
creates it from the frozen configuration, but a from-scratch rebuild by someone who only has the
repository has **not been verified**; the full pipeline (split, tuning, selection, final
evaluation) is described in `CLAUDE.md`. Artifacts are pickles: load only ones this project built.

## Run with Docker
Files: `Dockerfile` (API), `frontend/Dockerfile` (static site served by nginx),
`compose.app.yaml` (database, migrate + seed, API, web). **Status: written, validated as
configuration only, not built or run (NOT RUN).**

```bash
docker compose -f compose.app.yaml up --build
# web: http://localhost:8080   api: http://127.0.0.1:8000
```
- It uses its own project name, database server and volume, so it does not touch the database
  from `docker compose up -d db`.
- Needs `data/raw/ml-latest-small` and `data/processed/artifacts/serving_all_data` on the host;
  both are mounted read-only, never copied into an image.
- `VITE_API_URL` is baked into the frontend at build time. Ports are bound to `127.0.0.1`.
- **Open issue:** the API imports `plotly` (through `pmrs.evaluation.final`), which is declared
  only as a development dependency. The default `--no-dev` image would fail at start-up. Until
  the owner decides how to fix it, build with `UV_SYNC_ARGS= docker compose -f compose.app.yaml up --build`
  (installs the dev group too; larger image).
- The 512 MB figure for some free hosts is a **runtime memory** limit, not an image-size limit.

## Checks
```bash
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
cd frontend && npm run typecheck && npm run lint && npm run format:check && npm test && npm run build
```
Last full local run before Phase 6 (with data, artifacts and Postgres available): 294 backend
tests and 75 frontend tests passed.

## Continuous integration
`.github/workflows/ci.yml` runs the commands above on GitHub Actions with a throwaway Postgres.
**It has not passed yet.** Its first GitHub run failed during job setup because the action
references were placeholders (owner-reported). They are now pinned to full commit SHAs
(`actions/checkout` v7.0.1, `actions/setup-python` v7.1.0, `actions/setup-node` v7.1.0), but the
corrected file has not been pushed or re-run, so CI is **NOT VERIFIED**. A fresh checkout has no
MovieLens data and no artifact, so in CI these **skip (not pass)**: 16 tests in
`tests/test_api_recommendations.py` and 1 in `tests/test_download.py` (checked by running the
suite from a copy without data: 277 passed, 17 skipped). So CI cannot exercise real
recommendations through the API.

## Known limits
- **Local only.** No rate limiting, no login throttling, no HTTPS, `/docs` is enabled, tokens
  cannot be revoked, and `DELETE /me` asks for no password. Do not expose the API publicly.
- The token is kept in `sessionStorage`, so a script injected into the page could read it.
- Small, development-grade data; no real users. No load, security or many-user testing.
- Recommendations are popularity-heavy; exactly 11 ratings was never evaluated.

## Data, citation and attribution
Movie, rating and tag data: **MovieLens `ml-latest-small`**, from GroupLens (University of
Minnesota). It is used here for non-commercial research and demonstration only, and it is not
redistributed in this repository (download it with the command above). This project is not
endorsed by GroupLens or the University of Minnesota. Please cite:

> F. Maxwell Harper and Joseph A. Konstan. 2015. The MovieLens Datasets: History and Context.
> ACM Transactions on Interactive Intelligent Systems (TiiS) 5, 4: 19:1-19:19.
> <https://doi.org/10.1145/2827872>

These notes summarise the dataset's terms and are not legal advice; read the README that comes
with the download. Do not use this project for anything commercial or revenue-bearing.
