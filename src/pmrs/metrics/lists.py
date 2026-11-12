"""Step 13 list-level metrics: catalogue coverage and intra-list genre diversity.

Neither says whether recommendations are *right*. Coverage says how much of the
catalogue the method ever recommends (a method that shows the same 20 blockbusters to
everyone has near-zero coverage). Diversity says how different the movies inside one
list are from each other by genre.
"""

import math
from collections.abc import Collection, Sequence
from itertools import combinations


def catalogue_coverage(lists: Sequence[Sequence[int]], n_items: int, k: int) -> float:
    """Share of the catalogue that appears in at least one user's top ``k``."""
    if n_items < 1 or k < 1:
        raise ValueError("n_items and k must be at least 1")
    shown = {int(movie) for ranked in lists for movie in list(ranked)[:k]}
    return len(shown) / n_items


def genre_diversity(genre_sets: Sequence[Collection[str]]) -> float:
    """Mean pairwise genre distance in one list: 1 - Jaccard overlap, averaged.

    0 means every pair of movies has identical genres, 1 means no pair shares a genre.
    Two movies that both have no listed genres count as distance 0. A list with fewer
    than 2 movies has no pairs, so the result is NaN.
    """
    sets = [frozenset(s) for s in genre_sets]
    if len(sets) < 2:
        return math.nan
    distances = []
    for a, b in combinations(sets, 2):
        union = a | b
        distances.append(1.0 - len(a & b) / len(union) if union else 0.0)
    return sum(distances) / len(distances)
