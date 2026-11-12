"""Step 13 metrics: ranking, rating error, coverage, diversity and bootstrap intervals.

Pure numpy; no web dependencies and no model code. Every function is unit-tested
against hand-computed values. These are offline metrics for comparing methods under the
project's per-user holdout protocol. They are not benchmark scores and do not predict
how real viewers would react.
"""

from pmrs.metrics.intervals import (
    bootstrap_ci,
    bootstrap_ratio_ci,
    paired_bootstrap_difference,
)
from pmrs.metrics.lists import catalogue_coverage, genre_diversity
from pmrs.metrics.ranking import (
    average_precision_at_k,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)
from pmrs.metrics.rating import mae, rmse

__all__ = [
    "average_precision_at_k",
    "bootstrap_ci",
    "bootstrap_ratio_ci",
    "catalogue_coverage",
    "genre_diversity",
    "mae",
    "ndcg_at_k",
    "paired_bootstrap_difference",
    "precision_at_k",
    "recall_at_k",
    "rmse",
]
