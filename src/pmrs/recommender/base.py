"""Shared pieces for every recommender: fit data, history, ranking and the interface.

These are the building blocks every model shares (Steps 6-9). The single public entry
point is the ``Recommender`` class (Step 12), which wraps these models. Nothing here
depends on the web.

Leakage note (kept visible): ``fit_data`` only hands a model what the Step 5 protocol
allows for the chosen target. That removes a scored user's own held-out ratings and
cold-start users from the fit, but a model is still fitted once and so still sees
other users' ratings and tags dated after a scored user's own cutoff. Results therefore
support only "methods compared under the same per-user holdout protocol".
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Self

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import sparse

from pmrs.recommender.explain import Evidence
from pmrs.split import (
    IdMap,
    Split,
    Target,
    cold_start_history,
    fit_matrix,
    fit_tags,
    seen_items,
)

FloatArray = npt.NDArray[np.float64]
IntArray = npt.NDArray[np.intp]

MIN_RATING = 0.5
MAX_RATING = 5.0


@dataclass(frozen=True)
class FitData:
    """Everything a model may learn from, already limited by the split protocol."""

    matrix: "sparse.csr_matrix"  # users x items, rating values, fit ratings only
    item_map: IdMap
    movies: pd.DataFrame  # one row per item, in item_map order
    tags: pd.DataFrame  # user_id, movie_id, tag, timestamp: allowed tags only


@dataclass(frozen=True)
class History:
    """What the model is told about one user: item positions and the ratings given."""

    items: IntArray
    ratings: FloatArray

    def __post_init__(self) -> None:
        if self.items.shape != self.ratings.shape:
            raise ValueError("items and ratings must have the same length")
        if len(np.unique(self.items)) != len(self.items):
            raise ValueError("a history may not repeat an item")

    def __len__(self) -> int:
        return int(self.items.size)

    @classmethod
    def empty(cls) -> "History":
        return cls(np.array([], dtype=np.intp), np.array([], dtype=np.float64))

    @classmethod
    def from_frame(cls, ratings: pd.DataFrame, item_map: IdMap) -> "History":
        """Build from rows with ``movie_id`` and ``rating`` columns."""
        return cls(
            item_map.to_index(ratings["movie_id"]),
            ratings["rating"].to_numpy(dtype=np.float64),
        )


def fit_data(split: Split, movies: pd.DataFrame, target: Target) -> FitData:
    """Fit data for ``target`` exactly as the Step 5 protocol allows.

    Ratings come from ``fit_matrix`` (cold-start users' rows stay empty) and tags from
    ``fit_tags`` (each tag strictly earlier than its author's own cutoff).
    """
    ordered = movies.set_index("movie_id").reindex(split.item_map.ids).reset_index()
    if ordered["title"].isna().any():
        raise ValueError("every catalogue movie needs a row in ``movies``")
    return FitData(
        matrix=fit_matrix(split, target),
        item_map=split.item_map,
        movies=ordered,
        tags=fit_tags(split, target),
    )


def user_history(
    split: Split, user_id: int, target: Target, history_size: int | None = None
) -> History:
    """The ratings a model may see for ``user_id`` when recommending for ``target``.

    Same rule as the protocol's ``seen_items``: warm users give everything rated before
    the target cutoff; cold-start simulation users give only the first ``history_size``
    train ratings (0 gives an empty history).
    """
    known = seen_items(split, user_id, target, history_size)  # also checks the rules
    if history_size is not None:
        return History.from_frame(
            cold_start_history(split, user_id, history_size), split.item_map
        )
    rows = split.ratings
    mine = rows[(rows["user_id"] == user_id) & rows["movie_id"].isin(known)]
    return History.from_frame(mine, split.item_map)


def center_by_user(
    matrix: "sparse.csr_matrix",
) -> tuple["sparse.csr_matrix", FloatArray]:
    """Subtract each user's own mean rating from their ratings.

    Returns the centred matrix (same sparsity) and the user means (0 for empty rows).
    """
    counts = np.diff(matrix.indptr)
    sums = np.asarray(matrix.sum(axis=1), dtype=np.float64).ravel()
    means = np.divide(sums, counts, out=np.zeros_like(sums), where=counts > 0)
    centred = matrix.copy()
    centred.data = centred.data - np.repeat(means, counts)
    return centred, means


def rank_unseen(scores: FloatArray, seen: IntArray, k: int) -> IntArray:
    """Top-``k`` item positions by score, never returning a seen item.

    Order is score high to low; equal scores go to the lower item position, so results
    are deterministic. Items scored ``-inf`` or NaN mean "no evidence" and are placed
    after every scored item. This is the one shared "exclude seen" ranker.
    """
    if k < 0:
        raise ValueError("k must not be negative")
    usable = np.nan_to_num(scores, nan=-np.inf)
    keep = np.ones(usable.size, dtype=bool)
    keep[seen] = False
    positions = np.flatnonzero(keep)
    # lexsort: last key is primary. -score ascending == score descending.
    order = np.lexsort((positions, -usable[positions]))
    return positions[order][:k].astype(np.intp)


class Scorer(ABC):
    """Fit once, then score every catalogue item for any history."""

    name: str
    item_map: IdMap

    @abstractmethod
    def fit(self, data: FitData) -> Self:
        """Learn from ``data`` only."""

    @abstractmethod
    def score(self, history: History) -> FloatArray:
        """One score per catalogue item (higher is better); -inf means no evidence."""

    def evidence(self, history: History, item: int) -> Evidence:
        """Facts behind recommending item position ``item`` to this history."""
        return Evidence("no_evidence")

    def recommend(self, history: History, k: int = 10) -> npt.NDArray[np.int64]:
        """Top-``k`` raw movie IDs, excluding the history items."""
        positions = rank_unseen(self.score(history), history.items, k)
        return self.item_map.ids[positions]
