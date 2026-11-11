# Scope

Draft 1 · Nov 12, 2026 · Quick reference derived from `project-notes/PROJECT_GUIDE.md`.

## Objective
A web app that gives each user ranked, explained movie recommendations from three real
algorithms (content-based, collaborative, hybrid), fitted on MovieLens ratings and evaluated
with standard ranking metrics against baselines.

## Intended users
Hiring reviewers and engineers evaluating an AI/ML portfolio; demo users who register and rate
movies; the owner as a learner.

## In scope (Version 1)
- Register, log in, edit profile, choose favourite genres
- Movie catalogue from MovieLens `ml-latest-small`, with search, genre/year/rating filters, and
  a detail page (generated placeholder posters)
- Rate, like/dislike, watchlist, mark watched, view history
- Baselines (random, popularity), content-based, collaborative (item-based and SVD), and hybrid
  recommenders, with ranking, removal of already-seen movies, and a cold-start fallback
- A short explanation with each recommendation
- User dashboard (recommended, trending, popular, recently added by release year, favourite
  genres, watchlist, recent activity) and a system analytics page (counts, popular movies and
  genres, rating distribution, recommendation engagement from real in-app events)
- EDA, leakage-safe offline evaluation (Precision/Recall/NDCG/MAP@K, RMSE/MAE, coverage,
  diversity) with confidence intervals and a results report; MLflow for evaluation runs
- PostgreSQL, FastAPI, React, Docker Compose, CI, one cloud deployment, README, model card

## Out of scope (Version 1)
- TMDB posters/descriptions (API terms conflict with ML use; optional later, display only)
- AWS-specific infrastructure; password reset, email verification, OAuth, admin roles
- Live or scheduled model retraining; deep-learning or implicit-feedback (ALS) models
- A/B testing infrastructure; social features; mobile app
- Datasets other than `ml-latest-small` (`ml-1m` cannot be redistributed)
- Real personal data; any claim of real-world engagement gains or benchmark-level results

## Key boundaries
- Non-commercial demo only (MovieLens terms); citation and attribution shown.
- Data is not committed to git; secrets are never committed.
- Models are fitted offline; a user's new ratings affect their own results immediately but
  do not retrain the models.
- Offline metrics compare methods inside this project; they are not benchmark results.

## Done for Version 1
All items above working end to end, tests and CI passing, a documented evaluation, a one-command
local run, and a live non-commercial demo with README and model card.
