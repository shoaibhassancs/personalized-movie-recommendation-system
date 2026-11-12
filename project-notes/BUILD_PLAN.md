# PMRS Build Plan

Draft 1 · Nov 12, 2026 · This is a reasoned proposal, not a contract. Project description and
scope live in `PROJECT_GUIDE.md` and `SCOPE.md`. Effort estimates assume 15–20 h/week and are
rough.

## How to read this plan

- **Versions:** V1 is a complete, portfolio-ready system. V2 is separate extra depth.
- **Phases** end at a **gate**: you approve before the next phase starts. Steps are numbered
  continuously. Each step lists: **Goal · Needs** (dependencies) · **Method** · **Output** ·
  **Done when** (verification) · **Risk/decision**.
- **Dependencies:** each phase names the packages it needs; I explain and ask before installing
  them. Direct imports are declared in `pyproject.toml`.
- **Resource checks:** machine limit recorded in `PROJECT_GUIDE.md` §10. I re-check memory/disk
  before Docker builds, MLflow install, `node_modules`, and the full evaluation run.
- **No Git actions** unless you ask. CI and ignore files are only written as files.
- **Provisional defaults:** tool and design recommendations in this plan and the guide are
  defaults, not final approvals. Open choices are decided when their step or gate is reached:
  the evaluation protocol was decided at Step 5 (D-021, per-user holdout; Gate 1 approved); MLflow install size at Step 15; TMDB before Step 21; React before Step 25;
  deployment platform at Step 33; `ml-1m` only after V1 is assessed (Gate 6). Each decision is
  recorded in `DECISIONS.md`. The full table is in `PROJECT_GUIDE.md` §11.
- **Approval at every gate:** no phase starts without your explicit approval of that phase,
  and approval of one phase never covers a later one.

Order logic: ML first (the core and the biggest risk), then database and API, then React, then
delivery.

---

# VERSION 1

## Phase 1: Foundation and data (Steps 1–5)

Purpose: a working Python project, legal data in place, and an understanding of the data before
any model.
Packages (to approve): pytest, ruff, mypy (dev); pandas, numpy, scipy; plotly + ipykernel
(for EDA).

**Step 1. Project scaffold**
- Goal: reproducible Python project that cannot accidentally track data, secrets or artifacts.
  Needs: nothing. Method: **first** write a project-specific `.gitignore` (before any download or
  generated file exists); then `uv init`, `src/pmrs/` layout, `pyproject.toml`, ruff/pytest/mypy
  settings (Python 3.12 decided, D-011). The `.gitignore` covers at least:
  downloaded datasets (`data/`); secrets and local environment files (`.env`, `.env.*` but not
  `.env.example`); fitted model/serving artifacts (`models/`, `*.joblib`); MLflow tracking data
  (`mlruns/`, `mlartifacts/`); caches (`__pycache__/`, `.pytest_cache/`, `.ruff_cache/`,
  `.mypy_cache/`, `.ipynb_checkpoints/`); generated build and dependency directories (`.venv/`,
  `dist/`, `build/`, `*.egg-info/`, `frontend/node_modules/`, `frontend/dist/`); and OS/editor
  files (`.DS_Store`), plus the private `/project-notes/` folder (owner decision D-012). It must
  not ignore source, tests, docs, notebooks, `uv.lock`, `.env.example`, or the root `DECISIONS.md`.
- Output: `.gitignore`, empty package that imports, and a passing smoke test. Done when:
  the patterns are reviewed line by line against sample paths: `data/raw/ratings.csv`, `.env`,
  `models/x.joblib` and `mlruns/` are ignored; `src/pmrs/__init__.py`, `docs/evaluation.md`,
  `.env.example` and `uv.lock` are not. I will not run `git init` for this; once you create the
  repository yourself, the read-only `git check-ignore -v` can confirm it. Also: `uv sync`,
  `uv run pytest`, `uv run ruff check` all run clean.
- Risk/decision: Python 3.12 (decided, D-011). `project-notes/` is git-ignored (D-012), so
  planning notes stay local; `DECISIONS.md` is at the repo root and is tracked.
