"""Step 8 item-based collaborative filtering (item-item k-nearest neighbours).

Similarity is the cosine between two movies' columns after each user's ratings are
centred on that user's own mean (so a "4" from a harsh rater counts for more than a "4"
from a generous one). It is shrunk toward zero when few users rated both movies:
``sim * n / (n + shrinkage)`` with ``n`` the number of shared raters. Only the
``neighbours`` most similar movies with positive similarity are kept for each movie.

The full 9,742 x 9,742 similarity matrix is never held. Similarities are computed for a
block of movies at a time and reduced to the top neighbours immediately, so peak memory
is one block, not the square.

Scoring happens at request time from the user's own history, with no refit: for a movie
``i`` the score is ``sum(sim(i,j) * (r_j - mean_u)) / sum(sim(i,j))`` over the user's
rated movies ``j`` that are among ``i``'s neighbours. A movie with no such neighbour has
no evidence and scores ``-inf``.

Minimum support (Step 15, D-029): with ``min_support = m`` a movie rated by fewer than
``m`` fit users scores ``-inf`` too, so it is ranked below every movie that has enough
raters. This changes scores only. It is not a candidate filter: such movies stay in the
Step 5 candidate set and are simply listed last. ``m = 0`` is the original behaviour.
"""

from typing import Self

import numpy as np
import numpy.typing as npt
from scipy import sparse

from pmrs.recommender.base import FitData, FloatArray, History, Scorer, center_by_user
from pmrs.recommender.explain import Evidence

DEFAULT_NEIGHBOURS = 50  # provisional; tuned on validation only (Step 15)
DEFAULT_SHRINKAGE = 10.0  # provisional
DEFAULT_MIN_SUPPORT = 0  # 0: no minimum, the Step 8 behaviour
BLOCK_ITEMS = 500


class ItemKNNScorer(Scorer):
    name = "item_knn"

    def __init__(
        self,
        neighbours: int = DEFAULT_NEIGHBOURS,
        shrinkage: float = DEFAULT_SHRINKAGE,
        block_items: int = BLOCK_ITEMS,
        min_support: int = DEFAULT_MIN_SUPPORT,
    ) -> None:
        if neighbours < 1 or block_items < 1 or shrinkage < 0:
            raise ValueError("neighbours and block_items must be >= 1, shrinkage >= 0")
        if min_support < 0:
            raise ValueError("min_support must be >= 0")
        self.neighbours = neighbours
        self.shrinkage = shrinkage
        self.min_support = min_support
        self.block_items = block_items

    def fit(self, data: FitData) -> Self:
        self.item_map = data.item_map
        centred, _ = center_by_user(data.matrix)
        centred_csc = centred.tocsc()
        present = data.matrix.copy()
        present.data = np.ones_like(present.data)
        present_csc = present.tocsc()
        self.support: npt.NDArray[np.int64] = np.diff(present_csc.indptr).astype(
            np.int64
        )  # fit users who rated each movie
        norms = np.sqrt(
            np.asarray(centred.multiply(centred).sum(axis=0), dtype=np.float64).ravel()
        )
        n_items = centred.shape[1]
        rows: list[int] = []
        cols: list[int] = []
        vals: list[float] = []
        for start in range(0, n_items, self.block_items):
            stop = min(start + self.block_items, n_items)
            numerator = (centred_csc[:, start:stop].T @ centred).toarray()
            shared = (present_csc[:, start:stop].T @ present).toarray()
            scale = np.outer(norms[start:stop], norms)
            sim = np.divide(
                numerator, scale, out=np.zeros_like(numerator), where=scale > 0
            )
            sim *= shared / (shared + self.shrinkage)
            sim[np.arange(stop - start), np.arange(start, stop)] = 0.0  # not itself
            keep = min(self.neighbours, n_items)
            top = np.argpartition(-sim, keep - 1, axis=1)[:, :keep]
            for local in range(stop - start):
                chosen = top[local]
                chosen = chosen[sim[local, chosen] > 0]
                rows.extend([start + local] * len(chosen))
                cols.extend(chosen.tolist())
                vals.extend(sim[local, chosen].tolist())
        self.similarity: sparse.csr_matrix = sparse.csr_matrix(
            (vals, (rows, cols)), shape=(n_items, n_items), dtype=np.float64
        )
        return self

    def score(self, history: History) -> FloatArray:
        n_items = self.similarity.shape[0]
        scores = np.full(n_items, -np.inf)
        if len(history) == 0:
            return scores
        deviation = np.zeros(n_items)
        deviation[history.items] = history.ratings - history.ratings.mean()
        rated = np.zeros(n_items)
        rated[history.items] = 1.0
        numerator = np.asarray(self.similarity @ deviation, dtype=np.float64).ravel()
        denominator = np.asarray(self.similarity @ rated, dtype=np.float64).ravel()
        has_evidence = denominator > 0
        scores[has_evidence] = numerator[has_evidence] / denominator[has_evidence]
        scores[self.support < self.min_support] = -np.inf  # too few raters to trust
        return scores

    def evidence(self, history: History, item: int) -> Evidence:
        """The user's rated movies that are neighbours of ``item``, strongest first."""
        start, stop = self.similarity.indptr[item], self.similarity.indptr[item + 1]
        neighbours = self.similarity.indices[start:stop]
        sims = self.similarity.data[start:stop]
        position = {int(i): n for n, i in enumerate(history.items.tolist())}
        rows = [
            (n, float(s))
            for j, s in zip(neighbours.tolist(), sims, strict=True)
            if (n := position.get(j)) is not None
        ]
        if not rows:
            return Evidence("no_evidence")
        mean = float(history.ratings.mean())
        support = [(n, s) for n, s in rows if history.ratings[n] > mean]
        pool = support or rows  # prefer movies the user rated above their own average
        pool.sort(
            key=lambda r: (
                -r[1] * abs(history.ratings[r[0]] - mean),
                int(history.items[r[0]]),
            )
        )
        top = pool[:3]
        return Evidence(
            "neighbours",
            movies=tuple(int(self.item_map.ids[history.items[n]]) for n, _ in top),
            ratings=tuple(float(history.ratings[n]) for n, _ in top),
            value=float(sum(s for _, s in top)),
            count=len(rows),
        )
