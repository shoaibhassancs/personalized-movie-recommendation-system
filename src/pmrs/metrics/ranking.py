"""Step 13 ranking metrics for one user: Precision, Recall, MAP and NDCG at K.

All four use *binary* relevance: a held-out movie the user rated 4.0 or higher is
relevant (the project threshold), everything else is not. ``ranked`` is the list of
recommended movie ids, best first; ``relevant`` is the set of held-out relevant ids.

Plain-language meaning of each (for this project's offline comparison, not a promise
about what real users would do):

* ``precision_at_k``: of the K movies shown, the share that were relevant. A list
  shorter than K is not rewarded: the denominator is always K.
* ``recall_at_k``: of the user's relevant held-out movies, the share that appeared in
  the top K.
* ``average_precision_at_k``: rewards putting relevant movies early. Averaged over
  users it is MAP@K. Divided by ``min(number relevant, K)`` so a perfect list scores 1.
* ``ndcg_at_k``: like average precision but with a smoothly shrinking credit for lower
  ranks (1 / log2(rank + 1)), divided by the best possible score so 1 means perfect.

Edge cases, decided once: with **no relevant items** recall, average precision and NDCG
are undefined and return NaN (precision is 0, since nothing could be a hit). The
evaluation protocol never scores a user with no relevant held-out items, so NaN here
means a mistake upstream, and the harness refuses it. A list **shorter than K** is
scored on what it has. A list with a repeated movie id is an error, because it would
inflate scores.
"""

import math
from collections.abc import Collection, Sequence

import numpy as np
import numpy.typing as npt


def _hits(
    ranked: Sequence[int] | npt.NDArray[np.integer], relevant: Collection[int], k: int
) -> npt.NDArray[np.bool_]:
    """For each of the first ``k`` ranked movies: is it relevant?"""
    if k < 1:
        raise ValueError("k must be at least 1")
    top = np.asarray(ranked)[:k]
    if len(np.unique(top)) != len(top):
        raise ValueError("a ranked list may not repeat a movie")
    return np.isin(top, np.fromiter(relevant, dtype=np.int64))


def precision_at_k(
    ranked: Sequence[int] | npt.NDArray[np.integer], relevant: Collection[int], k: int
) -> float:
    return float(_hits(ranked, relevant, k).sum() / k)


def recall_at_k(
    ranked: Sequence[int] | npt.NDArray[np.integer], relevant: Collection[int], k: int
) -> float:
    hits = _hits(ranked, relevant, k)
    total = len(set(relevant))
    return float(hits.sum() / total) if total else math.nan


def average_precision_at_k(
    ranked: Sequence[int] | npt.NDArray[np.integer], relevant: Collection[int], k: int
) -> float:
    hits = _hits(ranked, relevant, k)
    total = len(set(relevant))
    if total == 0:
        return math.nan
    precision_at_each_rank = np.cumsum(hits) / np.arange(1, len(hits) + 1)
    return float((precision_at_each_rank * hits).sum() / min(total, k))


def ndcg_at_k(
    ranked: Sequence[int] | npt.NDArray[np.integer], relevant: Collection[int], k: int
) -> float:
    hits = _hits(ranked, relevant, k)
    total = len(set(relevant))
    if total == 0:
        return math.nan
    gains = 1.0 / np.log2(np.arange(2, len(hits) + 2))
    ideal = (1.0 / np.log2(np.arange(2, min(total, k) + 2))).sum()
    return float((gains * hits).sum() / ideal)