- Progress note: the Python 3.12 uv environment (`pyproject.toml`, `.python-version`, `.venv`)
  was created early at the owner's request; the rest of this step is not done (see BUILD_LOG).

**Step 2. Obtain and record the dataset**
- Goal: `ml-latest-small` in `data/raw/`, git-ignored. Needs: 1. Method: download script from
  grouplens.org; verify counts against the README (100,836 ratings; 9,742 movies; 610 users;
  3,683 tags); record license and citation text in `DECISIONS.md`.
- Output: script + verified files (~1 MB). Done when: row counts match the README.
- Risk: license reading is mine, not legal advice; recorded as such.

**Step 3. Loading and validation module**
- Goal: typed loaders with checks. Needs: 2. Method: pandas; parse the year from the title,
  split genres, check ID integrity, duplicates, rating range, timestamp sanity; unit tests with
  tiny fixtures.
- Output: `pmrs.data` module + tests. Done when: tests pass and a real-data check reports no
  silent drops (counts logged).

**Step 4. Exploratory data analysis**
- Goal: facts that drive design. Needs: 3. Method: notebook with Plotly: sparsity, rating
  distribution, user/item activity long tail, genre counts, time span, tag coverage, "(no
  genres listed)" rows, and **the time distribution**: ratings and tags per month/year, each
  user's first-to-last rating span, and how many users rate in a single short session.
- Output: notebook + short findings list. Done when: findings state the relevance threshold, the
  candidate minimum-history rule (the cut between evaluated and cold-start users), tag coverage, and whether ratings are spread widely enough in
  time for a shared chronological split (with numbers).
- Decision (owner): confirm relevant = rating ≥ 4 after seeing the distribution.

**Step 5. Interaction matrix and splits** (built; owner-approved protocol, D-021)
- Goal: evaluation data with an honest, narrowed claim. Needs: 3, 4. The plan's original shared
  chronological split (two global cutoffs `T_val`, `T_test`) was measured in Step 4 and failed its
  feasibility criteria (D-020), so the owner approved the plan's fallback instead.
