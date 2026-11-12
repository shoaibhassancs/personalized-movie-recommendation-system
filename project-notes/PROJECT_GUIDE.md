# Personalized Movie Recommendation System (PMRS): Project Guide

Draft 1 · Nov 12, 2026 · Solo portfolio project #3 (target: entry-level AI/ML engineer roles)

This guide says what the project is and why. How it gets built is in `BUILD_PLAN.md`; the short
boundary list is in `SCOPE.md`.

## 1. Summary

PMRS is a web app where a person registers, picks favourite genres, browses and searches a movie
catalogue, rates and saves movies, and gets personalised recommendations from three real
algorithms (content-based, collaborative, hybrid). Every recommendation carries a short reason,
and the person can switch between the three methods to compare them. A dashboard shows their own
activity; an analytics page shows system-level numbers. The models are fitted on the public
MovieLens ratings data and judged with standard ranking metrics against simple baselines.

## 2. Problem and why it matters

People facing thousands of titles cannot choose well from a catalogue. Recommenders solve this,
but a good one has to handle three hard cases: users with a lot of history, users with almost
none (the "cold start" problem), and the need to say *why* something was suggested. A recommender
is also easy to fake (hardcoded lists, popularity dressed up as personalisation), so the credible
part of this project is **measured** evidence that each method beats simple baselines.

## 3. Proposed solution and main flow

1. A new user registers and picks favourite genres. This is their only signal at first.
2. They browse, search, and filter by genre, release year and rating, and open movie pages.
3. They rate (0.5–5 stars), like/dislike, add to a watchlist, or mark movies watched. Each action
   is stored as an interaction.
4. On request, the backend asks the recommendation engine for a ranked list for that user, using
   the chosen method. Movies the user already rated or watched are removed. Each result has a
   reason built from the data that produced it.
5. The dashboard and analytics pages summarise activity from the database.

The recommenders are fitted **offline** on MovieLens and saved as files. A new user's own ratings
affect their results immediately, because their profile is computed at request time from the
stored similarity data. The models are **not** retrained live (see out of scope).

## 4. Role of AI/ML (and what the project will not claim)

