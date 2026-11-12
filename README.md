# PMRS: Personalized Movie Recommendation System

A solo, non-commercial portfolio project. A web app (React + FastAPI + PostgreSQL) where you
register, rate movies, and get ranked, explained recommendations from content-based,
collaborative and hybrid methods fitted on the MovieLens `ml-latest-small` dataset, with an
offline evaluation against baselines.

**Version 1 is a local release.** It runs on your own machine with one Docker command. There is
no hosted demo and no public URL, by design: see [Why there is no hosted demo](#why-there-is-no-hosted-demo).

| Item | State |
|---|---|
| Hosted demo | **None, deliberately.** Deferred for V1 (decision D-048); see [the reasons below](#why-there-is-no-hosted-demo). |
| Local Docker run | Built and run locally on one Mac; an 11-check round trip passed. See [Run it locally with Docker](#run-it-locally-with-docker). Not run on Linux or Windows. |
| Model artifact for a fresh reader | Build steps are documented (the tracked `docs/frozen_config.json`, the MovieLens download and `serving build`); the rebuild was verified once in a clean copy (details below). See [the model artifact](#the-model-artifact). |
| CI | Passed once on GitHub (owner-reported), but **before the latest code change**. It must be re-run after the next push, so CI is **not verified for the current code**. See [CI](#continuous-integration). |
| Screenshots | **Not added yet.** The list of planned images is in [Screenshots](#screenshots). |
| Code licence | **None.** The code is unlicensed for now, so all rights are reserved by default and no one is granted reuse rights. The owner has not chosen a licence. |

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
(`src/pmrs/evaluation/`).

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

## Run it locally with Docker
This is the intended way to try the project. It starts four things on your machine: a PostgreSQL
database (its own volume), a one-shot job that creates the tables and loads MovieLens, the API,
and the web app. Everything listens on `127.0.0.1` only.

**You need**
- Docker with Compose v2 (Docker Desktop on macOS or Windows, or Docker Engine on Linux). It was
  tested only on macOS with Apple silicon.
- About 3 GiB of free disk. The first local build used roughly 2.8 GiB in total (base images, build
  cache and the database volume).
- The MovieLens data in `data/raw/ml-latest-small/`.
- The frozen model artifact in `data/processed/artifacts/serving_all_data/` (see
  [the model artifact](#the-model-artifact)).
- A `.env` file next to `compose.app.yaml`, copied from `.env.example`. For this stack it needs
  `POSTGRES_USER`, `POSTGRES_PASSWORD` (use only letters and digits, since it goes into a database
  URL), `POSTGRES_DB` and `JWT_SECRET` (32 or more characters, for example from
  `python -c "import secrets; print(secrets.token_urlsafe(48))"`). `.env` is git-ignored: never commit
  it, and never put these values in an image or a command you share.

**Steps**
```bash
cp .env.example .env          # then edit .env and fill in the four values above
# get the data once (this downloads from GroupLens; see "Data, citation and attribution"):
uv run python -m pmrs.data.download
# (or download https://files.grouplens.org/datasets/movielens/ml-latest-small.zip yourself
#  and unzip it so that data/raw/ml-latest-small/ratings.csv exists)
docker compose -f compose.app.yaml up --build
```
When the `migrate` job reports `verified: database equals the dataset` and the API is healthy, open
**http://localhost:8080**. Register with any email address you do not mind storing locally (an address
such as `you@example.com` works), choose a few genres, and start rating. The API is at
http://127.0.0.1:8000. The first build takes several minutes; later starts take a few seconds.

**Stop and clean up**
```bash
docker compose -f compose.app.yaml down        # stop; keeps the seeded database volume
docker compose -f compose.app.yaml down -v     # stop and delete this stack's database volume only
```

**Good to know**
- This stack has its own project name and volume, so it never touches the database started by
  `docker compose up -d db` (used for development).
- If port 8000 or 8080 is busy, set `API_PORT` or `WEB_PORT` (for example `WEB_PORT=8090`) and run the
  same `up --build` command again; the web image bakes in the API address, so it must be rebuilt.
- The data and the artifact are mounted read-only; they are never copied into an image. The images contain
  no `.env` and no secrets, and both containers run as non-root users.
- Image sizes (measured locally): API about 636 MB on disk (about 131 MB compressed), web about 93 MB
  (about 26 MB compressed).
- Local use only. See [Known limits](#known-limits).

### The model artifact
The model artifact is not in the repository: it is a pickle fitted on MovieLens data, so it is git-ignored and is only built by this project's own
code. The API refuses to start without `data/processed/artifacts/serving_all_data`. You build it from three things: the tracked source, the MovieLens
dataset, and the frozen configuration in `docs/frozen_config.json`. That file holds only settings, hybrid weights, routing and provenance notes, the
random seed and two SHA-256 hashes; it contains no data, no secrets, no local paths and no fitted model.

```bash
uv sync                                              # Python packages from uv.lock
uv run python -m pmrs.data.download                  # MovieLens ml-latest-small -> data/raw/ (downloads from GroupLens)
mkdir -p data/processed/tuning
cp docs/frozen_config.json data/processed/tuning/proposed_frozen_config.json
uv run python -m pmrs.evaluation.serving build       # writes data/processed/artifacts/evaluated_step16 and serving_all_data
```
- Run these from the repository root; the code reads those relative paths.
- The code recomputes the configuration's settings hash and refuses to build unless it equals the frozen value `e68a7ee6...ce2b5`, so an edited
  config is rejected. `build` also refuses to overwrite an existing artifact folder.
- The app loads only `serving_all_data`. `evaluated_step16` is the fit that the published evaluation numbers describe. Building either one does not
  compute any evaluation metric.
- `serving verify` compares the artifacts with the project owner's local record of the single Step 16 evaluation run, which is not in the repository, so
  it is not expected to work in a fresh clone.
- **Verified once (2026-11-12), on the author's Mac, in a clean copy of the tracked files** that held the MovieLens files and `docs/frozen_config.json`
  but not the existing artifact. `serving build` took about 7 seconds and wrote both folders. For each folder the manifest check, the frozen-hash check
  and the model load passed; `provenance.json` and the stored config were identical to the author's originals; the data fingerprint and fit counts
  matched (serving: 100,836 ratings, 610 users, 3,683 tags, 9,742 movies). For 40 sample users at five history sizes and six methods, the rebuilt and the
  original models returned identical top-10 lists in all 1,200 cases per artifact, with identical scores. The full test suite, including the 16
  recommendation-API tests that need an artifact, passed against the rebuilt artifact (294 passed, 0 skipped).
- **Limits of that check:** the model files are **not byte-identical** to the author's originals (they differ by a few hundred bytes; the cause was not
  investigated), so compare behaviour, not file hashes. That run reused an existing Python environment and a local copy of the MovieLens files instead of
  running `uv sync` and the GroupLens download. It was tried on one machine only. Artifacts are pickles: load only ones this project built.

## Run it from source (development)
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
Development `.env` also needs `DATABASE_URL` (and `TEST_DATABASE_URL` for the tests) and optionally
`FRONTEND_ORIGIN`. Use `localhost`, not `127.0.0.1`, for the frontend (the API allows exactly one origin).

## Why there is no hosted demo
Version 1 deliberately has no public deployment. The reasons, together:

- **Zero hosting cost.** V1 is kept at a strict $0 budget, with no payment method and no paid fallback.
- **Free-tier limits.** Free hosting tiers commonly limit memory (for example 512 MB) and expire or reset free
  databases (for example after about 30 days), which would delete every account and rating. Those figures
  come from the project owner's notes and have **not been rechecked against any provider's current
  documentation**. A free web service that sleeps when idle also loses anything held in memory.
- **A local memory test.** The API container was run locally with a 512 MB memory limit, swap off and 0.1 CPU.
  It used about 250 MiB in ordinary single use, but **eight simultaneous registrations got it OOM-killed** (each
  password hash uses 64 MiB); two, three and four at once peaked at 318, 382 and 447 MiB.
- **A slow cold start.** Under the same 0.1 CPU limit the API took about 3.7 to 4 minutes to start, against about
  10 to 15 seconds unthrottled.
- **Hardening a public API needs.** There is no login throttling, no cap on concurrent password hashing, no
  HTTPS, `/docs` is enabled, tokens cannot be revoked and deleting an account asks for no password. Those would
  have to be built and tested before any public exposure.
- **Unresolved MovieLens terms.** MovieLens is licensed for non-commercial use. Whether a portfolio
  demonstration counts as non-commercial is an open question for the project owner, and hosting a copy of the
  data and models fitted on it is a form of redistribution.

**The 512 MB test was run locally on one Mac, and Render was not tested.** It is a local estimate, not
evidence about any hosting provider. Public hosting (for example on Render's free plan) remains a possible
future option; [docs/hosting-gate.md](docs/hosting-gate.md) lists what would have to be true first. For this
local-only release the memory result is a hosting limitation, not a defect: the local stack applies no memory
cap and is reachable only from your own machine.

## Screenshots
Screenshots are **not added yet**. They will be supplied last and this section updated once more. Planned
images, each captured from the local Docker stack (not a hosted site), saved under `docs/screenshots/`:

| # | Screen | What it shows |
|---|---|---|
| 1 | Catalogue with search and filters applied | search, genre/year/rating filters, generated placeholder posters |
| 2 | A movie's detail page | rating, like/dislike, watchlist and watched controls |
| 3 | Onboarding genre picker | how a new person starts |
| 4 | Recommendations page (hybrid) | the fixed explanation sentences and the "served" notice |
| 5 | Dashboard | the seven panels |
| 6 | Analytics page | counts, a chart and text tables, with "served" and "acted" wording |
| 7 | Dashboard or catalogue at phone width | responsive layout |
| 8 | One page in dark and light mode (optional) | theming |
| 9 | Offline evaluation chart (optional) | warm-user NDCG@10 with intervals, with the claim limit in the caption |

How they will be made, and caption rules:
- Use a throwaway local stack with a demo account (display name "Demo Viewer", an `@example.com` address) in a
  clean browser profile. Do not capture the Account page (it shows the email), tokens, `.env`, environment
  variables, database URLs, terminal paths, notifications, bookmarks or browser extensions.
- Each caption says "local run, not a hosted demo". The recommendation screens need an account with 11 or more
  ratings to show the hybrid; captions state the rating count and do not call the result personalised or
  accurate. Analytics counts include imported MovieLens users, and "served" means returned by the API, not seen.
  Posters are generated placeholders. Evaluation numbers describe the offline protocol only, never the app.
- These are ordinary portfolio screenshots. Their captions keep the normal MovieLens attribution: the data is MovieLens (GroupLens), used for
  non-commercial portfolio purposes, and the citation below applies.

## Checks
```bash
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
cd frontend && npm run typecheck && npm run lint && npm run format:check && npm test && npm run build
```
Last full local runs: 294 backend tests (with data, artifacts and Postgres available) and 76 frontend tests passed.

## Continuous integration
`.github/workflows/ci.yml` runs the commands above on GitHub Actions with a throwaway Postgres. Its first run
failed during job setup because the action references were placeholders (owner-reported). They are now pinned
to full commit SHAs (`actions/checkout` v7.0.1, `actions/setup-python` v7.1.0, `actions/setup-node` v7.1.0), and
a corrected workflow then passed on GitHub (owner-reported). **That pass was recorded before the latest code
change (an import-only edit to `src/pmrs/evaluation/final.py`), so the workflow must be re-run after the next
push; until then CI is not verified for the current code.**

A fresh checkout has no MovieLens data and no artifact, so in CI these tests **skip, and a skipped test is not a
pass**: 16 tests in `tests/test_api_recommendations.py` and 1 in `tests/test_download.py` (checked locally by
running the suite from a copy without data: 277 passed, 17 skipped). CI therefore cannot exercise real
recommendations through the API.

## Known limits
- **Local only.** No rate limiting, no login throttling, no HTTPS, `/docs` is enabled, tokens cannot be revoked,
  and `DELETE /me` asks for no password. Do not expose the API publicly.
- The token is kept in `sessionStorage`, so a script injected into the page could read it.
- Small, development-grade data; no real users. No load, security or many-user testing beyond the local memory
  test above.
- Recommendations are popularity-heavy; exactly 11 ratings was never evaluated.
- The Docker run was tested on one machine (macOS, Apple silicon) only.

## Data, citation and attribution
Movie, rating and tag data: **MovieLens `ml-latest-small`**, from GroupLens (University of Minnesota). It is used
here for non-commercial research and demonstration only, and it is not redistributed in this repository (the
download command above fetches it from GroupLens). This project is not endorsed by GroupLens or the University of
Minnesota. Please cite:

> F. Maxwell Harper and Joseph A. Konstan. 2015. The MovieLens Datasets: History and Context.
> ACM Transactions on Interactive Intelligent Systems (TiiS) 5, 4: 19:1-19:19.
> <https://doi.org/10.1145/2827872>

These notes summarise the dataset's terms and are not legal advice; read the README that comes with the
download. Do not use this project for anything commercial or revenue-bearing. Whether a portfolio demonstration
counts as non-commercial use is an open question for the project owner. The app footer shows the attribution, a compact
citation and the not-endorsed line on every page.

## Licence
The code has **no licence** for now (all rights reserved by default). The MovieLens data keeps its own terms.
