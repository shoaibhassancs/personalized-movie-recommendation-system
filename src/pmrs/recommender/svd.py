"""Step 9 matrix-factorisation model: TruncatedSVD with fold-in.

Each user's ratings are centred on their own mean and the sparse users x items matrix is
decomposed with scikit-learn's ``TruncatedSVD`` into ``factors`` item directions.

Honest limits, stated plainly:

* scikit-learn has no ALS or FunkSVD. TruncatedSVD treats every unrated cell as "the
  user's average" (a centred zero), unlike ALS/FunkSVD which fit only the observed
  ratings. It is a simpler stand-in, not the usual recommender factorisation.
* Fold-in is a projection, not a refit: a new user's centred ratings are projected onto
  the item directions to get their factors, then mapped back to a score per movie.

Ranking uses the unclipped predicted deviation so scores do not tie at the limits.
``predict_ratings`` gives the same prediction clipped to 0.5-5, as a rating.
"""

from typing import Self

import numpy as np
from sklearn.decomposition import TruncatedSVD

from pmrs.recommender.base import (
    MAX_RATING,
    MIN_RATING,
    FitData,
    FloatArray,
    History,
    Scorer,
    center_by_user,
)

DEFAULT_FACTORS = 50  # provisional; tuned on validation only (Step 15)
DEFAULT_SEED = 42


class SVDScorer(Scorer):
    name = "svd"

    def __init__(
        self, factors: int = DEFAULT_FACTORS, seed: int = DEFAULT_SEED
    ) -> None:
        if factors < 1:
            raise ValueError("factors must be >= 1")
        self.factors = factors
        self.seed = seed

    def fit(self, data: FitData) -> Self:
        self.item_map = data.item_map
        centred, _ = center_by_user(data.matrix)
        usable = max(1, min(self.factors, min(centred.shape) - 1))
        model = TruncatedSVD(n_components=usable, random_state=self.seed)
        model.fit(centred)
        self.item_factors: FloatArray = np.asarray(model.components_.T)  # items x k
        self.global_mean = (
            float(data.matrix.data.mean()) if data.matrix.nnz > 0 else 0.0
        )
        return self

    def _deviation(self, history: History) -> FloatArray:
        n_items = self.item_factors.shape[0]
        if len(history) == 0:
            return np.zeros(n_items)
        centred = history.ratings - history.ratings.mean()
        user_factors = centred @ self.item_factors[history.items]  # fold-in
        return np.asarray(self.item_factors @ user_factors, dtype=np.float64)

    def score(self, history: History) -> FloatArray:
        return self._deviation(history)

    def predict_ratings(self, history: History) -> FloatArray:
        """Predicted rating per movie, clipped to the 0.5-5 scale."""
        base = history.ratings.mean() if len(history) else self.global_mean
        return np.clip(base + self._deviation(history), MIN_RATING, MAX_RATING)
