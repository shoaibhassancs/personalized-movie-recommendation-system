"""Recommendation models (Steps 6-12): baselines, content-based, item-kNN and SVD,
plus the hybrid ladder, explanations and the ``Recommender`` class (see ``recommender``,
``hybrid``, ``explain``, ``artifact`` and ``cli``).

No web dependencies. Every model is fitted through ``fit_data``, which applies the
Step 5 protocol; see ``base`` for the leakage note.
"""

from pmrs.recommender.base import (
    FitData,
    History,
    Scorer,
    center_by_user,
    fit_data,
    rank_unseen,
    user_history,
)
from pmrs.recommender.baselines import (
    BayesianAverageScorer,
    PopularityScorer,
    RandomScorer,
)
from pmrs.recommender.content import ContentScorer
from pmrs.recommender.knn import ItemKNNScorer
from pmrs.recommender.svd import SVDScorer

__all__ = [
    "BayesianAverageScorer",
    "ContentScorer",
    "FitData",
    "History",
    "ItemKNNScorer",
    "PopularityScorer",
    "RandomScorer",
    "SVDScorer",
    "Scorer",
    "center_by_user",
    "fit_data",
    "rank_unseen",
    "user_history",
]
