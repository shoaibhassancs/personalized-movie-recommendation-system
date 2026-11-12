# Model card - PMRS movie recommender

Status: **final for V1; reviewed by the owner (2026-11-12, D-051).** The model, configuration and
every number below are unchanged from the Gate 3 draft (approved, D-034); only this status, the
intended-use note, the attribution and three accuracy edits (non-commercial portfolio wording, the
serving-artifact wording and "pseudonymous") were edited. Not a product; a portfolio project.

## Intended use
Ranked, explained movie suggestions in a demo web app that runs on one machine (there is no
hosted deployment). Not for decisions about people. Intended for non-commercial portfolio use only
(MovieLens is licensed for non-commercial use); whether public job-seeking use fits the MovieLens
terms remains unresolved. Data: MovieLens `ml-latest-small` from GroupLens (University of Minnesota),
not endorsed by them. Please cite F. Maxwell Harper and Joseph A. Konstan, 2015, "The MovieLens
Datasets: History and Context", ACM TiiS 5(4), 19:1-19:19, <https://doi.org/10.1145/2827872>.

## What the artifacts are
Two local, git-ignored folders in `data/processed/artifacts/`, each with a SHA-256 manifest
(`MANIFEST.sha256`), `metadata.json`, `provenance.json` and a copy of the frozen configuration.

| Artifact | Fitted on | Evaluated? |
|---|---|---|
| `evaluated_step16` | The exact Step 16 fit: train + validation ratings of eligible users, cold-start users left out, tags earlier than their author's test cutoff, test period not in the fit | Yes. The Step 16 test metrics apply to this fit only. |
| `serving_all_data` | ALL MovieLens ratings and tags (610 users, 100,836 ratings, 3,683 tags), including the test-period ratings and the cold-start users | **No.** The Step 16 metrics do NOT apply to it. It uses the frozen configuration but has not been evaluated; the Step 16 metrics do not apply to it. |

The app loads only `serving_all_data`. Frozen configuration (hash `e68a7ee6...ce2b5`, D-031):
item-kNN neighbours 20, shrinkage 5, minimum support 20; SVD 50 factors; content weights all 1.0;
0 ratings: genre/popularity mix (provisional, untuned); 1-10 ratings: popularity; 11 or more:
hybrid (content 0.35, item-kNN 0.25, SVD 0.25, popularity 0.15).

## Evaluation (Step 16, evaluated model only; unchanged; see `docs/evaluation.md`)
Warm users (453), NDCG@10 [95% interval]: hybrid 0.064 [0.052, 0.077], SVD 0.055, popularity
0.047, Bayesian average 0.032, item-kNN 0.021, content 0.007, random 0.002. Hybrid minus popularity
+0.017 [+0.006, +0.029]; minus SVD +0.009 [+0.001, +0.017] (small). Cold-start simulation (113
users): the "hybrid" is the popularity fallback, so there is no hybrid advantage (0.031-0.035).

**What this establishes:** methods compared under the same per-user holdout protocol, with
sampling noise between users. **It does not establish** leakage-safe or future prediction: models
are fitted once and still see other users' later ratings and tags. The cold-start slice is a
simulation, not evidence about real new users.

## Limitations
- Scores are low in absolute terms; most top-10 lists contain no relevant movie.
- Popularity-heavy: popularity coverage is about 1% of the catalogue; the hybrid about 6%.
- **Exactly 11 ratings was not evaluated** (the routing changes from popularity to hybrid there).
- The 0-rating genre mix was not tuned. Choices were made after viewing validation results.
- Explanations describe what the mechanism did; they are not proof of why you would like a movie.
- Small, development-grade dataset (MovieLens `ml-latest-small`), no TMDB or other content.
- Diagnostic only (not quality): fed the same profile, the two artifacts' top-10 lists differed
  for all 40 sampled users (mean overlap 0.60), as expected since the serving fit has more data.

## Data and security
The artifacts contain pseudonymous MovieLens user IDs and rating histories, with no names or
contact details. That is not a claim of no personal data. A `.joblib` file is a pickle: loading it
can run code, so load only artifacts this project built. The manifest catches damage and mix-ups; it
cannot make an untrusted file safe. Artifacts are local, git-ignored and never uploaded.
