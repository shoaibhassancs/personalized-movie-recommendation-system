# DECISIONS

Append-only log. Never delete entries; if a decision changes, add a new entry and mark the old
one *superseded*. Labels: **Owner decision**, **Assumption**, **Provisional default** (my
recommendation, not approved as final), **Open** (to be decided at the stated step/gate).
Entries after each approved phase also list files changed, commands run with real results,
verification, and anything unverified.

---

## D-001 · 2026-11-12 · Owner decision · Planning documents approved as working documents
- **Decided:** `project-notes/PROJECT_GUIDE.md`, `SCOPE.md`, `project-notes/BUILD_PLAN.md` and
  `project-notes/ARCHITECTURE.md` are approved as working project documents. Their
  recommendations are **provisional defaults**; open choices are decided at the steps/gates in
  the guide §11 and plan.
- **Also decided by the owner:** open decisions are made as we build (not now); approval is
  required at every phase gate; the four initial records (`CLAUDE.md`, this file, `BUILD_LOG.md`,
  `.gitignore`) are created now, with `DECISIONS.md` and `BUILD_LOG.md` placed in `project-notes/`.
- **Files changed:** created the four files above.
- **Commands run / results:** read-only inspection and reading of documents; no installs, no
  tests, no Git. Earlier in planning, three public web pages (GroupLens READMEs, TMDB API terms)
  were fetched into the session scratchpad for reading only.
- **Unverified:** nothing has been built or run.

## D-002 · 2026-11-12 · Assumption · Project location
Project lives in `/Users/shoaibhassan/Local Files/PythonProjects/personalized-movie-recommendation-system`
(the working directory; the owner did not object).

## D-003 · 2026-11-12 · Assumption · Machine facts (inspected, not guessed)
macOS (Darwin 24.2.0), Apple M1, 8 cores, 8 GB RAM, 12 GiB free of 228 GiB (94% used).
Python 3.13.5 is the default `python3`; Python 3.12.16 is also installed via Homebrew (seen with
`uv python list --only-installed`); Node 22.16.0, npm 10.9.2, uv 0.13.6, git 2.39.5, Docker CLI
29.9.2 (daemon not checked), psql client 17.11. Disk is the main constraint. Re-check before heavy
work.

## D-004 · 2026-11-12 · Settled (from approved working documents) · Product and scope shape
- Build the system in the guide: accounts, catalogue/search/filters, interactions, content-based,
  collaborative (item-kNN and TruncatedSVD) and hybrid recommenders with baselines, explanations,
  user dashboard, analytics page, offline evaluation, Docker, CI, one cloud demo, README, model
  card. Version 1 stands alone; Version 2 holds optional depth.
- Out of V1: AWS-specific infrastructure, password reset/email verification/OAuth/admin roles,
  live retraining, deep-learning/implicit-feedback models, A/B testing infrastructure, real user
  data.
- "Recently added" means newest release years (MovieLens has no date-added field).
- New ratings affect that user's recommendations immediately (profile computed at request time);
  models are fitted offline, not retrained live.
- Analytics page shows aggregates only; engagement statistics come only from real in-app events.
- Source: guide §6; spec limits. **Why:** keeps a solo project credible and appropriately sized.

## D-005 · 2026-11-12 · Settled · Build order and process
ML core and evaluation first (Phases 1–3), then database/API, React, delivery. Phase gates require
explicit approval. No Git actions unless requested. Dependencies are approved before install.

## D-006 · 2026-11-12 · Settled (from approved plan) · Evaluation method
Shared chronological train/validation/test periods for all users; nothing at or after the
applicable cutoff fits any evaluated model or content feature (ratings or timestamped tags);
validation for tuning only; final test evaluation after a refit on train + validation; candidate
set excludes the user's pre-cutoff items while held-out items stay eligible; feasibility of the
split is measured before modelling; an infeasible split triggers an owner-approved fallback with
a narrowed claim. Metrics: Precision/Recall/NDCG/MAP@K (5, 10, 20), RMSE/MAE (secondary),
coverage, diversity, bootstrap intervals over users, separate cold-start group.
**Why:** a per-user time split still lets models see other users' later data. Details: guide §7,
plan Steps 4–5, 14–16. The specific cutoffs are **open** (see below).

## D-007 · 2026-11-12 · Source check · Licences and terms (read, not legal advice)
- MovieLens `ml-latest-small` README (GroupLens, read 2026-11-12): research use; no implied
  endorsement; citation required; redistribution allowed under the same terms; no commercial or
  revenue-bearing use without permission; described as a development dataset not appropriate for
  shared research results. `ml-1m` README: redistribution not allowed without permission.
- TMDB API terms (themoviedb.org, read 2026-11-12): includes a restriction on using TMDB APIs or
  content "in connection with, including for training, a machine learning (ML) or artificial
  intelligence (AI) based Application", a 6-month cache limit, attribution, and no commercial use
  without agreement.
- **Consequence:** public demo is non-commercial with citation/attribution. Owner to read the
  TMDB terms before any TMDB use (see open decisions).
- **Unverified:** I did not check the GroupLens pages beyond the READMEs, or any later change to
  either source.

## D-008 · 2026-11-12 · Provisional defaults (my recommendations, NOT approved as final)
| # | Default | Revisit at |
| --- | --- | --- |
| P1 | Python 3.12 via uv | SUPERSEDED by D-011 (decided) |
| P2 | Cutoffs at 80th/90th percentile of rating time; feasibility minimums of 100 evaluated users and 500 relevant items per evaluation period, 30 cold-start users | Step 5 / Gate 1 |
| P3 | Full MLflow with a local file store; lightweight install if disk is too tight | Step 15 |
| P4 | TMDB out of V1; generated placeholder posters | Before Step 21 |
| P5 | Thin React single-page app (instead of Streamlit) | Before Step 25 |
| P6 | One simple cloud platform for the demo | Step 33 |
| P7 | `ml-1m` benchmark deferred to V2 | After V1 assessment (Gate 6) |
| P8 | Relevant item = rating ≥ 4 | Step 4 |
| P9 | Item-kNN as the primary collaborative method; TruncatedSVD as the second | Phase 2 |
| P10 | SQLAlchemy 2 + Alembic; JWT auth; email + password | Phase 4 |
| P11 | Recharts-style lightweight chart library in the React app; Plotly for reports | Before Step 30 |
| P12 | `project-notes/` is tracked in Git | SUPERSEDED by D-012 (ignored) |

## D-009 · 2026-11-12 · Open decisions (not decided; do not treat as approved)
*(Historical list. Update: Python version and `project-notes/` tracking were later decided in
D-011 and D-012; the current list is in D-014.)*
Python version (Step 1) · final evaluation cutoffs and whether the fallback is needed (Step 5) ·
MLflow install variant (Step 15) · TMDB (before Step 21) · React vs a simpler frontend (before
Step 25) · deployment platform (Step 33) · `ml-1m` (after Gate 6) · whether to track
`project-notes/` in Git (at repository creation).

## D-010 · 2026-11-12 · Record · `.gitignore` created at setup
`.gitignore` was created together with the initial records, before Step 1, at the owner's
request. Its patterns follow Step 1 and are anchored at the repository root where needed so
`tests/data/` and `src/pmrs/data/` are not hidden. It has not been checked with Git (no repository
exists). Step 1 still has to finish its other work, so it is **not** marked done.

---

## D-011 · 2026-11-12 · Owner decision · Python 3.12
- **Decided:** use Python 3.12 (Homebrew 3.12.16, already installed) managed by uv. **Supersedes
  provisional default P1** (now decided, not provisional).
- **Why:** lowest dependency-compatibility risk; no 3.13-only features needed. Package
  compatibility on 3.12 is **not yet verified**; it is checked when dependencies are added.
- **Note:** `pyproject.toml` says `requires-python = ">=3.12"`; `.python-version` pins 3.12.

## D-012 · 2026-11-12 · Owner decision · `project-notes/` ignored; `DECISIONS.md` at repo root
- **Decided:** `/project-notes/` is added to `.gitignore` (planning notes stay local).
  `DECISIONS.md` moves from `project-notes/` to the repo root so it remains trackable.
  **Supersedes provisional default P12** (`project-notes/` tracked) and the placement stated in
  D-001. Resolves the open item "whether to track `project-notes/`".
- **Consequence:** the guide, plan, scope-detail, architecture and build log are not in Git; a
  public reviewer sees `SCOPE.md`, `DECISIONS.md`, `CLAUDE.md` and later the README/model card.
  `CLAUDE.md` refers to files that exist only locally; that is accepted.
- **Files changed:** moved `DECISIONS.md`; edited `.gitignore`, `CLAUDE.md`,
  `project-notes/BUILD_PLAN.md` (Step 1 text). Not verified with Git (no repository).

## D-013 · 2026-11-12 · Owner request · Python 3.12 uv environment created
- **Done:** `uv init --bare --vcs none --python 3.12 --name pmrs .` (created `pyproject.toml`:
  name `pmrs`, version 0.1.0, no dependencies) and `uv venv --python 3.12` (created `.venv`,
  `.python-version`). Project name `pmrs` is my choice (short package name from the plan).
- **Verified:** `.venv/bin/python --version` printed `Python 3.12.16`. No Git, installs of
  packages, tests, or downloads were run.
- **Not done:** `src/pmrs` package, dev tools (pytest, ruff, mypy), build backend, smoke test.
  Those need dependency approval and are the rest of Step 1.

## D-014 · 2026-11-12 · Status · Current open decisions (replaces the live use of D-009)
- **Decided since D-009:** Python 3.12 (D-011); `project-notes/` git-ignored and `DECISIONS.md` at
  the repo root (D-012); the bare uv project/environment (D-013, owner-approved).