| Method | Idea | Main weakness (shown honestly in the results) |
| --- | --- | --- |
| Baselines (random, popularity) | Reference points | Not personal |
| Content-based | Match movie attributes (genres, user tags, title words, decade) to a profile built from what the user rated highly | Narrow; "more of the same" |
| Collaborative (item-based nearest neighbours, plus matrix factorisation with scikit-learn's TruncatedSVD) | Use rating patterns of many users | Needs history; weak for new users and rarely-rated movies |
| Hybrid | Weighted blend; the weight shifts toward content when the user has few ratings | Weights need tuning on data |

ML is appropriate here because personalisation from thousands of sparse ratings is a learned-
similarity problem, not a rule-writing problem.

The project **will** claim: the methods are implemented, fitted on real data, and compared with
named metrics under a per-user temporal holdout, with uncertainty shown (not a globally
leakage-safe or future-predicting evaluation).
The project **will not** claim: improved real-world engagement, production-scale performance, or
results comparable to published benchmarks. The dataset is small (see Section 8), the evaluation
is offline, and "engagement statistics" in the app only reflect whatever people do in this app.

## 5. Audience and portfolio value

Audience: hiring managers and engineers reviewing an entry-level AI/ML portfolio, plus the owner
as a learner. Skills the project can show:

- **ML:** data cleaning, EDA, sparse interaction matrices, temporal per-user holdout with documented leakage limits, three model
  families, ranking metrics, cold start, hyperparameter tuning on validation only, experiment
  tracking.
- **Engineering:** a typed FastAPI backend with authentication, a PostgreSQL schema and seed
  pipeline, one shared recommender implementation, tests, Docker, CI, and a deployed demo.
- **Product thinking:** explanations, a fallback for new users, a React interface that exposes
  the methods side by side.

## 6. Scope (see `SCOPE.md` for the compact list)

**Included in Version 1:** everything in your sections A–G, in lean form: accounts and profiles;
catalogue, search, filters, detail page; rate/like/dislike/watchlist/watched/history; three
recommenders plus baselines; explanations; user dashboard; analytics page; offline evaluation
with a results report; Docker Compose; CI; one cloud deployment; README and model card.

**Size verdict.** As written, the specification is too large for one solo project at full depth:
React app, auth, three recommenders, evaluation, MLflow, Postgres, Docker, AWS, and TMDB. After the trims below it is
well-sized for a flagship third project, roughly 10–14 weeks at 15–20 hours a week (an estimate,
not a commitment). The ML core and its evaluation are the part to protect; the web layer should
stay thin.

**Recommended trims and changes from the original specification**

| Item | Recommendation | Reason |
| --- | --- | --- |
| TMDB posters and descriptions | **Leave out of V1.** Use generated placeholder posters. Optional V2, display only. | TMDB's API terms (checked Nov 12, 2026) forbid using TMDB content "in connection with, including for training, a machine learning (ML) or artificial intelligence (AI) based Application", limit caching to 6 months, require attribution, and exclude commercial use. This whole app is an ML application, so the clause may apply even to display. I cannot give a legal ruling; you should read it and decide. MovieLens itself has no descriptions or posters. |
| "Description-based" content model | Use genres + MovieLens user tags + title words + decade instead | Without TMDB there are no descriptions. This is honest and still a real content model. |
| AWS | Deploy to one simple platform (decided later); AWS-specific setup is V2 | AWS adds cost and setup (IAM, networking, RDS) without adding ML evidence. |
| MLflow | Keep, minimal: local file store, only for evaluation and tuning runs | Cheap, and the specification asks for it. Disk impact to be checked. |
| Plotly | Use in the EDA and evaluation reports. Use a lighter chart library inside the React app. | Plotly's browser bundle is very large. |
| Large datasets | Use `ml-latest-small` only (about 100k ratings) | Fits an 8 GB laptop and may be redistributed; see Section 8. |
| "Real-time" behaviour | New ratings change that user's results immediately; models are not retrained live | Live retraining adds job infrastructure with little extra evidence. |
| "Recently added" | Defined as newest release years, because MovieLens has no "date added" | A fact about the data, not a design choice. |

**Out of scope (V1):** TMDB integration; AWS-specific infrastructure; password reset, email
verification, OAuth, admin roles; live or scheduled retraining; deep-learning or implicit-
feedback models; A/B testing infrastructure; social features; mobile app; multilingual content;
real user data; performance claims beyond what is measured.

## 7. Evaluation approach

- **Split (owner-approved, D-021):** a **per-user temporal holdout**. For each user the latest
  ceil(10%) of ratings are test and the preceding ceil(10%) are validation; the rest are train.
  Equal timestamps stay together and a boundary tie goes to the later period. A shared global
  chronological split was measured first and was infeasible (D-020: 13 to 30 evaluable users per
  period against a proposed 100).
- **Information rule:** validation scoring uses models fitted on train ratings only; validation is
  for tuning only; for the final test the models are refit on train + validation, and test is read
  once. A tag may be used only if it is earlier than its own author's cutoff. The final serving
  artifacts use all data, since no evaluation follows.
- **Claim limit and remaining leakage (plain statement):** users have different cutoff dates, but
  a model is fitted once for everyone. So a model scoring one user's held-out items has been fitted
  on other users' ratings and tags dated *after* that user's cutoff (about half of the fit data on
  average; measured shares are in BUILD_LOG Step 5). Results therefore support only
  "methods compared under the same per-user holdout protocol". They do **not** show that the system
  is globally leakage-safe or that it predicts future behaviour.
- **Eligibility:** a user is scored only if at least 10 ratings remain in train and neither held-out
  period exceeds 30% of their ratings (their eligible train ratings still enter the fit), and only
  in a period holding at least one relevant item.
- **Relevant item:** a held-out movie rated >= 4.0 (owner-confirmed).
- **Candidate set:** for each warm evaluated user, every catalogue movie except those the user
  rated before the applicable cutoff. For a cold-start simulation user, every catalogue movie
  except the ratings actually revealed for that history size (0, 3, 5 or 10): their hidden train,
  validation and test ratings are unknown to the simulated new user and never filter candidates.
  Held-out movies from the evaluated period stay eligible in both cases, so relevant held-out
  items must be ranked against all other unknown movies (for cold-start users this includes their
  own hidden train items, which is stricter on the models).
- **Cold-start simulation (labelled as a simulation):** a fixed-seed 20% of users is kept out of
  every fit. They are scored with 0, 3, 5 or 10 of their earliest ratings revealed. The zero-history
  case measures the popularity fallback. This is not real new-user evidence, and MovieLens cannot
  measure the favourite-genre onboarding path.
- **Ranking metrics:** Precision@K, Recall@K, NDCG@K, MAP@K at K = 5, 10, 20, over that
  candidate ranking.
- **Rating metrics:** RMSE and MAE for the rating-predicting models (reported as secondary
  because ranking is the product goal).
- **Beyond accuracy:** catalogue coverage and list diversity (genre dissimilarity).
- **Comparison:** against random and popularity baselines; hybrid weights chosen on the
  validation set only; the test set is read once at the end; uncertainty shown with bootstrap
  confidence intervals over users; a separate, labelled cold-start *simulation* (0, 3, 5, 10
  revealed ratings, on users kept out of every fit).
- **Caveat that goes in the report:** MovieLens documents `ml-latest-small` as a development
  dataset not intended for shared research results. Our numbers are for comparing methods
  inside this project, not for leaderboards.

## 8. Data, licensing, privacy, safety

- **MovieLens `ml-latest-small`:** 100,836 ratings, 3,683 tag applications, 9,742 movies,
  610 users, 1996–2018, no demographics. Source: GroupLens README (read Nov 12, 2026). Terms
  summarised from it: research use; no implied endorsement; citation required; redistribution
  allowed *under the same terms*; **no commercial or revenue-bearing use without permission**.
  The larger `ml-1m` forbids redistribution without permission, so it is not bundled anywhere.
  Consequence: the public demo must be non-commercial and carry the citation and attribution.
  This is not legal advice.
- **Data and secrets in git:** the project-specific `.gitignore` is created in Build Plan
  Step 1, before any data is downloaded or artifact generated. It excludes the downloaded
  dataset (`data/`), `.env` files, model artifacts, MLflow data, caches and build/dependency
  folders. A script downloads the data into `data/raw/` (Step 2).
- **Seed users:** the 610 MovieLens users become "historical" accounts that cannot log in. They
  exist so collaborative filtering has neighbours. Real registered users get separate IDs.
- **Privacy:** only an email (or username) and a password hash are stored for registered users;
  passwords are hashed (never stored plain); secrets live in environment variables and are never
  committed. No real personal data is needed for the demo.
- **Honest limits to display in the app and docs:** data stops in 2018; 610 users; user tags are
  sparse; recommendations reflect that data, including its popularity bias.

## 9. How it will be built (high level)

`src/` layout Python package with the recommender code (no web dependency) → offline evaluation
harness → PostgreSQL schema and seed script → FastAPI service that imports the same recommender
code → React single-page app → Docker Compose for one-command local run → CI → one cloud
deployment → README and model card. ML work comes **before** the web layer so that the hardest,
most valuable part is proven first. The detailed order is in `BUILD_PLAN.md`.

## 10. Machine and tooling facts (inspected Nov 12, 2026)

macOS (Darwin 24.2.0), Apple M1, 8 cores, 8 GB RAM, **12 GiB free of 228 GiB (94% used)**.
Installed: Python 3.13.5 (system default) and 3.12.16 (used by the project), Node 22.16.0 / npm 10.9.2, uv 0.13.6, git 2.39.5, Docker CLI 29.9.2
(daemon status not checked), psql client 17.11 (no server verified). The data is tiny and fits
in memory; **disk space is the real constraint** for Docker images, MLflow, and `node_modules`.

## 11. Assumptions, open questions, risks

**Assumptions (not yet confirmed by you)**

1. The project folder is the current one (`.../personalized-movie-recommendation-system`).
2. **Decided (owner, D-011):** Python 3.12 via uv. Library compatibility on 3.12 is still to be
   verified when dependencies are added.
3. The analytics page is visible to any logged-in user and shows only aggregates.
4. Registration uses email + password, with a simple JWT login.
5. Tooling follows your earlier projects: uv, ruff, pytest, mypy, `DECISIONS.md`.

**Open decisions.** The recommendations in this guide (TMDB out of V1, thin React,
no `ml-1m` in V1, the 80/90 percentile cutoffs, and so on) are **provisional defaults, not final
approvals**. Each is decided by the owner at the build step or gate where it first matters, and
recorded in `DECISIONS.md` when decided:

| Decision | Decided at |
| --- | --- |
| Evaluation protocol: per-user holdout, minimums, cold-start simulation | **Decided at Step 5 (D-021, owner-approved)**; Gate 1 pending |
| MLflow full vs lightweight install | Step 15, after a disk check |
| TMDB (stay out of V1, or display-only use after reading its terms) | Before Step 21 (catalogue work that depends on external content) |
| React vs a simpler frontend | Before Step 25 (frontend work) |
| Deployment platform | Step 33 |
| Local `ml-1m` benchmark | Deferred until V1 is assessed (Gate 6); currently V2 |

**Already decided (not open):** Python 3.12 (D-011); `project-notes/` is git-ignored and
`DECISIONS.md` sits at the repo root (D-012). See `DECISIONS.md` D-014 for the current list.
Until a decision is made, the default is what the documents say. Changing a default that alters
scope, versions or deliverables follows the plan's change process (propose, approve, then edit).

**Risks**

| Risk | Mitigation |
| --- | --- |
| Scope creep from the web layer | Fixed page list; ML phases finish and pass a gate first |
| Small data gives noisy metrics | Bootstrap intervals; claims limited to relative comparison |
| Ratings too clustered in time for a shared chronological split | **Occurred** (D-020); owner-approved per-user holdout with a narrowed claim (D-021) |
| Collaborative model beats hybrid, or hybrid adds little | Report as found; hybrid weights tuned on validation only |
| Disk almost full | Check space before Docker, MLflow, `node_modules`; prune as needed |
| TMDB / MovieLens terms misread | Primary sources linked in `DECISIONS.md`; owner decides; non-commercial demo |
| Engagement statistics look empty or fake | Compute only from real in-app events; show the empty state honestly |
| scikit-learn has no ALS or classic FunkSVD | Use item-kNN and TruncatedSVD, and say so |
