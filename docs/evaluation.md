# Evaluation report (Step 16)

**Claim limit.** These results compare methods under the same per-user holdout protocol
(D-021). They do not show that any method is leakage-safe, and they are not a prediction of
future behaviour. Models are fitted once, so they still see other users' ratings and tags dated
after a scored user's own cutoff (Step 5 measured this: for warm users the median share of the
fit dated at or after the user's own cutoff is 48.9% for the test fit; the median share of
usable tags dated after the cutoff is 50.2%). Intervals cover sampling noise between users only.

## What was run
- One read of the test period, after refitting on train + validation (eligible users; the 20%
  cold-start users stay out of every fit), using the frozen configuration: file
  `data/processed/tuning/proposed_frozen_config.json`, hash
  `e68a7ee613e27719e7369f592ce438cd8fb7b4ff5887a55af4ce39d5eecce2b5` (D-031). The hash covers the
  settings fields, not the status text.
- Command: `uv run python -m pmrs.evaluation.final --target test --read-test-once`. Results:
  `data/processed/final/test/` (git-ignored; `report.txt`, `summary.csv`, `comparisons.csv`,
  `per_user.csv`, `coverage.csv`, `rating_errors.csv`, `run.json`, `final_run.json`,
  `frozen_config.json`, five charts in `charts/`).
- Relevant = rated 4.0 or higher. Headline metric NDCG@10 (chosen in advance). 95% percentile
  bootstrap over users, 2,000 resamples, seed 42. Users: 453 warm; 113 cold-start simulation.
- Settings were tuned on validation only (D-029, D-030). Some were chosen after viewing the
  validation results, so validation numbers are optimistic. The test period was not used to
  change anything.

## Headline: warm users (453), NDCG@10 [95% interval]
| method | NDCG@10 | precision@10 | recall@10 | MAP@10 | coverage@10 |
|---|---|---|---|---|---|
| random | 0.002 [0.001, 0.005] | 0.002 | 0.002 | 0.001 | 0.368 |
| popularity | 0.047 [0.036, 0.058] | 0.029 | 0.046 | 0.024 | 0.011 |
| Bayesian average | 0.032 [0.023, 0.041] | 0.022 | 0.031 | 0.015 | 0.006 |
| content | 0.007 [0.003, 0.011] | 0.004 | 0.009 | 0.003 | 0.082 |
| item-kNN | 0.021 [0.014, 0.030] | 0.012 | 0.020 | 0.011 | 0.087 |
| SVD | 0.055 [0.044, 0.067] | 0.033 | 0.059 | 0.027 | 0.060 |
| **hybrid** | **0.064 [0.052, 0.077]** | 0.038 | 0.064 | 0.033 | 0.064 |

Paired NDCG@10 differences (hybrid minus reference, same users):
- vs popularity +0.017 [+0.006, +0.029]
- vs SVD +0.009 [+0.001, +0.017]
- vs Bayesian average +0.032 [+0.019, +0.046]
- vs item-kNN +0.043 [+0.029, +0.056]
- vs content +0.057 [+0.045, +0.069]
- SVD vs popularity +0.008 [-0.003, +0.021] (spans zero)

In plain words: for warm users the hybrid had the highest mean NDCG@10, and its lead over
popularity and over SVD held in these resamples, but the lead over SVD is small (its interval
barely clears zero) and the lead over popularity is about 0.017 in a score of 0.047. Warm-user
validation NDCG@10 was 0.080; the test value 0.064 is lower, as expected after tuning on
validation. The hybrid's lists are far more varied than popularity's by coverage (0.064 vs 0.011)
but its genre diversity is lower (0.711 vs 0.785). Content-based alone was weak (0.007), and
item-kNN with minimum support 20 was below popularity (-0.025 [-0.038, -0.012]).
These are small absolute scores; most users' top 10 contain no relevant movie.

## Cold-start SIMULATION (113 users), NDCG@10
| revealed ratings | popularity = hybrid | Bayesian average | SVD | random |
|---|---|---|---|---|
| 0 | 0.031 [0.018, 0.047] | 0.035 [0.017, 0.058] | 0.012 | 0.001 |
| 3 | 0.032 [0.018, 0.048] | 0.036 [0.017, 0.059] | 0.023 | 0.001 |
| 5 | 0.032 [0.018, 0.049] | 0.037 [0.018, 0.061] | 0.027 | 0.000 |
| 10 | 0.035 [0.021, 0.052] | 0.037 [0.018, 0.061] | 0.023 | 0.003 |

**The "hybrid" in these rows is the popularity fallback** (D-030): its lists are identical to
popularity's, so the paired difference is exactly 0.000 and there is no hybrid success to
report. The hybrid did not beat any baseline here, and Bayesian average scored slightly higher
than popularity at every size (-0.004 to -0.002 hybrid minus Bayesian, intervals span zero, so no
difference is established). Hybrid minus SVD at 0/3/5/10 revealed: +0.019, +0.009, +0.006,
+0.012, all spanning zero. This is a simulation, not evidence about real new users. The
configuration was never evaluated at exactly 11 ratings.

## Rating error (secondary, warm users)
SVD RMSE 0.950 [0.912, 0.989], MAE 0.739; user mean 0.962 / 0.751; Bayesian average 0.990 /
0.779; global mean 1.052 / 0.838. SVD's advantage over the per-user mean is small.

## What this can and cannot establish
- Can: under this per-user holdout, on this dataset, the hybrid scored higher than each single
  method for warm users on average, with sampling uncertainty between users shown.
- Cannot: leakage-safe or future prediction; real new-user behaviour; results on other data or
  online; that the small gap to SVD would persist. Many comparisons were made, so some intervals
  excluding zero may be chance. Held-out movies stay in the candidate set (Step 5 rules).
- Charts (Plotly HTML in `charts/`): warm NDCG@10; cold-start NDCG by revealed ratings; paired
  difference vs popularity; metrics across K; coverage vs NDCG.
- Item-kNN (minimum support 20) stayed below popularity on both validation and test.

MovieLens data: GroupLens, non-commercial use; cite Harper and Konstan (2015).