- **Still open (provisional defaults in D-008):** evaluation cutoffs, feasibility minimums and
  whether the fallback is needed (Step 5 / Gate 1) · MLflow install variant (Step 15) · TMDB
  (before Step 21) · React vs a simpler frontend (before Step 25) · deployment platform (Step 33)
  · `ml-1m` (after Gate 6).
- **Also open (Step 1):** the exact development and build dependencies; proposal sent, awaiting
  owner approval. Nothing installed.

## D-015 · 2026-11-12 · Owner decision · Step 1 dependencies and Python pin
- **Decided (owner):** development dependencies pytest, ruff and mypy; build backend `uv_build`;
  `requires-python = "==3.12.*"`. Approval covers the remaining Step 1 scaffold only.
- **Owner also set:** work in phase-sized chunks and pause only for real decisions, new
  dependency sets, external actions or gates; the build log must be explanatory plain language
  (see `CLAUDE.md`, "Build log style"). `CLAUDE.md` and `BUILD_LOG.md` were reorganised accordingly.
- **Supersedes:** the "Step 1 dependencies awaiting approval" item in D-014.

## D-016 · 2026-11-12 · Execution · Step 1 scaffold completed
- **Done:** wrote `pyproject.toml` (build-system `uv_build>=0.13.6,<0.14.0`; ruff, mypy, pytest
  settings); created `src/pmrs/__init__.py` and `tests/test_smoke.py`; ran
  `uv add --dev pytest ruff mypy` (installed pytest 9.2.0, ruff 0.17.4, mypy 2.4.1 and 10 helper
  packages; created `uv.lock`).
- **Choices (mine, not asked):** ruff rule sets E, W, F, I, N, UP, B with N803/N806 ignored for
  `X`-style names; mypy `strict = true` on `src/`; `uv_build` version range matches installed uv
  0.13.6.
- **Commands and results:** `uv sync` PASS (13 packages checked); `uv run pytest` PASS (1 passed);
  `uv run ruff check` PASS; `uv run mypy` PASS (1 source file). The first loop attempt failed on
  my shell syntax, not on a check, and was rerun.
- **Disk:** free space stayed 12 GiB (checked before install); `.venv` is about 97 MB.
- **Unverified:** `.gitignore` patterns against Git (no repository); `ruff format`; compatibility
  of future packages on 3.12. Step 1 is complete for what the plan's "done when" lists, except the
  Git-based ignore check, which waits for you to create a repository.
- **Correction (same day):** a Git repository on branch `main` now exists (created by the owner,
  not by me). I ran one read-only `git status` by mistake, against the instruction not to run Git
  commands; nothing changed. The `git check-ignore` verification is therefore still NOT RUN.

