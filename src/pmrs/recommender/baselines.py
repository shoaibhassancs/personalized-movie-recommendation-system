"""Step 6 baselines: random, global popularity, Bayesian-weighted average rating.

They are the yardsticks later methods must beat. Popularity is also the planned
fallback for a user with no ratings (Step 10).
"""

from typing import Self

import numpy as np

from pmrs.recommender.base import FitData, FloatArray, History, Scorer
from pmrs.recommender.explain import Evidence

DEFAULT_PRIOR_STRENGTH = 10.0  # provisional; tuned on validation only (Step 15)


class _ItemCounts:
    """Rating count and rating sum per item, from the fit matrix."""

    @staticmethod
    def of(data: FitData) -> tuple[FloatArray, FloatArray]:
        matrix = data.matrix.tocsc()
        counts = np.diff(matrix.indptr).astype(np.float64)
        sums = np.asarray(matrix.sum(axis=0), dtype=np.float64).ravel()
        return counts, sums


class RandomScorer(Scorer):
    """Random order. Reproducible: the draw depends on the seed and the history."""

    name = "random"

    def __init__(self, seed: int = 42) -> None:
        self.seed = seed

    def fit(self, data: FitData) -> Self:
        self.item_map = data.item_map
        return self

    def score(self, history: History) -> FloatArray:
        rng = np.random.default_rng([self.seed, *np.sort(history.items).tolist()])
        return rng.random(len(self.item_map))

    def evidence(self, history: History, item: int) -> Evidence:
        return Evidence("random")


class PopularityScorer(Scorer):
    """Global popularity: the number of fit ratings each movie has."""

    name = "popularity"

    def fit(self, data: FitData) -> Self:
        self.item_map = data.item_map
        self.counts, _ = _ItemCounts.of(data)
        return self

    def score(self, history: History) -> FloatArray:
        return self.counts.copy()

    def evidence(self, history: History, item: int) -> Evidence:
        return Evidence("popularity", count=int(self.counts[item]))


class BayesianAverageScorer(Scorer):
    """Average rating pulled toward the overall mean for movies with few ratings.

    ``(v * R + m * C) / (v + m)`` with ``v`` ratings, mean ``R``, prior strength ``m``
    and overall item-rating mean ``C``. Movies with no fit ratings score ``C``.
    """

    name = "bayesian_average"

    def __init__(self, prior_strength: float = DEFAULT_PRIOR_STRENGTH) -> None:
        if prior_strength < 0:
            raise ValueError("prior_strength must not be negative")
        self.prior_strength = prior_strength

    def fit(self, data: FitData) -> Self:
        self.item_map = data.item_map
        counts, sums = _ItemCounts.of(data)
        self.counts = counts
        total = counts.sum()
        self.global_mean = float(sums.sum() / total) if total > 0 else 0.0
        m = self.prior_strength
        denominator = counts + m
        self.values = np.divide(
            sums + m * self.global_mean,
            denominator,
            out=np.full_like(sums, self.global_mean),
            where=denominator > 0,
        )
        return self

    def score(self, history: History) -> FloatArray:
        return self.values.copy()

    def evidence(self, history: History, item: int) -> Evidence:
        return Evidence(
            "overall_rating",
            value=float(self.values[item]),
            count=int(self.counts[item]),
        )