- Method: `scipy.sparse` user-item matrix with ID maps, and a **per-user temporal holdout**: for
  each user, the latest ceil(10%) of ratings are test and the preceding ceil(10%) are validation;
  the rest are train. Equal timestamps stay together; a boundary tie goes to the later period.
  Relevant means rating >= 4.0.
  - **Eligibility:** a user is scored only with at least 10 ratings left in train and neither
    held-out period above 30% of their ratings; an excluded user's train ratings stay in the fit.
    A user is evaluated in a period only if it holds at least one relevant item.
  - **Information rule:** validation scoring uses models fitted on train ratings only; for the
    final test, models are refit on train + validation (eligible users' validation ratings only)
    and test is read once. A tag is usable only if earlier than its own author's cutoff for the
    target. A no-tags content variant is reported alongside.
  - **Candidate set:** warm users: whole catalogue minus the user's pre-cutoff items. Cold-start
    simulation users: whole catalogue minus only the ratings revealed for that history size
    (0 excludes nothing); hidden train, validation and test ratings never filter candidates
    (D-023). Held-out items are eligible in both cases.
  - **Cold-start simulation:** a fixed-seed (42) 20% of users is kept out of every fit (ratings
    and tags). They are scored with 0, 3, 5 and 10 earliest train ratings revealed. Labelled a
    simulation; the zero-history case measures the popularity fallback; the favourite-genre
    onboarding path cannot be measured on MovieLens.
  - **Claim limit (mandatory in every report):** cutoffs differ per user but a model is fitted
    once, so it still sees other users' later ratings and tags. The results support only "methods
    compared under the same per-user holdout protocol", never "globally leakage-safe" or "predicts
    the future".
  - **Feasibility report:** per-period, per-group tables of ratings, relevant ratings, evaluated
    users, relevant held-out items, held-out items present in the fit, candidates per user, usable
    tags, cold-start counts, and the measured share of fit data dated after a user's own cutoff.
- Output: `pmrs.split` (period assignment, ID maps, interaction matrix, fit/tag/candidate rules,
  evaluation-user groups, cold-start history), saved assignments and feasibility tables in
  `data/processed/split/` (git-ignored). Done when: tests prove (a) timestamp ordering within each
  user, (b) ties never split, (c) no user-item pair is in two periods, (d) fits never contain
  test ratings or tags at or after the author's cutoff, (e) candidate sets exclude pre-cutoff
  items (warm) or only the revealed history (cold-start) and keep held-out ones, (f) cold-start users are absent from every fit.

**Gate 1:** data understood, split (or approved fallback) fixed, thresholds agreed.

## Phase 2: Recommendation models (Steps 6–12)

Purpose: all algorithms working offline in plain Python. No web code yet.
Packages: scikit-learn (needed throughout; added in Chunk A), joblib (via scikit-learn; declared when
Step 12 first imports it).

**Step 6. Baselines and popularity fallback** (built in Chunk A, 2026-11-12; D-024)
- Goal: reference methods and the cold-start fallback. Needs: 5. Method: random; global
  popularity; Bayesian-weighted average rating (shrinks small-count movies). Shared "exclude
  seen" ranking helper.
- Output: baseline recommenders. Done when: tests on a toy dataset give hand-checked order;
  seen items never returned.

**Step 7. Content-based model** (built in Chunk A, 2026-11-12; D-024)
- Goal: genre/tag/title/decade similarity. Needs: 5. Method: TF-IDF over genres, normalised user
  tags, title tokens; decade feature. **The model is built from a data cutoff passed in by the
  caller. During evaluation, tags come only from the Step 5 `allowed(cutoff)` set (timestamp <
  the applicable cutoff) and the TF-IDF vocabulary/weights are fitted on that data only**; the
  all-tags version is built only for the final serving artifacts (Step 17); user profile = rating-centred weighted average of liked
  item vectors; cosine scoring.
- Output: content recommender. Done when: toy tests pass; a user who only rated sci-fi gets
  sci-fi on a real-data spot check (documented).
- Risk: sparse tags; weights of feature groups are tuned later on validation only.

**Step 8. Collaborative filtering: item-based** (built in Chunk A, 2026-11-12; D-024)
- Goal: neighbourhood CF. Needs: 5. Method: mean-centred cosine item-item similarity with
  top-N neighbours and shrinkage for few co-raters; rating prediction and ranking scores.
- Output: item-kNN recommender. Done when: toy tests; scores computed from the user's profile at
  request time (no retraining) is proven by a test that adds a rating and sees the list change.

**Step 9. Collaborative filtering: matrix factorisation** (built in Chunk A, 2026-11-12; D-024)
- Goal: latent-factor CF. Needs: 5. Method: TruncatedSVD on the mean-centred matrix, with
  fold-in for new users.
- Output: SVD recommender. Done when: toy tests; reconstructed ratings clipped to 0.5–5;
  fold-in test passes.
- Note: scikit-learn has no ALS/FunkSVD. This is a limitation to state, not hide.

**Step 10. Hybrid and cold-start logic** (built in Chunk B, 2026-11-12; D-026)
- Goal: blended ranking and new-user handling. Needs: 6–9. Method: normalise scores per method;
  blend with a weight that depends on the user's rating count; branches: 0 ratings → favourite
  genres + weighted popularity; few ratings → content-heavy; many → balanced.
- Output: hybrid recommender. Done when: tests cover each branch; weights tunable via a config
  but not tuned yet.
- Built: ladder 0 / 1-9 / 10+ ratings in `hybrid.py` (`HybridConfig`); per-user min-max scaling
  over candidates; all weights provisional and untuned.

**Step 11. Explanations** (built in Chunk B, 2026-11-12; D-026)
- Goal: truthful reasons. Needs: 7–10. Method: each model returns evidence with its scores (top
  matching genre/tag; the user's highest-rated similar movie; neighbour support; popularity
  fallback), turned into fixed sentences.
- Built: `Model.evidence(history, item)` returns `Evidence`; `explain.render` is the only place
  sentences are written; `Recommender` keeps evidence and sentence together.
- Output: explanation field in results. Done when: tests assert each explanation names a real
  movie/genre from the evidence, and the fallback says it is popularity-based.

**Step 12. Single recommender interface and artifacts** (built in Chunk B, 2026-11-12; D-026)
- Goal: one implementation for notebooks, CLI, and the API. Needs: 6–11. Method: a `Recommender`
  class with `recommend(user_profile, strategy, k)`, artifact save/load (joblib), version
  metadata (data hash, date, seed).
- Output: `pmrs.recommender` + small CLI. Done when: fit → save → load → identical results test.
- Built: `Recommender`, `artifact.py` (joblib + `metadata.json` with SHA-256; never overwrites;
  trusted-artifacts-only warning), `cli.py` (`build`, `recommend`); `joblib>=1.6.0` declared.
  Tests: ladder, scaling, explanations, candidate rule, round trip, damage detection.

**Gate 2:** all methods run offline, tests green, owner reviews sample outputs. *Status: Steps
6-12 built and checked (154 tests, lint, strict mypy, real-data smoke run); awaiting owner review.*

## Phase 3: Evaluation and experiment tracking (Steps 13–17)

Purpose: the credibility evidence.
Packages: mlflow (size to be checked first; `mlflow-skinny` is the fallback), plotly.

**Step 13. Metrics module** (built 2026-11-12; D-028)
- Goal: correct metrics. Needs: 5. Method: Precision/Recall/NDCG/MAP@K, RMSE, MAE, coverage,
  intra-list genre diversity.
- Output: `pmrs.metrics`. Done when: unit tests with hand-computed values (including edge cases:
  no relevant items, K larger than the list).
- Built: ranking, rating, coverage, diversity and bootstrap functions; 21 hand-computed tests.

**Step 14. Evaluation harness** (built 2026-11-12; D-028)
- Goal: one command compares all methods. Needs: 12, 13. Method: two modes. **Validation
  mode:** every fitted component (popularity statistics, item similarities, SVD, TF-IDF, user
  profiles) uses only the Step 5 train data and tags usable for validation. **Test mode:** models
  are refit on train + validation with the configuration frozen in Step 15. For each evaluated user, the
  **candidate set is every catalogue movie except those the user rated before the applicable
  cutoff** (the user's own train items for validation, train + validation for test; for a
  cold-start simulation user, only the ratings revealed for that history size). Held-out movies from the evaluated
  period are **not** removed: they stay eligible, so relevant held-out items must be ranked
  against all other unknown movies. Movies with no ratings before the cutoff stay eligible too
  (methods that cannot score them rank them last or by fallback; this shows in coverage).
  Score at K = 5, 10, 20; report per-user metrics so intervals can be computed, and report the
  cold-start simulation separately (labelled as such) using the Step 5 groups.
- Output: harness + results table on validation, with evaluated-user counts. Done when: baselines
  behave sensibly (random ≈ near zero, popularity above it); harness rerun is reproducible; tests
  confirm (a) a held-out item is in the candidate list while a known pre-cutoff item (or a revealed
  cold-start history item) is not, and (b)
  no rating or tag used in fitting is at or after its own user's or author's cutoff in force.
  The harness labels all outputs with the narrowed per-user-holdout claim.
- Built: `pmrs.evaluation` (`uv run python -m pmrs.evaluation`), results in
  `data/processed/evaluation/validation/` (git-ignored); rerun verified byte-identical; the test
  period is protected (`allow_test`); first untuned validation results recorded in D-028.

**Step 15. Tuning with tracking** (built and run 2026-11-12; D-029, D-030; the selected configuration is
proposed and awaits the owner's approval to freeze)
- Goal: choose settings without touching test. Needs: 14. Method: 36 configurations in stages
  (item-kNN neighbours x shrinkage, item-kNN minimum support, SVD factors, content feature-group
  weights, hybrid weights for the many- and few-ratings rungs) evaluated in validation mode;
  each logged to MLflow (`mlflow-skinny`, local file store, git-ignored) and to CSV/JSON. Rule:
  adopt the best NDCG@10 only if its paired 95% interval against the default is entirely above 0.
- Output: `data/processed/tuning/` (trials, stage tables, before/after, proposed frozen config with
  SHA-256) and 36 MLflow runs. Done: a test records every target tuning touches (only
  `validation`) and the harness still refuses `test`. NOT frozen until the owner approves.
- MLflow size was checked first: 64 MB with dependencies, under the 1 GB limit.
- After the grid, the owner chose pure popularity for 1-10 ratings and for the cold-start
  simulation (0, 3, 5, 10 revealed) and kept the 10+ hybrid for warm users (D-030, an owner
  decision, not a grid winner). `pmrs.evaluation.selection` writes the proposed config and runs
  the validation routing checks (18 PASS).

**Step 16. Final test evaluation and report** (built and run 2026-11-12; D-032; `docs/evaluation.md`; awaiting owner review)
- Goal: the headline results. Needs: 15. Method: refit the frozen configuration on train +
  validation, then read the test period once; bootstrap 95% intervals over
  users; separate cold-start simulation; charts in Plotly; written `docs/evaluation.md` with caveats
  from the guide, the Step 5 feasibility table, and the exact claim the split supports (the
  narrowed per-user-holdout claim and the measured cross-user leakage).
- Output: results report. Done when: every number in the report is traceable to a logged run;
  weaknesses (e.g., hybrid not winning) are stated if they occur.
- Decision (owner): if hybrid does not beat the best single method, we report it and discuss
  rather than tuning on test.

**Step 17. Final serving artifacts and model card draft** (built and verified 2026-11-12; D-033; `MODEL_CARD.md`; awaiting Gate 3)
- Goal: artifacts for the API. Needs: 16. Method: refit chosen configuration on all MovieLens
  data; save with version metadata; draft `MODEL_CARD.md`.
- Output: artifact files (git-ignored) + model card draft. Done when: load-and-recommend test
  passes.

**Gate 3:** evaluation accepted; ML core frozen for V1 unless evidence says otherwise.

## Phase 4: Database and backend API (Steps 18–24)

Purpose: persistent users and interactions, and an API over the same recommender.
Packages: fastapi, uvicorn, sqlalchemy, alembic, psycopg, pydantic-settings, a password-hash
library, a JWT library, httpx (tests). Docker for Postgres.

**Step 18. PostgreSQL and schema**
- Goal: dev database. Needs: 1; Docker daemon running. Method: Docker Compose Postgres; SQLAlchemy
  2 models and Alembic migrations for users, movies, ratings, interactions (like/dislike,
  watchlist, watched, viewed), user favourite genres, recommendation events.
- Output: schema + migration. Done when: migrate up/down works on an empty DB.
- Risk: disk (Postgres image); check space first.

**Step 19. Seed pipeline**
- Goal: load MovieLens into the DB. Needs: 3, 18. Method: idempotent script; MovieLens users
  flagged historical (cannot log in).
- Output: seed command. Done when: DB counts equal dataset counts; running twice changes nothing.

**Step 20. FastAPI app and authentication**
- Goal: register, login, profile, genre preferences. Needs: 18. Method: hashed passwords, JWT
  access tokens, settings from environment variables, test database fixtures.
- Output: auth endpoints + tests. Done when: tests cover duplicate email, wrong password,
  expired/invalid token, and access to another user's data denied.

**Step 21. Catalogue API**
- Goal: browse/search/filter. Needs: 19, 20. Method: paginated list, title search, genre/year/
  rating filters, sort, detail endpoint with average rating and count; placeholder poster
  generated from title/genre.
- Output: endpoints + tests. Done when: filter combinations return the expected rows on a small
  seeded fixture.

**Step 22. Interaction API**
- Goal: rate, like/dislike, watchlist, watched, history. Needs: 20, 21. Method: upserts;
  validation (0.5–5 in 0.5 steps); history lists.
- Output: endpoints + tests. Done when: repeated actions update rather than duplicate; users see
  only their own data.

**Step 23. Recommendation endpoints and engagement events**
- Goal: serve the three methods. Needs: 17, 22. Method: load artifacts at startup; build the
  user profile from DB interactions; call the shared `Recommender`; log "shown" and
  "acted-on" events with the strategy name.
- Output: `/recommendations` with strategy and explanations. Done when: tests for new user
  (fallback), few ratings, many ratings; seen movies excluded; adding a rating changes the
  list; response time measured and recorded (no performance claim without the number).

**Step 24. Dashboard and analytics endpoints**
- Goal: data for sections F and G. Needs: 23. Method: SQL aggregates. Trending = most
  interactions in a recent window of the **app's** data, falling back to the dataset's latest
  period (stated on the page); recently added = newest release years.
- Output: endpoints + tests. Done when: aggregates match hand-checked counts on a fixture; empty
  states return honest zeros.

**Gate 4:** API verified by tests and by calling it manually together.

## Phase 5: Frontend (Steps 25–30)

Purpose: a thin, working React interface. Packages (npm): react, react-router, vite,
typescript, a small chart library, vitest + testing-library.

**Step 25. React scaffold and API client.** Goal: running app with routing and typed API calls.
  Needs: 20. Done when: build succeeds and a login round-trip works. Risk: `node_modules` disk
  use (check).
**Step 26. Auth, profile and genre onboarding.** Needs: 25. Done when: register → pick genres
  → land on the dashboard, verified in a browser.
**Step 27. Catalogue and movie detail.** Search, filters, rating/like/watchlist/watched
  controls. Needs: 21, 22, 26. Done when: each control changes state and persists after reload.
**Step 28. Recommendations page.** Strategy switch (content / collaborative / hybrid),
  explanation text, cold-start message. Needs: 23, 27. Done when: a fresh account and a
  heavily-rating account show clearly different, explained lists.
**Step 29. User dashboard.** Needs: 24, 28. Done when: all seven dashboard items in section F
  render with real data.
**Step 30. Analytics dashboard.** Needs: 24. Done when: all section G items render; empty states
  are honest. Frontend tests for key components; manual browser walkthrough recorded.

(Each of steps 25–30 states its own goal/method/output when its phase starts; they are grouped
here because they are small and share one tool chain.)

**Gate 5:** a person can complete the nine-point final deliverable list locally.

## Phase 6: Delivery (Steps 31–35)

**Step 31. Containerisation.** Goal: one command runs everything. Needs: 5 gates. Method:
  Dockerfiles (API, frontend), full `compose.yaml`, `.env.example`. Done when: clean `docker
  compose up --build` works and the seed runs. Risk: disk/memory check first.
**Step 32. Continuous integration.** Goal: automated checks. Method: GitHub Actions file with
  ruff, mypy, pytest, frontend lint/build/test. Done when: the same commands pass locally (the
  workflow itself runs only after you push, which I will not do).
**Step 33. Cloud deployment.** Goal: a live demo. Needs: 31. Method: pick one platform after
  comparing current free-tier limits and cost from primary docs; set secrets in the platform,
  not in files. Done when: public URL passes a smoke test. Owner decision: platform, and
  approval of exactly what is uploaded. The demo is non-commercial and shows the MovieLens
  citation.
**Step 34. Documentation.** README (what, how to run, architecture, results summary, limits),
  final `MODEL_CARD.md`, dataset citation and attribution, screenshots. Done when: a fresh reader
  can run it from the README.
**Step 35. Final verification.** Fresh run from a clean checkout copy; full test suite;
  walkthrough against the nine deliverables in the original specification; update every
  document to match reality. Done when: each claim in the README has a check behind it, and
  unverified items are listed.

**Gate 6 = V1 done.**

---

# VERSION 2 (separate, optional)

Only after V1 is accepted; each item needs its own approval.

1. TMDB posters/descriptions for display only, after you read TMDB's terms (including the ML/AI
   clause, the 6-month cache limit, and attribution).
2. Local `ml-1m` benchmark replication (not redistributed) for a more standard comparison.
3. Implicit-feedback model (e.g., ALS via a dedicated library) and learned feature weights.
4. Diversity re-ranking (MMR) and novelty metrics.
5. Scheduled retraining job and model versioning in the app.
6. Optuna-based search; compare with the V1 grid.
7. AWS deployment (container service + managed Postgres) if you want the cloud-specific skills.
8. Load tests with measured latency; admin role; email verification and password reset.