## D-017 · 2026-11-12 · Record · Git repository created by the owner; `.gitignore` check
- **Owner action:** the owner created the project's first Git repository and pushed it. I did not
  run `git init`, commit, push or any command to inspect the push, and have not seen what was
  pushed. (D-016's correction note, which says the repository was created by the owner, stands.)
- **My earlier slip, kept on record:** I ran one read-only `git status` against the instruction
  not to run Git commands. I report it made no changes.
- **Owner authorization:** one narrowly scoped, read-only `git check-ignore -v -n` on sample paths.
- **Command and result:** `git check-ignore -v -n` on 20 paths: **PASS**. Ignored as intended:
  `data/raw/ratings.csv`, `.env`, `.env.local`, `models/x.joblib`, `mlruns/`,
  `project-notes/BUILD_PLAN.md`, `.venv/`, `frontend/node_modules/`, `.DS_Store`. Not ignored as
  intended: `src/pmrs/__init__.py`, `tests/test_smoke.py`, `uv.lock`, `DECISIONS.md`, `SCOPE.md`,
  `CLAUDE.md`, `pyproject.toml`, `docs/evaluation.md`, `notebooks/eda.ipynb`,
  `tests/data/sample.csv`, `src/pmrs/data/loader.py`. `.env.example` matched the exception rule
  `!.env.example`, so it is tracked, as intended.
- **Unverified:** what is actually committed or pushed (no Git inspection was done); whether any
  ignored file was committed before the rules existed (unlikely, as the rules predate the data).
- **Effect:** closes the `.gitignore` verification gap listed in D-016.

## D-018 · 2026-11-12 · Owner decision · Steps 2–4 dependencies and download
- **Approved by the owner:** runtime pandas and numpy; dev pandas-stubs, plotly, ipykernel,
  nbformat, nbclient; one download of `ml-latest-small.zip` from the official GroupLens URL only
  (stop and ask if it redirects), non-commercial use, citation recorded, nothing uploaded or sent
  about the owner. Do all of Steps 2–4 as one chunk; do not start Step 5 or select its cutoffs.
- **Installed (resolved by uv):** numpy 2.5.4, pandas 3.1.1, python-dateutil 4.0.0, tzdata 2026.6,
  and the dev packages (ipykernel 7.4.0 or later, nbclient, nbformat, pandas-stubs, plotly 7.1.0 or
  later, and their helpers). `uv sync` reports 53 packages. `.venv` grew from about 97 MB to
  about 307 MB; free disk was 12 GiB before and the data is 4.1 MB.
- **My additions (not asked):** `ruff format` applied to the new code and the notebook; per-file
  ruff setting to skip the line-length rule in notebooks (`pyproject.toml`).

## D-019 · 2026-11-12 · Source record · MovieLens `ml-latest-small`
- **Source:** official GroupLens page https://grouplens.org/datasets/movielens/latest/ links to
  https://files.grouplens.org/datasets/movielens/ml-latest-small.zip. The server answered 200 with
  no redirect (HEAD check) and a 978,202-byte file; the download matched that size.
- **SHA-256 of the archive:** `696d65a3dfceac7c45750ad32df2c259311949efec81f0f144fdfb91ebc9e436`.
  **No official checksum is published on that page**, so no comparison was possible (NOT RUN).
- **Licence conditions** (from the dataset README, read 2026-11-12; not legal advice): use for
  research purposes; may not state or imply endorsement by the University of Minnesota or
  GroupLens Research; must acknowledge use in resulting publications; may redistribute the data
  and transformations only under these same conditions; **no commercial or revenue-bearing use**
  without permission from a GroupLens faculty member. The README also calls it a development
  dataset, not appropriate for shared research results.
- **Required citation:** F. Maxwell Harper and Joseph A. Konstan. 2015. The MovieLens Datasets:
  History and Context. ACM Transactions on Interactive Intelligent Systems (TiiS) 5, 4, Article 19
  (December 2015), 19 pages. DOI: http://dx.doi.org/10.1145/2827872
- **Storage:** `data/raw/ml-latest-small/` and the zip in `data/raw/`; git-ignored, never committed.
  The tracked test fixtures in `tests/data/tiny/` are invented, not dataset rows. The notebook
  contains aggregate statistics and tag-text counts only.
- **Needed later:** the citation and non-commercial notice in the README and in the app (Steps 33–34).

## D-020 · 2026-11-12 · Execution · Steps 2–4 results
- **Built:** `src/pmrs/data/{__init__,download,loaders}.py`; `tests/test_loaders.py`,
  `tests/test_download.py`, `tests/data/tiny/*.csv`; `notebooks/01_eda.ipynb`.
- **Commands and results:** `uv run python -m pmrs.data.download` PASS (5 expected files, none
  missing); `uv run pytest` PASS (24 tests, including real-data counts equal to the README and zero
  rows dropped); `uv run ruff check` PASS; `uv run ruff format --check` PASS; `uv run mypy` PASS (4
  files); notebook execution with `nbclient` PASS (0 error outputs, 8 figures; about 196 KB); `uv sync`
  PASS (53 packages). Mistakes: my first ruff run flagged long lines and three unused mypy
  ignore comments in my own code; fixed and re-run. The notebook was re-formatted after its last
  execution and not re-executed.
- **Real-data facts:** 9,742 movies; 100,836 ratings; 3,683 tags; 610 users; 13 movies without a
  year; 34 without genres; 18 unrated movies; mean rating 3.502; density 1.70%.
- **Findings for owner decisions (Step 5):** (1) relevance threshold: recommend `>= 4.0` (48.2% of
  ratings; 603 of 610 users with at least 5 relevant) (**open, owner to confirm**). (2) A shared
  chronological split fails the plan's feasibility criteria at the example cutoffs: 13–30
  evaluated users per period vs a minimum of 100, because 59.3% of users rated everything in one day
  (**open: fallback, relaxed minimums, or other design**). (3) Tags: only 58 users tagged, 16.1% of
  movies have a tag: content model should rely on genres and title words. (4) Cutoffs were NOT
  chosen. The example percentile pairs are illustrations only.
- **Unverified:** the notebook's numbers come from one run of a development dataset; the preview
  depends on the example cutoffs; no alternative split has been tested.
- **Correction (same day):** in the final command of this chunk I accidentally invoked `git -v`
  (a stray command, with output discarded) although Git commands were not allowed. It is not a
  valid inspection or change command and I have no evidence it changed anything, but I did not
  see its output, so I cannot state that for certain. Nothing else in this chunk touched Git.

## D-021 · 2026-11-12 · Owner decision · Step 5 evaluation protocol (supersedes the shared chronological split in the plan; resolves the open item in D-020)
- **Owner decisions:** (1) a relevant rating is `>= 4.0`. (2) Evaluation uses a **per-user temporal
  holdout**: each user's latest ceil(10%) of ratings are test, the preceding ceil(10%) validation;
  equal timestamps stay together and a boundary tie goes to the later period. (3) A user is not
  scored if fewer than 10 ratings remain in train or either held-out period exceeds 30% of their
  ratings; their eligible train ratings stay in the fit. A user is evaluated in a period only with
  at least one relevant item there. (4) A tag is usable only if earlier than its own author's
  cutoff; a no-tags content variant is reported too. (5) SciPy is a runtime dependency (sparse
  matrix); `scipy-stubs` is NOT added unless mypy shows it is needed, and then proposed separately.
  (6) A separate **simulated** cold-start evaluation on a fixed-seed 20% of users kept out of every
  fit, with 0, 3, 5 and 10 revealed ratings; the zero-history case may measure the popularity
  fallback. It is a simulation, not real new-user evidence, and MovieLens cannot measure the
  favourite-genre onboarding path. (7) The global-split minimums are not relaxed and no claim of
  adequate power for a global split is made.
- **Claim limit (binding for every report and README):** results support only "methods compared
  under the same per-user holdout protocol". They do not support "globally leakage-safe" or
  "predicts future behaviour": users' cutoffs differ but models are fitted once, so a model scoring
  a user still contains other users' ratings and tags from after that user's cutoff (measured in
  D-022).
- **My interpretations, for the owner to correct:** (a) excluded users contribute train ratings
  only, in both the validation fit and the test refit (their validation ratings are not used);
  (b) the 20% cold-start users are removed from the warm evaluation too, so warm results come from
  the 80% of users the models were fitted on; (c) tags by users who have no ratings are dropped
  (no cutoff exists for them); (d) the cold-start sample is drawn from all users (seed 42), then
  filtered by the same eligibility and relevance rules.
- **Records updated:** `CLAUDE.md` (ML rules, current state, commands), `SCOPE.md` (wording),
  `PROJECT_GUIDE.md` §7 and the risk and open-decision tables, `BUILD_PLAN.md` Step 5 and the
  Step 14 to 16 wording, `ARCHITECTURE.md` (module row).

## D-022 · 2026-11-12 · Execution · Step 5 results
- **Built:** `src/pmrs/split/{__init__,__main__,holdout,matrix,protocol,report}.py`;
  `tests/test_split.py` (31 tests); `scipy>=1.18.1` added (resolved 1.18.1). Output written to
  `data/processed/split/` (git-ignored): assignments, per-user flags, six feasibility tables.
- **Measured (real data, 610 users, 100,836 ratings):** train 79,575 / validation 10,624 / test
  10,637 ratings. 603 users eligible, 7 excluded (4 held-out share above 30%, 3 both reasons).
  Cold-start holdout 122 users; 488 users in the fit. Evaluated users: warm 450 validation / 453
  test; cold-start simulation 119 validation / 113 test (569 and 566 in total, as proposed). Relevant
  held-out items: warm 3,858 / 4,091; cold-start 985 / 916. Tags usable: 1,359 for validation fits,
  3,048 for test fits of 3,683 (359 tags are by cold-start users and never used).
- **Measured leakage:** for scored warm users, the share of the fit dated at or after their own
  cutoff has median 52.3% (validation) and 48.9% (test), ranging from about 10% to about 96% across
  users (10th to 90th percentile); the median share of usable tags dated after the user's cutoff
  is 99.2% (validation) and 50.2% (test). This cross-user future-data leakage is not removed.
- **Mypy and SciPy:** `mypy` (strict) reports SciPy as untyped (`import-untyped`). Without adding
  `scipy-stubs` (not approved), the two SciPy imports carry a narrow `# type: ignore[import-untyped]`.
  SciPy types are therefore `Any`. **Proposal, awaiting owner approval:** add `scipy-stubs` (dev) and
  remove the ignores.
- **Not verified:** no model has been run on the split; the cold-start simulation is only data
  preparation so far; the split on `ml-latest-small` is not assessed for other datasets.

## D-023 · 2026-11-12 · Owner decision and correction · Cold-start candidate sets; scipy-stubs; D-021 interpretations confirmed
- **Owner confirmed** the four D-021 interpretations: (a) excluded users still contribute eligible
  train ratings to both fits, with their validation/test ratings neither scored nor used in the
  test refit; (b) the 20% cold-start sample is removed from the warm evaluation and every fit;
  (c) tags with no usable author cutoff are dropped; (d) the cold-start sample is drawn from all
  users with seed 42, then filtered by the eligibility and relevance rules.
- **Owner approved `scipy-stubs`** (dev), matched to SciPy 1.18.1. Resolved to `scipy-stubs`
  1.18.1.1; it also installs the typing helpers `optype` 0.19.0 and `numpy-typing-compat`
  20260602.2.5. Both SciPy `type: ignore` comments were removed; strict mypy passes. This
  supersedes the "awaiting approval" proposal in D-022.
- **Bug found and corrected (owner request):** as built in D-022, the candidate set for a
  cold-start simulation user was not defined; the generic rule (exclude all pre-cutoff items)
  would have used the user's hidden train/validation ratings to filter a "new" user's candidates.
  **Corrected rule:** warm users exclude their known pre-cutoff items; a cold-start simulation
  user excludes only the ratings revealed for that history size (0, 3, 5, 10). History 0 excludes
  nothing. Hidden train, validation and test ratings never filter candidates; held-out items stay
  eligible. Code now refuses a cold-start candidate request without a history size, and refuses a
  history size for warm users.
- **Effect (measured):** mean cold-start candidates are 9,742 / 9,739 / 9,737 / 9,732 movies for
  history 0 / 3 / 5 / 10, and 100% of cold-start users' relevant held-out items are candidates at
  every history size. Hidden train items of a cold-start user are ranked as unknown movies, which
  is stricter on the models (a hidden item the user liked counts as a miss).
- **Leakage limitation unchanged:** the claim stays "methods compared under the same per-user
  holdout protocol"; models are still fitted on other users' ratings and tags dated after a scored
  user's cutoff (D-022).
- **Records updated:** `CLAUDE.md`, `PROJECT_GUIDE.md` §7, `BUILD_PLAN.md` Steps 5 and 14,
  `BUILD_LOG.md`. D-021 and D-022 are kept as written.

## D-024 · 2026-11-12 · Owner decision and record · Gate 1 approved; Phase 2 Chunk A (Steps 6-9) approved and built
- **Owner decision:** Gate 1 approved. Phase 1 is complete and the Step 5 protocol in D-021 and D-023
  is accepted, including its stated limits. The claim stays "methods compared under the same
  per-user holdout protocol"; models are fitted once and still see other users' ratings and tags
  dated after a scored user's own cutoff.
- **Owner decision:** Phase 2 Chunk A = Steps 6-9 only (baselines, content-based, item-kNN, SVD,
  with a shared scoring interface and tests). The hybrid, explanations, artifact packaging,
  metrics, API, database, frontend and deployment were not started.
- **Owner decision:** `scikit-learn` added as a runtime dependency. Resolved to scikit-learn 1.9.1;
  it also installed `joblib` 1.6.0, `threadpoolctl` 3.8.0 and `cloudpickle` 3.1.2. Measured:
  `.venv` grew from 387 MB to 434 MB; free disk was 17.7 GiB before the install and 17.6 GiB
  after (the older "about 12 GiB" figure in `CLAUDE.md` was out of date).
- **`joblib` is not declared in `pyproject.toml` yet** because no code imports it. It is declared
  when artifact save/load is written (Step 12). This is the one place where the plan wording
  ("declared") is followed later rather than now; it was stated in the Chunk A proposal.
- **Provisional defaults (owner: keep as provisional, tune on validation only at Step 15; not
  final):** Bayesian prior strength 10; kNN neighbours 50 and shrinkage 10; SVD factors 50
  (seed 42); content feature-group weights all 1.0 (genres, tags, title words, decade);
  random seed 42.
- **Interpretations I made (mine, not owner decisions; reviewable):**
  (a) kNN score = shrunk-similarity-weighted average of the user's centred ratings over the
  movie's kept neighbours; only positive similarities are kept; a movie with no neighbour in the
  user's history has no evidence and scores `-inf` (ranked last). No extra damping term.
  (b) SVD ranks by the unclipped predicted deviation (so scores do not tie at 0.5 and 5);
  `predict_ratings` gives the clipped 0.5-5 value. Unrated cells count as "the user's average"
  (a TruncatedSVD property; there is no ALS or FunkSVD in scikit-learn).
  (c) Content profile: items rated above the user's own mean, weighted by the gap; if none, all
  history items weighted by rating; empty history scores zero everywhere.
  (d) `RandomScorer` draws from the seed plus the user's history, so results are reproducible.
  (e) Because the history excludes exactly the revealed or pre-cutoff items, "exclude the history"
  equals the D-023 candidate rule; a test confirms this against `candidate_items`.
- **Memory design:** the item-item similarity matrix is never held in full; it is computed
  500 movies at a time and reduced to the top neighbours (tested against a brute-force
  calculation for several block sizes).
- **Open (needs owner decision): strict mypy.** scikit-learn 1.9.1 ships no type information
  (`import-untyped`), which gives 3 strict-mypy errors at the three `sklearn` imports
  (`sklearn.decomposition`, `sklearn.feature_extraction.text`, `sklearn.preprocessing`). Nothing
  was changed to hide them. Options: (1) one `[[tool.mypy.overrides]]` entry for `sklearn.*`
  (config change; scikit-learn values become `Any`); (2) three inline `type: ignore` comments
  (the approach first used for SciPy); (3) a third-party stubs package, which I have not
  searched for and which would need your approval as a dependency. I recommend (1).
- **Checks (2026-11-12):** pytest PASS (105 tests: 63 earlier + 42 new); ruff check PASS; ruff
  format --check PASS; mypy strict **FAIL** (3 errors, all the scikit-learn issue above);
  `uv run python -m pmrs.split` PASS; real-data smoke run PASS (see BUILD_LOG for numbers).
- **Not verified:** recommendation quality (no metric was computed; metrics are Phase 3); SVD and
  kNN under the test refit (the smoke run used the validation fit only); behaviour on any data
  other than `ml-latest-small`. Sample lists are a human spot check, not evidence.
- **Records updated:** `CLAUDE.md`, `BUILD_PLAN.md` (Steps 6-9 status), `BUILD_LOG.md`.

## D-025 · 2026-11-12 · Owner decision · One mypy override for scikit-learn (resolves the open item in D-024)
- **Owner decision:** approve one narrow `[[tool.mypy.overrides]]` entry (`module = "sklearn.*"`,
  `ignore_missing_imports = true`) in `pyproject.toml`. No stubs dependency and no inline
  `type: ignore` comments.
- **Result (2026-11-12):** strict `mypy` **PASS**, no issues in 17 source files; no additional
  errors appeared, so no project code needed changing. `grep` finds 0 `type: ignore` in `src`.
  Also re-run: pytest PASS (105), ruff check PASS, ruff format --check PASS,
  `python -m pmrs.split` PASS, smoke run (SVD model) PASS, `uv sync` PASS (61 packages).
- **Known limitation:** scikit-learn values (the TF-IDF vectorizers, `normalize`, `TruncatedSVD`
  and what they return) are `Any`, so mypy does **not** check how they are used. Our own code
  around them is still checked strictly; the behaviour of those calls is covered by the tests,
  not by the type checker.
- **Unchanged:** split protocol, model behaviour, scope. Chunk B not started. This supersedes the
  "strict mypy FAIL" status in D-024.

## D-026 · 2026-11-12 · Owner decision and record · Phase 2 Chunk B (Steps 10-12) approved, repaired and finished
- **Owner decisions (approvals recorded, not recommendations):** (a) Chunk B approved with the
  `joblib` dependency declared (`joblib>=1.6.0`); (b) artifacts go in the git-ignored
  `data/processed/artifacts/`; (c) ladder settings: 0 ratings = popularity (with favourite genres,
  a genre-and-popularity mix; no genres, pure popularity), 1-9 = content-heavy blend, 10+ =
  balanced blend, each method min-max scaled per user over that user's candidate movies; genre
  names are plain names. (d) After a first attempt left the code in an inconsistent state, the
  owner asked this session to take over Chunk B, repair the existing code into one design and
  finish. No other scope, dependency or protocol change was made.
- **What went wrong (plain account):** the first attempt left `recommender.py` written against one
  explanation interface (`Catalog`, `content_evidence(...)` helper functions, `Evidence.sentence`,
  kind `"none"`) while `explain.py` and the five models used another (`scorer.evidence(history,
  item)` plus `render(...)`, kind `"no_evidence"`). `explain.py` had been overwritten without
  being read first, and the original is not recoverable by this session. Result: 15 mypy errors
  and 12 Ruff findings. Nothing was wrong with the Step 5 split, the Chunk A models or their
  scoring.
- **Design chosen (one interface):** `scorer.evidence(history, item)` returns an immutable
  `Evidence`; `explain.render(evidence, title_of)` is the only place sentences are written;
  `explain.Catalog` holds titles and display genres; `Recommender` calls both and keeps the
  evidence beside the sentence. Rejected: keeping the helper-function interface, which would have
  moved evidence logic away from the model that produced the score and needed isinstance checks.
- **A real bug found and fixed by the new tests:** `ContentScorer.evidence` treated a sparse
  matrix product as an array and crashed at run time (never executed before). Fixed by making the
  product dense first. Chunk A scoring was not affected.
- **Files:** `explain.py` (Catalog, MAX_TAGS_SHOWN = 5), `hybrid.py`, `recommender.py`,
  `artifact.py`, `cli.py` (new: `build` and `recommend`), evidence methods in the models,
  `smoke.py` (adds the hybrid and artifact round trip), `tests/test_hybrid_recommender.py` (49
  tests). `pyproject.toml` and `uv.lock` carry `joblib`.
- **Provisional, untuned settings (changeable only in `HybridConfig`, tuned on validation only in
  Step 15):** few-ratings rung 1-9; few weights content 0.60, item-kNN 0.15, SVD 0.15, popularity
  0.10; many weights 0.35 / 0.25 / 0.25 / 0.15; no-ratings-with-genres mix 0.6 genre match + 0.4
  popularity; at most 5 shared tags named in a sentence.
- **Candidate rule (unchanged, D-023):** a returned list never contains a movie in the user's
  profile and excludes nothing else. For a warm user the profile is the pre-cutoff history; for a
  cold-start simulation user it is only the revealed ratings (none for 0 revealed). Held-out items
  stay eligible. A test checks every strategy against several profile sizes.
- **Artifacts and security:** an artifact is `recommender.joblib` plus `metadata.json` (schema
  version, creation time, split target, seed, data hash, counts, library versions, settings,
  model size and SHA-256). Saving never overwrites. Loading checks size, SHA-256, schema and that
  the metadata matches the model, and warns if library versions differ. **A joblib file is a
  pickle: loading can run any code in it. Load only artifacts this project built. The SHA-256
  check catches accidents, not tampering**, because whoever can replace the model file can also
  replace its metadata. The warning is stored in the metadata and printed by the CLI every time.
- **Checks (2026-11-12):** pytest PASS (154: 105 earlier + 49 new); ruff check PASS; ruff format
  --check PASS; strict mypy PASS (22 files); full real-data smoke run PASS (all models and the
  hybrid, round trip identical); CLI build and recommend on real data PASS; a second CLI build
  correctly refused to overwrite. `uv sync` NOT RE-RUN this chunk beyond the earlier `uv add`.
- **What the tests do and do not show:** they prove mechanics (ladder rungs and boundaries,
  scaling and blending arithmetic, sentences built only from evidence, no rated movie ever
  returned, save/load identical, damage detected). They are **not** evidence that any method
  recommends well; no metric was computed (Phase 3).
- **Not verified / still open:** recommendation quality of every method and of the blend; the
  `test` target artifact (not built; the test split must stay unread until the final refit);
  behaviour across different library versions (only a warning); explanation truthfulness beyond
  "the sentence only uses its evidence" (a sentence describes what the mechanism did, not why the
  user would like the movie); the CLI was exercised on the validation artifact only.
- **Records updated:** `CLAUDE.md`, `BUILD_PLAN.md` (Steps 10-12), `BUILD_LOG.md`. Gate 2 awaits
  the owner's review.

## D-027 · 2026-11-12 · Owner decision and record · Gate 2 follow-up: content-explanation wording and fuller smoke samples
- **Owner decision:** approved a focused follow-up within Chunk B: make content explanations say
  when a cited movie was used because it beat the user's own average (showing rating and average),
  use neutral wording when the model falls back to a movie that was not above average, and extend
  the smoke output (all seven strategies for one warm user; hybrid at 0, 3, 5 and 10 revealed
  ratings for one cold-start user; sentences and the user's average everywhere). No change to
  scoring, weights, split rules, candidate rules or scope; no quality metrics; Phase 3 not started.
- **Why:** the content model treats a rating as positive only relative to the user's own mean
  (user 307: mean 2.4968, so a 2.5 counts). The old sentence ("Because you rated X (2.5)") hid this
  and read as if the user liked X. The wording, not the scoring, was the defect.
- **Change:** `Evidence` gained `average` and `above_average`; `ContentScorer.evidence` fills them
  (same selection as before); `render` states the comparison, or uses neutral fallback wording.
  The printed average gets extra digits when two places would round it up to the cited rating
  ("2.497", not "2.50"). kNN and SVD sentences are unchanged (they do not call movies liked).
- **Checks (2026-11-12):** pytest PASS (160); ruff check PASS; ruff format --check PASS; strict
  mypy PASS; full smoke run PASS with 14 of 14 artifact round trips identical. Quality metrics NOT
  RUN. The neutral fallback wording is covered by tests only, not by a real-data sample.
- **Records updated:** `BUILD_LOG.md`. `CLAUDE.md` and `BUILD_PLAN.md` needed no change.

## D-028 · 2026-11-12 · Owner decision and record · Gate 2 approved; Phase 3 started; Steps 13-14 built
- **Owner decisions:** Gate 2 approved. Phase 3 (Steps 13-17) to begin per `BUILD_PLAN.md`:
  preserve the per-user holdout protocol and its limitation; tune on validation only; freeze the
  chosen settings before the final test evaluation; read the test period once; no change to the
  split or candidate rules without asking; non-commercial; no unrelated scope; report what the
  metrics mean, comparisons against baselines, uncertainty, and keep validation results distinct
  from the final test result; no Git; stop at the next approval gate.
- **Built (no new dependency, no open decision needed):** Step 13 `pmrs.metrics` (Precision,
  Recall, MAP, NDCG @K with binary relevance at rating >= 4.0; RMSE; MAE; catalogue coverage;
  intra-list genre diversity; percentile bootstrap intervals over users, paired differences and a
  pooled-ratio bootstrap). Step 14 `pmrs.evaluation` (harness, report, `python -m
  pmrs.evaluation`): every method, K = 5, 10, 20, per-user rows kept, warm users and the four
  cold-start simulation sizes (0, 3, 5, 10) reported separately.
- **Edge-case rules (decided once, in code and tests):** no relevant item gives NaN for recall,
  MAP and NDCG (precision 0) and the harness refuses NaN, because the protocol never scores a user
  with no relevant held-out movie; precision always divides by K (short lists are not rewarded);
  a repeated movie in a list is an error; two movies both with no listed genres have genre
  distance 0.
- **Recommended by the assistant, not yet owner-confirmed (confirm at the Step 15 approval):**
  headline metric NDCG@10, fixed before the first real run; the other metrics are supporting
  detail. Intervals: 2,000 user-resamples, seed 42, 95% percentile; the same resampled users are
  used for every method, so paired differences are exact. Rating error (RMSE/MAE) is reported as
  secondary on warm users only, beside two reference predictors (`global_mean`, `user_mean`) that
  are not models, so any SVD gain is visible.
- **Test-period protection (so far):** `evaluate(..., "test")` raises `ProtectedTargetError`
  unless `allow_test=True`; the command line offers `validation` only. A test rewrites every
  test-period rating value and shows validation results do not change (only the *count* of a
  user's test ratings matters, through the Step 5 eligibility rule fixed in D-021). A one-time
  read guard and the frozen-configuration hash are Step 16 work.
- **Protocol checks in code:** every list is checked against the candidate rule as it is built
  (no known movie, 20 unique movies); `verify_fit_respects_cutoffs` checks that every fitted
  rating and tag is strictly earlier than its own user's/author's cutoff in force and that no
  cold-start user is in the fit (tests prove it catches a late rating, a late tag and a cold user).
  The Step 5 candidate and cold-start rules were not changed.
- **First real validation run (2026-11-12, untuned defaults, validation period only; NOT a test
  result and NOT tuned).** Evaluated users: 450 warm; 119 cold-start simulation. Warm NDCG@10
  [95% CI]: random 0.001 [0.000, 0.002]; popularity 0.065 [0.052, 0.077]; Bayesian average 0.038
  [0.029, 0.047]; content 0.010 [0.005, 0.017]; item-kNN 0.002 [0.000, 0.006]; SVD 0.070 [0.056,
  0.084]; hybrid 0.076 [0.063, 0.089]. Paired: hybrid minus popularity +0.011 [-0.002, +0.024]
  (spans 0); hybrid minus SVD +0.006 [-0.005, +0.017] (spans 0); hybrid minus content +0.066 and
  minus item-kNN +0.073 (both exclude 0). Cold-start simulation: popularity is the strongest or
  tied for the strongest at every size; the hybrid equals popularity at 0 revealed by design and
  is *worse* than popularity at 3 and 5 revealed (-0.039 and -0.037, intervals exclude 0) and at 10
  (-0.020, [-0.045, -0.000]). Full tables: `data/processed/evaluation/validation/report.txt`.
- **Findings that bear on Step 15 (stated, not acted on):** (1) item-kNN is near random on warm
  users and recommends rare movies (coverage 0.23): its score is a weighted average with no
  minimum support, so a movie with one neighbour can score extremely high. Tuning `neighbours`
  and `shrinkage` may help, but fixing the cause would change the model's scoring (a minimum
  support rule), which is beyond "provisional parameters" and needs the owner's decision.
  (2) The content model ranks well below popularity: it has no popularity signal. (3) The
  few-ratings rung of the hybrid is content-heavy (0.60), and content is the weakest component
  here, which explains the hybrid trailing popularity at 3 and 5 revealed. (4) With 0 revealed
  ratings content, kNN and SVD all have no information and return the same tie-break order
  (lowest movie id first); their identical numbers at 0 revealed are not a method result.
- **Checks (2026-11-12):** pytest PASS (199: 160 earlier + 21 metrics + 18 evaluation); ruff
  check PASS; ruff format --check PASS; strict mypy PASS (31 files, 0 `type: ignore`);
  `python -m pmrs.split` PASS; first validation run PASS; **rerun byte-identical** on all six
  output files (reproducible); `uv sync` NOT RUN.
- **Not done / waiting for owner:** Step 15 needs MLflow (a new dependency set; size to be
  checked, owner decision if over 1 GB, per the plan) and decisions on the tuning grid and the
  item-kNN question above. Steps 15-17 not started. No test-period number exists.
- **Records updated:** `CLAUDE.md`, `BUILD_PLAN.md` (Steps 13-14), `BUILD_LOG.md`.


## D-029 · 2026-11-12 · Owner decision and record · Step 15 approved and run: tuning on validation only, proposed frozen settings

- **Owner decisions (approval given for Step 15):** the proposed grid and selection rule; NDCG@10 as
  the headline metric with precision, recall, MAP and coverage as supporting measures; check the
  size of `mlflow-skinny` and install it only if under 1 GB and leaving at least 10 GB free
  (otherwise local CSV/JSON logs); test item-kNN minimum support at 0, 5, 10 and 20 (may change
  ranking scores, must not remove movies from the Step 5 candidate set); test popularity-heavier
  weight sets for the few-ratings rung. Validation data only; test unread; split, candidate rules
  and claim limit unchanged; stop before Step 16.
- **MLflow check (measured, 2026-11-12):** `mlflow-skinny` 3.18.0 with its 39 dependencies is
  64 MB in a throwaway environment (project `.venv` grew 434 MB to 497 MB); free disk stayed about
  18 GiB. Both limits met, so it was installed as a **dev** dependency (`uv add --dev
  mlflow-skinny`). The lookup sent only the package name to the package index. MLflow 3.18 refuses
  its plain-folder store ("maintenance mode") unless `MLFLOW_ALLOW_FILE_STORE=true`; the code sets
  that (local only, nothing sent, `mlruns/` is git-ignored). A SQLite store would need extra
  packages and was not used. The CSV/JSON log is always written too.
- **Code changes:** `ItemKNNScorer(min_support=m)`: a movie rated by fewer than m fit users
  scores `-inf` and is listed after every supported movie. This changes scores only; the movie
  stays in the candidate set (tested). New `ModelSettings` (neighbours, shrinkage, min_support,
  factors, content weights; defaults reproduce the untuned system exactly, tested) accepted by
  `Recommender.fit` and `evaluate`. New `pmrs.evaluation.tuning` (`uv run python -m
  pmrs.evaluation.tuning`). Tuning has no target argument and never passes `allow_test`; a test
  records every target it touches and a source check forbids the test period.
- **Procedure:** 36 configurations in stages, each using the settings adopted earlier: item-kNN
  neighbours x shrinkage (9), then minimum support (3 more), SVD factors (3), content feature-group
  weights (9: default plus each group at x0.5 and x2), many-ratings hybrid weights (6), few-ratings
  hybrid weights (6). Objective: warm users (450) for single models and the many-ratings rung;
  cold-start 3 and 5 revealed (119 users, averaged per user) for the few-ratings rung. Rule: best
  mean NDCG@10 is adopted only if its paired 95% bootstrap interval against the reference is
  entirely above 0; otherwise the reference is kept and the result is called inconclusive. The
  run takes about 47 s and is deterministic.
- **Results (validation period only; not test; optimistic because the winner of ~36 tries was
  picked on the same users):**
  - item-kNN grid: neighbours 20, shrinkage 5 adopted: NDCG@10 0.013 vs 0.002 for the default
    (paired +0.011 [+0.006, +0.016]). Minimum support 20 adopted on top: 0.020 [0.014, 0.028],
    paired +0.007 [+0.004, +0.011] against m=0. Cost: coverage@10 fell 0.188 -> 0.080 (default
    0.233). Still far below popularity (paired -0.045 [-0.058, -0.031]): item-kNN remains weak.
    Support 20 was the largest value tried and was still improving, so a larger value might do
    better; it was not tried (outside the approved grid).
  - SVD factors: default 50 kept (20: -0.001 [-0.012, +0.010]; 100: -0.014 [-0.024, -0.003]).
  - Content weights: default kept; best mean (decade x0.5, +0.001 [-0.001, +0.003]) is
    INCONCLUSIVE. Content stays far below popularity (0.010 vs 0.065).
  - Hybrid many-ratings weights: default kept. Best mean was "svd-leaning" 0.087 vs 0.080
    (paired +0.007 [-0.000, +0.013]): INCONCLUSIVE, not adopted. Every weight set beats popularity
    on warm users, but only by about 0.015 to 0.022.
  - Hybrid few-ratings weights: "svd+popularity 0.70" (content 0, kNN 0, SVD 0.30, popularity
    0.70) adopted: 0.050 [0.030, 0.074] vs 0.020 for the default (paired +0.030 [+0.009, +0.053]).
    Against popularity it is a tie (+0.001 [-0.012, +0.012]). So the few-ratings rung stops losing
    to popularity but does **not** beat it, and is practically popularity plus a little SVD
    (coverage@10 0.003).
- **Full validation comparison after tuning (NDCG@10, untuned -> tuned):** warm hybrid 0.076 ->
  0.080 (paired +0.004 [-0.001, +0.010], inconclusive; the gain comes only from the better
  item-kNN inside it); hybrid minus popularity on warm +0.015 [+0.002, +0.028] and minus SVD
  +0.010 [0.000, 0.021]. Cold-start hybrid: 3 revealed 0.009 -> 0.049 and 5 revealed 0.013 ->
  0.052, equal to popularity (0.048, 0.050; paired +0.000 [-0.013, +0.012] and +0.002 [-0.012,
  +0.015]); at 10 revealed (many-ratings rung, not tuned on cold-start) 0.027 vs popularity 0.050,
  paired -0.023 [-0.049, -0.002]: the hybrid still trails popularity there. At 0 revealed the
  hybrid equals popularity by design.
- **Proposed frozen configuration (NOT frozen; waiting for the owner):** item-kNN neighbours 20,
  shrinkage 5, min_support 20; SVD factors 50; content weights all 1.0; many-ratings weights
  (0.35, 0.25, 0.25, 0.15) for (content, kNN, SVD, popularity), unchanged; few-ratings weights
  (0.00, 0.00, 0.30, 0.70); no-ratings genre/popularity mix 0.6/0.4 unchanged (untuned). File:
  `data/processed/tuning/proposed_frozen_config.json`, SHA-256
  `3eb9f692cf1ef337094420b72503a0a12a773b64e7ef34c3e5bb51ccfc8a246a`, which `load_frozen` checks.
  Recommendation, owner to decide: freeze exactly this (it is the output of the approved rule),
  and state in the report that the few-ratings rung is effectively popularity.
- **Open points for the owner:** (1) accept the few-ratings weights even though they remove all
  content and kNN influence, or keep the original weights for product reasons (explanations from
  the content model) at a measured cost; (2) whether to extend the minimum-support grid beyond 20;
  (3) whether the 10-revealed cold-start gap to popularity needs a look before Step 16 (it was
  not an objective); (4) accept that the 0-revealed genre/popularity mix stays untuned.
- **Checks (2026-11-12):** pytest PASS (212: 199 + 13 tuning); ruff check PASS; ruff format
  --check PASS; strict mypy PASS (33 files); tuning run PASS (36 configurations; MLflow logged 36
  runs after setting the file-store opt-out; the first run failed to log to MLflow and was
  repeated; the adopted settings were the same in both runs, though the two result files were
  not compared byte for byte); `uv sync` NOT RUN; test-period evaluation NOT RUN by
  design: no test-period number exists.
- **Remains for Step 16:** the single test read (needs `allow_test=True`, once, after the owner
  approves the frozen file), refit on train + validation, bootstrap intervals, charts,
  `docs/evaluation.md`. Step 17 and Gate 3 not started.
- **Records updated:** `CLAUDE.md`, `BUILD_PLAN.md` (Step 15), `BUILD_LOG.md`, `pyproject.toml` and
  `uv.lock` (mlflow-skinny).


## D-030 · 2026-11-12 · Owner decision · Popularity fallback for low-rating users; selected (still proposed) configuration

- **Owner decisions, made from the validation results in D-029 and the diagnostic that followed:**
  1. Users with **1 to 10 ratings get pure popularity**. This is an **owner decision based on
     validation, not a tuning-grid winner**: the tuned SVD/popularity blend tied popularity on
     NDCG@10 (3 revealed: +0.0003 [-0.013, +0.012]; 5 revealed: +0.0020 [-0.012, +0.015]) and showed
     no clear measured advantage. It was 33-34 distinct movies in 119 users' top-10 lists against
     13-14 for popularity (0.35% against 0.14% of the 9,742-movie catalogue), and 7.7-7.9 of 10
     movies were shared with popularity. Pure popularity (0, 0, 0, 1) was not in the approved grid.
  2. The **cold-start simulation at 0, 3, 5 and 10 revealed ratings uses popularity**. At 3 and 5
     it tied the hybrid; at 10 the hybrid was worse (-0.0228 [-0.0487, -0.0022] hybrid minus
     popularity). The **10+ hybrid is kept for warm users**.
  3. Warm-user 10+ weights (0.35, 0.25, 0.25, 0.15), SVD factors 50, content weights (all 1.0)
     and item-kNN (neighbours 20, shrinkage 5) stay as in D-029. **Item-kNN minimum support stays
     at 20 for comparison; nothing above 20 is searched.**
  4. The zero-rating favourite-genre mix (0.6 / 0.4) stays **provisional and untuned**: MovieLens
     cannot measure the value of onboarding genre choices.
- **How it is built (one ladder, no separate evaluation-only path):** `few_max = 10` and
  few-ratings weights (content 0, kNN 0, SVD 0, popularity 1). So 0 ratings use the genre/popularity
  mix (or popularity with no genres), 1-10 ratings use popularity, and 11 or more ratings use the
  hybrid. Every warm validation user has 12-2,158 ratings, so no warm user falls in the popularity
  rung; **exactly 11 ratings was never evaluated** (a boundary consequence of the owner's rule
  at the evaluated size 10). The code defaults in `HybridConfig` are unchanged (still the
  provisional untuned values); the selected values live in the configuration file only.
- **Files:** `data/processed/tuning/grid_winner_config.json` (what the selection rule alone chose,
  SHA-256 `3eb9f692...`, kept for the record) and `data/processed/tuning/proposed_frozen_config.json`
  (the selected configuration, SHA-256
  `e68a7ee613e27719e7369f592ce438cd8fb7b4ff5887a55af4ce39d5eecce2b5`), which carries a
  `provenance` section labelling each choice as grid winner, default kept, owner decision, or
  untuned, and a `routing` section. Code: `pmrs.evaluation.selection`
  (`uv run python -m pmrs.evaluation.selection` writes the file and runs the checks). It is
  **still proposed, not frozen**: freezing needs the owner's explicit approval, and Step 16 has not
  started.
- **Validation checks (2026-11-12, validation period only), all PASS:** the selected file loads and
  its hash matches; settings equal the grid winner; every evaluated user lands on the intended rung
  (warm 450 users: 10+ hybrid; 0 revealed: no-ratings rung; 3, 5, 10 revealed: popularity rung);
  at 0, 3, 5 and 10 revealed every one of the 119 hybrid top-20 lists equals the popularity list
  and the paired NDCG@10 difference is exactly +0.0000 [+0.0000, +0.0000]; popularity, content,
  item-kNN, SVD and Bayesian average and the warm hybrid are identical to the saved grid-winner run
  (maximum gap 0.0); favourite genres at 0 ratings still use the genre/popularity mix.
- **Expected results confirmed:** cold-start NDCG@10 is now popularity's: 0.046 (0 revealed), 0.048
  (3), 0.050 (5), 0.050 (10). Warm hybrid is unchanged at 0.080 [0.066, 0.094]; against popularity
  +0.015 [+0.002, +0.028], against SVD +0.010 [0.000, 0.021]. The cold-start numbers are no longer
  a hybrid result at all; they are the popularity baseline reported under the hybrid's name, and
  Step 16 must say so.
- **Still unverified / limits:** any test result (none exists; the test period was not read); how
  well the choices generalise beyond these validation users (the choices were made after seeing
  these results); 11 ratings; the meaning of the cold-start simulation as new-user evidence.
- **Checks:** pytest PASS (215: 212 + 3 for the routing and the labelled file); ruff check PASS;
  ruff format --check PASS; strict mypy PASS (34 files); validation routing checks PASS (18 of 18);
  `uv sync` NOT RUN; test-period evaluation NOT RUN by design.
- **Records updated:** `CLAUDE.md`, `BUILD_PLAN.md` (Step 15), `BUILD_LOG.md`. No dependency was
  added in this step; no Git command was run; split and candidate rules unchanged.

## D-031 · 2026-11-12 · Owner decision · Configuration frozen for Step 16

- **Owner decision:** the owner approved freezing `data/processed/tuning/proposed_frozen_config.json`
  as the frozen configuration. Its content hash is
  `e68a7ee613e27719e7369f592ce438cd8fb7b4ff5887a55af4ce39d5eecce2b5`. **No setting in it may be
  changed.** Any change would need a new owner decision and a new hash, and would void the
  one-time test read.
- **What the hash is:** the project's `canonical_hash` of the file's content with the `status` and
  `sha256` fields left out (`pmrs.evaluation.tuning`). It is **not** the SHA-256 of the file's raw
  bytes (those differ: `29f7b245...`). Verified 2026-11-12: recomputing it gives the approved value.
- **The file still says `"status": "PROPOSED"`.** The file was deliberately not edited, because
  the owner said not to change it; the status field is outside the hash, so this record, not the
  file text, is what says it is frozen.
- **Contents in brief:** seed 42; 0 ratings use the 0.6/0.4 genre/popularity mix (or popularity with
  no genres); 1-10 ratings use pure popularity; 11+ ratings use the hybrid (content 0.35, item-kNN
  0.25, SVD 0.25, popularity 0.15); item-kNN neighbours 20, shrinkage 5, minimum support 20; SVD
  factors 50; content weights all 1.0. Provenance labels are in the file and in D-030.
- **Not done:** Step 16 has not started. The test period has not been read. No test-period number
  exists. `uv sync` NOT RUN. No Git command was run for this record.
- **Records updated:** `DECISIONS.md`, `BUILD_LOG.md` (current status). Nothing else was changed.

## D-032 · 2026-11-12 · Execution · Step 16 final test evaluation (single read)
- **Preflight (owner-required):** (1) the frozen file's `status` now says FROZEN; the hash
  `e68a7ee6...ce2b5` covers the settings fields only (`status` and `sha256` are left out), so it
  did not change; `load_frozen` accepts the file. No setting changed. (2) `uv sync --locked
  --dry-run` showed no changes; `uv sync --locked` made none. (3) pytest 220, ruff, mypy PASS;
  validation dry run PASS (warm hybrid 0.080, as in Step 15).
- **Built:** `pmrs.evaluation.final` (the only module passing `allow_test=True`; checks the
  frozen status and hash; refuses a second test read), `tests/test_final.py` (5 tests); one guard in
  `selection.write_selected` so a frozen file is never rewritten. Plotly was already declared; two
  narrow `# type: ignore[import-untyped]` comments for it. No dependency added.
- **Result (test, read once, 453 warm / 113 cold-start users):** warm NDCG@10 hybrid 0.064
  [0.052, 0.077], SVD 0.055, popularity 0.047, Bayesian 0.032, item-kNN 0.021, content 0.007,
  random 0.002. Hybrid minus popularity +0.017 [+0.006, +0.029]; minus SVD +0.009 [+0.001, +0.017].
  Cold-start: the hybrid IS popularity (0.031 to 0.035), no hybrid advantage; Bayesian average was
  nominally higher (spans zero). Full tables in `docs/evaluation.md`.
- **Claim:** methods compared under the same per-user holdout protocol; not leakage-safe, not a
  prediction of future behaviour. Nothing was tuned after reading the test period.
- **Verified:** per-user file means equal summary values (120 rows, 0 mismatches); report values match
  the CSVs; run files carry the frozen hash; cold-start hybrid equals popularity per user.

## D-033 · 2026-11-12 · Execution · Step 17 serving artifacts and model card draft
- **Owner decisions (approved):** build both artifacts; the serving artifact is fitted on all
  MovieLens ratings and tags including the test period and the cold-start users; the Step 16
  metrics apply only to the evaluated model; add a SHA-256 manifest; keep both local and git-ignored;
  the model card says the artifacts hold anonymized user IDs and rating histories (no claim of no
  personal data); the serving-vs-evaluated comparison is a diagnostic only.
- **Built:** `pmrs.evaluation.serving` (`build`, `verify`), `tests/test_serving.py` (4 tests),
  `MODEL_CARD.md` (draft). Artifacts: `evaluated_step16` (4.7 MB) and `serving_all_data` (5.3 MB),
  each with `MANIFEST.sha256`, `metadata.json`, `provenance.json`, `frozen_config.json`. The existing
  artifact code was reused unchanged; `serving_fit_data` is a new all-data fit. Split, candidate rules,
  evaluation protocol and Step 16 results unchanged. No dependency added.
- **Checks:** 21 load-and-recommend checks PASS (manifest and frozen hash, fit counts, frozen settings,
  routing at 0/3/5/10/11/20 ratings for both artifacts, genre mix, evaluated lists equal an in-memory
  refit for 40 warm users); pytest 224, ruff, mypy PASS; Step 16 result files and `docs/evaluation.md`
  byte-identical before and after (SHA-256 compared). Disk free 18.23 GB before and after (artifacts 10 MB).
- **Not done / limits:** Step 16 test metrics were NOT recomputed (NOT RUN, by design); the serving
  artifact has no metric; exactly 11 ratings still not evaluated. Diagnostic: lists differ for all 40
  sampled users, mean top-10 overlap 0.60. No Git command run. Gate 3 awaits the owner.

## D-034 · 2026-11-12 · Owner decision · Gate 3 approved: ML core frozen for V1
- **Owner decision:** Gate 3 is approved. The Step 16 evaluation (`docs/evaluation.md`) is accepted.
  The ML core is frozen for V1 with the recorded configuration (hash `e68a7ee6...ce2b5`, D-031), the
  artifacts `evaluated_step16` and `serving_all_data` (D-033), the Step 16 results (D-032) and their
  limitations. Models and the evaluation protocol are not to be changed on the basis of these results.
- **Limitations carried forward:** results compare methods under the same per-user holdout protocol and
  do not establish leakage-safe future prediction; the cold-start numbers are the popularity fallback;
  exactly 11 ratings was not evaluated; the serving artifact has no metric.
- **Not started:** Phase 4. No other change made for this record.

## D-035 · 2026-11-12 · Execution · Phase 4, chunk 4A (Steps 18-19): database and seed, code written
- **Owner decisions (approved):** chunk 4A only (no auth, catalogue, interactions, recommendations or
  dashboard); SQLAlchemy, Alembic, psycopg and pydantic-settings; one shared `ratings` table (as in
  ARCHITECTURE.md); MovieLens users are clearly historical non-login users and future authentication
  must not be able to sign in as one; original MovieLens rating timestamps are kept; no Postgres image
  is pulled until the owner approves after seeing size and disk figures.
- **Built (not yet run against a database):** `pmrs.db` (`models`, `settings`, `seed`), Alembic setup
  (`alembic.ini`, `migrations/`, revision 0001), `compose.yaml` (Postgres 17 alpine, loopback port
  5433), `.env.example` (names only), `tests/test_db.py` (10 tests; 6 need the test database).
- **Design choices (mine, for review):** (1) historical users are separated by an `is_historical` flag
  AND a database CHECK constraint: a historical row must have a `movielens_user_id` and no email and no
  password hash, and a registered row must have both; the database refuses anything else, so no login
  credential can exist for a historical user. Step 20 must additionally look users up by email only.
  (2) `users.id` is the table's own key; the MovieLens id is a separate unique column. (3) Emails must be
  lower-case (check constraint). (4) Ratings are `numeric(2,1)` with a half-star 0.5-5 check, key
  (user, movie), `rated_at` timestamptz built from the original Unix seconds. (5) Seeding inserts
  with "do nothing on conflict" in one transaction, then `verify` compares every movie and rating with
  the CSV data, so a silently different row is reported. (6) Host port 5433, because another Postgres
  (not this project's) already listens on 5432.
- **Dependency note:** `psycopg[binary]` was installed (the `[binary]` extra adds prebuilt wheels so no
  system libpq is needed); resolved alembic 1.20.1, psycopg 3.3.8, pydantic-settings 2.16.2,
  sqlalchemy 2.1.8. No other dependency; pydantic was already present.
- **Not run:** every check that needs PostgreSQL (migrate up/down, constraints, seeding twice, counts).
  The image `postgres:17-alpine` has NOT been pulled; waiting for the owner.
- **Unchanged:** split, recommender, evaluation results and artifacts. No Git command run.

## D-036 · 2026-11-12 · Execution · Phase 4, chunk 4A (Steps 18-19) run and verified
- **Owner decisions (approved):** pull `postgres:17-alpine`; `psycopg[binary]` accepted as the
  implementation of the approved psycopg; the other project's PostgreSQL on port 5432 is not to be
  contacted (it was not; this project's database uses loopback port 5433).
- **Measured:** image 415 MB on disk (116 MB compressed content), above my 250-300 MB estimate. Database
  files 88 MB; Docker volume 92 MB. Free disk 16.16 GiB after the pull, 14.80 GiB after seeding (the
  drop is larger than the image and volume together; the rest is not explained by this work). Above the
  10 GiB stop limit throughout.
- **Result:** all database checks PASS. Tests used only the separate `pmrs_test` database. On the dev
  database `pmrs`: migration 0001 applied; the first seed added 610 users, 9,742 movies and 100,836
  ratings and verified identical to the CSVs; the second seed added 0 of each and verified again.
  Counts: 610 users (all historical, 0 with an email or password hash), 9,742 movies, 100,836 ratings,
  1,572 movies with tag text (equals the number of movies in `tags.csv`). Spot checks: Toy Story and
  The Matrix rows match; user 1's rating of movie 1 is 4.0 at 2000-07-30 18:45:03 UTC = Unix 964982703,
  the CSV value, so original timestamps are kept.
- **Steps 18 and 19 are complete.** Chunk 4B (Steps 20-22) has not started.
- **Unchanged:** split, recommender, evaluation results, artifacts, protocol. No Git command run.

## D-037 · 2026-11-12 · Execution · Phase 4, chunk 4B (Steps 20-22): accounts, catalogue, interactions
- **Owner decisions (approved):** dependencies FastAPI, uvicorn, argon2-cffi, PyJWT and dev-only httpx;
  the catalogue is readable without login, everything user-specific needs a token; 60-minute access
  tokens, no refresh token, no server-side logout, and the API is local only: **do not expose it
  publicly until rate limiting and HTTPS are addressed**; Argon2id with a password minimum of 15 and
  maximum of 128 characters, passphrases allowed, never silently truncated; `JWT_SECRET` from a
  cryptographically secure generator, never printed or logged; rating, watched, watchlist, like and
  dislike are independent actions; the 5-rating minimum for rating-based sorting stays; `DELETE /me`
  added (own account only, never a historical user); the manual walkthrough used the test database.
- **Interpretation to confirm:** I kept like and dislike mutually exclusive (liking replaces a dislike
  and the reverse), as in the proposal's table, while rating, watched, watchlist and like/dislike
  stay independent of each other. If you meant that a movie may be liked and disliked at once, say so.
- **Schema:** no change. Cascading deletes and the unique (user, movie, kind) key already existed.
  Seed, recommender, evaluation, artifacts and protocol are unchanged.
- **Built:** `pmrs.api` (`app`, `settings`, `security`, `deps`, `schemas`, `catalogue`, `auth`, `me`,
  `movies`, `actions`), `tests/conftest.py` (shared throwaway-database fixture; `test_db.py` now uses it),
  `tests/test_api.py` (24 tests). Run: `uv run uvicorn pmrs.api.app:create_app --factory`.
- **Routes:** `POST /auth/register|login`; `GET/PUT/DELETE /me`, `PUT /me/genres`, `GET /me/history`,
  `GET /me/watchlist`; `GET /movies`, `GET /movies/{id}`; `PUT|DELETE /movies/{id}/rating|like|dislike|
  watchlist|watched`; `POST /movies/{id}/view`. No route takes a user id.
- **Rules (mine, for review):** registration lower-cases the email and returns 409 for a duplicate
  (this reveals that an email exists; accepted for the demo). Login uses the same answer and the same
  hashing work for an unknown email and a wrong password. A rating update sets `rated_at` to now.
  Sorting by rating puts movies with at least 5 ratings first; the rest follow by rating count.
  A repeat `viewed` only refreshes the time (the schema cannot count views). 422 responses do not echo
  submitted values, so a rejected password is never returned. A token that names a historical user is
  refused.
- **Results (test database only):** 24 API tests PASS; full suite 258 passed, 0 skipped; ruff, ruff
  format, strict mypy (51 files) PASS; `uv sync --locked` PASS. A deliberate break (removing the
  historical-user guard) made the historical test fail, and it passed again once restored. Manual
  walkthrough on a throwaway copy of the real data in `pmrs_test` PASS (dropped afterwards; the dev
  database was untouched: 610 users, 0 registered, 100,836 ratings, 9,742 movies). Query times on the
  real data, median of 15: list 26.6 ms, search 34.3 ms, genre+year 32.3 ms, sort by rating 29.1 ms,
  by popularity 25.0 ms, detail 3.8 ms (local, one user, one process; not a load test).
- **Not done / limits:** no rate limiting, no HTTPS, no token revocation (a deleted user's token stops
  working because the user is gone, but a stolen token of a live user works until it expires); CORS not
  configured (frontend phase); recommendations, dashboard and analytics (chunk 4C) not started. A
  Starlette warning recommends `httpx2` for the test client; not installed (unapproved).

## D-038 (2026-11-12): like and dislike are mutually exclusive (owner-confirmed)

- **Owner decision:** the owner confirmed the interpretation flagged in D-037. Like and dislike are
  mutually exclusive: adding one removes the other. Ratings, watched status and watchlist status stay
  independent of each other and of like/dislike. No code change was needed; the API already behaves
  this way and has tests for it.

## D-039 (2026-11-12): chunk 4C, recommendations, dashboard and analytics (Steps 23-24)

- **Owner decisions (approved):** use the existing `serving_all_data` artifact without changing or
  retraining anything, and state that it has no separate quality metric and that the Step 16 results
  apply only to the evaluated model. Expose `hybrid`, `popularity`, `content`, `item_knn` and `svd`;
  `random`, `bayesian_average` and content-without-tags stay evaluation-only (said in the API docs).
  Profiles use the signed-in user's ratings and favourite genres only; likes, dislikes, watched and
  watchlist are never model inputs, and watched and disliked movies may be hidden from displayed lists.
  An `acted` event is recorded automatically by the existing action routes when the user acts on a
  movie previously served; "shown" means *served by the API*, not seen, and nothing claims an action
  was caused by a recommendation. `/analytics/*` requires login. CORS allows exactly the configured
  frontend origin, no wildcard. The dashboard has all seven panels and reuses the recommendation
  service without duplicate event logging.
- **Built:** `GET /me/recommendations?strategy=&k=` (k 1-50), `GET /me/dashboard`, and
  `GET /analytics/summary|popular|ratings-distribution|engagement`. Startup verifies the artifact's
  SHA-256 manifest and frozen-config hash with the existing `load_verified`, then loads it once; the app
  refuses to start if that fails. `create_app` takes an optional stand-in recommender for tests.
  `FRONTEND_ORIGIN` (default `http://localhost:5173`, validated: scheme, host, optional port, no path,
  no wildcard) and `SERVING_ARTIFACT_DIR` are settings. No schema change, no new dependency.
- **Recommendation rules (my choices within your decisions, each testable):**
  - Hybrid routing is the frozen one (D-030). The response names the branch and gives a plain reason;
    with 0 or 1-10 ratings it says the list is not personalised.
  - Hidden movies are filtered after the model runs; the request asks for k plus the number hidden so
    the list is still k long. Watchlist and liked movies stay visible and show their state.
  - `content`, `item_knn` and `svd` with zero ratings return an empty list and a note, because the
    models have no evidence and would otherwise return an arbitrary list (checked: movie ids 1, 2, 3).
    With 1-10 ratings they work but carry a note that they were only evaluated for users with many.
- **Event rules:** a `shown` event is written for each movie returned, per call. An `acted` event is
  written when the user adds or changes (not removes) a rating, like, dislike, watchlist, watched or
  view on a movie that has a `shown` event, once per serving; it carries the latest serving's strategy.
  Because the schema stores only shown/acted, the kind of action is not kept. The dashboard's
  recommended panel goes through the same function, so it logs once.
- **Dashboard definitions:** trending = ratings and actions by registered users in the last 30 days;
  if there are none, the most-rated movies in the final 365 days of the MovieLens data (ending at its
  last rating, not today), with the source and window stated. The dataset fallback uses 365 days because
  the last 30 days hold at most 4 ratings per movie. "Recent releases" is by release year, not by when
  a movie was added.
- **Analytics:** aggregates only, MovieLens and app numbers always in separate fields, engagement only
  from `recommendation_events`.
- **Measured (local, one client, median of 15, not a load test):** startup including SHA-256 check and
  load 2.2 s; server memory about 228 MB after startup and 215 MB after the calls; a recommendation
  request 29-36 ms for every strategy and user type (single worst call 90 ms); an empty single-method
  reply about 6 ms; the dashboard 131 ms; analytics 6-28 ms.
- **Not done / limits:** no rate limiting, no HTTPS, no token revocation (still local only); CORS is a
  browser rule, not protection against other clients; one registered account sees only itself, but
  analytics show app totals to every logged-in user, which with very few users can be near-identifying;
  `acted` is not stored per action type; no test of many simultaneous users; recommendation quality is
  not shown by any of this. Starlette's `httpx2` warning remains (not installed, unapproved).
- **Unchanged:** recommender code, configuration hash, both artifacts, Step 16 results, seed data,
  split, protocol. The test period was not read. `serving verify` rewrote its report
  `step17_checks.json` (outside the artifact folders); both manifests still verify.

## D-040 (2026-11-12): Gate 4 approved
The owner accepted Steps 23-24 as built, with the recorded limitations (D-037, D-039: local only, no
rate limiting or HTTPS, no quality metric for the serving artifact). The backend, recommender,
evaluation results and artifacts are not to change.

## D-041 (2026-11-12): Phase 5, chunk 5A (Steps 25-27): frontend scaffold, accounts, catalogue
Owner decisions (approved in the chunk 5A message):
- React, TypeScript, Vite and plain CSS (this closes the open "React vs a simpler frontend" decision).
  Phase 5 is split: 5A = Steps 25-27, 5B = Steps 28-30. Until the dashboard exists (5B), people land on
  the catalogue instead of "the dashboard" named in Step 26.
- The 60-minute bearer token is kept in `sessionStorage` (token and expiry time only). Passwords are
  never stored in the browser. Known limit: any script running on the page could read the token (XSS).
  Mitigations: no `dangerouslySetInnerHTML` (an ESLint rule forbids it), no third-party scripts, fonts or
  analytics.
- Dependency set approved with `npm install --no-audit`; `npm audit` is not to be run without separate
  approval.
- The 19 MovieLens genres are a frontend constant (no genres endpoint). The catalogue list API is
  unchanged (list items carry no per-user state, so controls live on the detail page).
- Direct calls to the API (no Vite proxy) with exactly one CORS origin, `http://localhost:5173`, and Vite
  `strictPort`. Only `VITE_API_URL` is exposed to the browser; no secret may ever use a `VITE_` name.
- The browser walkthrough runs on the throwaway test database only; the development database is not used.
- A detail-page view may be recorded as "viewed" but must not count as an acted recommendation; acted
  events stay limited to the explicit actions in D-039. Recommendation click-through is for later.
- The API stays local. Before any public exposure: HTTPS, login throttling and the account-deletion risk
  (the API does not ask for the password again) must be addressed.

Built and checked (see BUILD_LOG, "Phase 5A"):
- Packages installed (exact versions, lockfile `package-lock.json` saved in `frontend/`): react 19.3.1, react-dom 19.3.1,
  react-router 7.18.5; dev: vite 8.3.8, @vitejs/plugin-react 6.3.0, typescript 6.0.3, vitest 5.1.0,
  jsdom 29.1.1, @testing-library/react 16.3.3, jest-dom 7.0.1, user-event 14.6.10, eslint 10.14.0,
  typescript-eslint 8.72.2, prettier 3.10.0. Six small companion packages were also installed that the
  proposal did not list by name and that need the owner's acknowledgement: @types/react,
  @types/react-dom, @types/node (type definitions), @eslint/js and globals (lint presets) and
  eslint-plugin-react-hooks (React lint rules). Installed with `--ignore-scripts` as well. 238 packages,
  `node_modules` 176 MB.
- **Open point for the owner:** the backend's `POST /movies/{id}/view` also records an acted event
  (D-039). Because a detail-page view must not count as acted, the 5A frontend does NOT call it, so no
  "viewed" row is written. Options: (a) leave it (recommended for now); (b) approve a one-line backend
  change so `view` records `viewed` without an acted event, with its test updated.
- Unchanged: backend, recommender, artifacts, evaluation results, seed data, split, protocol.

## D-042 (2026-11-12): a view records `viewed` only, never an `acted` event (corrects D-039)
Owner decision. Opening a movie detail page records a `viewed` interaction (one row per user and movie;
a repeat refreshes its time) and does not write a recommendation `acted` event. `acted` is limited to
adding or changing a rating, like, dislike, watchlist or watched on a movie that was served. This
supersedes the part of D-039 that listed "view" among acting events and resolves the open point in
D-041. Change: `POST /movies/{id}/view` no longer calls `record_acted` (the only API behaviour change);
the frontend detail page now calls it once per visit for a logged-in person (best effort; a failure
does not break the page). No schema, recommender, evaluation or artifact change. Also fixed: the
catalogue filter boxes now re-fill from the URL on Back, Forward, refresh and shared links.
