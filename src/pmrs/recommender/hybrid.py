"""Step 10 hybrid scoring and the cold-start ladder.

The ladder picks a branch from how many ratings the user has *right now*:

* 0 ratings: ``no_ratings``. With favourite genres supplied, movies are ranked by a
  weighted mix of "matches the chosen genres" and popularity. With no genres supplied,
  the ranking is pure popularity.
* 1 to 9 ratings: ``few_ratings``. A blend that leans on the content model, because
  neighbours and latent factors need more history to be reliable.
* 10 or more: ``many_ratings``. A more balanced blend.

Blending: each method's scores are min-max scaled to 0..1 *per user, over that user's
candidate movies only* (the movies they have not already rated). A movie a method has no
evidence for (``-inf``/NaN) scales to 0 for that method. The blended score is the
weighted sum of the scaled scores.

Every number here is a provisional default (owner: reviewable in Phase 3; tuning on
validation data only, Step 15). Nothing has been tuned and none of it is evidence of
quality.
"""

from collections.abc import Collection
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from pmrs.recommender.base import FloatArray, IntArray

Branch = Literal["no_ratings", "few_ratings", "many_ratings"]
COMPONENTS = ("content", "item_knn", "svd", "popularity")  # also the tie-break order

FEW_MAX = 9  # 1..9 ratings is "few"; 10 and up is "many"


def _few_weights() -> dict[str, float]:
    return {"content": 0.60, "item_knn": 0.15, "svd": 0.15, "popularity": 0.10}


def _many_weights() -> dict[str, float]:
    return {"content": 0.35, "item_knn": 0.25, "svd": 0.25, "popularity": 0.15}


@dataclass(frozen=True)
class HybridConfig:
    """Provisional ladder settings. Change them here; nothing is tuned yet."""

    few_max: int = FEW_MAX
    # no-ratings branch with genres:
    #   score = genre_weight * genre match + popularity_weight * popularity
    genre_weight: float = 0.6
    popularity_weight: float = 0.4
    few_weights: dict[str, float] = field(default_factory=_few_weights)
    many_weights: dict[str, float] = field(default_factory=_many_weights)

    def __post_init__(self) -> None:
        if self.few_max < 1:
            raise ValueError("few_max must be at least 1")
        if self.genre_weight < 0 or self.popularity_weight < 0:
            raise ValueError("weights must not be negative")
        if abs(self.genre_weight + self.popularity_weight - 1.0) > 1e-9:
            raise ValueError("genre_weight + popularity_weight must equal 1")
        for name, weights in (("few", self.few_weights), ("many", self.many_weights)):
            unknown = set(weights) - set(COMPONENTS)
            if unknown:
                raise ValueError(f"{name}_weights: unknown methods {sorted(unknown)}")
            if any(w < 0 for w in weights.values()):
                raise ValueError(f"{name}_weights must not be negative")
            if abs(sum(weights.values()) - 1.0) > 1e-9:
                raise ValueError(f"{name}_weights must sum to 1")

    def branch(self, n_ratings: int) -> Branch:
        """Which rung of the ladder a user with ``n_ratings`` ratings is on."""
        if n_ratings < 0:
            raise ValueError("n_ratings must not be negative")
        if n_ratings == 0:
            return "no_ratings"
        return "few_ratings" if n_ratings <= self.few_max else "many_ratings"

    def weights_for(self, branch: Branch) -> dict[str, float]:
        if branch == "few_ratings":
            return dict(self.few_weights)
        if branch == "many_ratings":
            return dict(self.many_weights)
        raise ValueError("the no_ratings branch does not blend methods")


def min_max_scale(scores: FloatArray, candidates: IntArray) -> FloatArray:
    """Scale ``scores`` to 0..1 using only the candidate positions.

    Non-candidates and candidates without evidence (``-inf``/NaN) get 0. If every
    scored candidate has the same score there is nothing to separate, so they all get 0.
    """
    out = np.zeros(scores.size)
    if candidates.size == 0:
        return out
    values = scores[candidates]
    finite = np.isfinite(values)
    if not finite.any():
        return out
    low, high = float(values[finite].min()), float(values[finite].max())
    if high > low:
        out[candidates[finite]] = (values[finite] - low) / (high - low)
    return out


def blend(
    component_scores: dict[str, FloatArray],
    weights: dict[str, float],
    candidates: IntArray,
) -> tuple[FloatArray, dict[str, FloatArray]]:
    """Weighted sum of the per-user min-max scaled scores.

    Returns the blended score (0..1 when the weights sum to 1) and each method's scaled
    scores (kept so explanations can say which method contributed most).
    """
    scaled = {
        name: min_max_scale(component_scores[name], candidates)
        for name in COMPONENTS
        if weights.get(name, 0.0) > 0.0
    }
    n_items = next(iter(component_scores.values())).size
    total = np.zeros(n_items)
    for name, values in scaled.items():
        total += weights[name] * values
    return total, scaled


def genre_match(
    item_genres: list[frozenset[str]], chosen: Collection[str]
) -> FloatArray:
    """Share of the chosen genres each movie has (0..1). Names are lower-case."""
    wanted = frozenset(chosen)
    if not wanted:
        return np.zeros(len(item_genres))
    return np.array([len(wanted & genres) / len(wanted) for genres in item_genres])
