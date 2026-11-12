"""Real-data smoke run for Steps 6-9: fit time, scoring time, peak memory, sample lists.

``uv run python -m pmrs.recommender.smoke`` fits each model on the validation fit data
(train ratings only) in its own subprocess, so peak memory is per model. It prints a few
recommendation lists for a human spot check. It never reads or prints held-out items and
computes no accuracy: metrics belong to Phase 3, and a glance at sample lists is not
evidence of quality.

Reminder of the claim limit: the fit still contains other users' ratings dated after a
scored user's own cutoff, so anything later measured on this protocol supports only
"methods compared under the same per-user holdout protocol".
"""

import resource
import subprocess
import sys
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from pmrs.data import load_movielens
from pmrs.recommender.base import FitData, History, Scorer, fit_data, user_history
from pmrs.recommender.baselines import (
    BayesianAverageScorer,
    PopularityScorer,
    RandomScorer,
)
from pmrs.recommender.content import ContentScorer, genre_names
from pmrs.recommender.knn import ItemKNNScorer
from pmrs.recommender.svd import SVDScorer
from pmrs.split import Split, build_split, evaluation_users

RAW_DIR = Path("data/raw/ml-latest-small")
MODELS = (
    "random",
    "popularity",
    "bayesian_average",
    "content",
    "content_no_tags",
    "item_knn",
    "svd",
)
TOP = 5


def make_model(name: str) -> Scorer:
    factories: dict[str, Callable[[], Scorer]] = {
        "random": RandomScorer,
        "popularity": PopularityScorer,
        "bayesian_average": BayesianAverageScorer,
        "content": ContentScorer,
        "content_no_tags": lambda: ContentScorer(use_tags=False),
        "item_knn": ItemKNNScorer,
        "svd": SVDScorer,
    }
    return factories[name]()


def peak_mb() -> float:
    """Peak resident memory of this process (bytes on macOS, kilobytes on Linux)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak / (1024 * 1024 if sys.platform == "darwin" else 1024)


def genre_shares(movies: pd.DataFrame, movie_ids: np.ndarray) -> Counter[str]:
    genres = movies.set_index("movie_id").loc[movie_ids, "genres"]
    counts: Counter[str] = Counter()
    for entry in genres:
        counts.update(genre_names(entry))
    return counts


def describe_history(movies: pd.DataFrame, split: Split, history: History) -> str:
    if len(history) == 0:
        return "no ratings"
    counts = genre_shares(movies, split.item_map.ids[history.items])
    top = ", ".join(f"{g} {n}" for g, n in counts.most_common(3))
    return f"{len(history)} ratings; top genres: {top}"


def sample_users(
    split: Split, movies: pd.DataFrame
) -> list[tuple[str, int, int | None]]:
    """(label, user_id, history_size) for the spot check: warm, sci-fi-heavy, cold."""
    warm = evaluation_users(split, "validation", "warm")
    scifi_share = {}
    for user in warm:
        history = user_history(split, int(user), "validation")
        if len(history) >= 20:
            counts = genre_shares(movies, split.item_map.ids[history.items])
            scifi_share[int(user)] = counts["sci-fi"] / len(history)
    scifi_user = max(scifi_share, key=lambda u: (scifi_share[u], -u))
    cold = evaluation_users(split, "validation", "cold_start")
    cold_user = int(cold[0])
    picks: list[tuple[str, int, int | None]] = [
        ("warm (first id)", int(warm[0]), None),
        ("warm (middle id)", int(warm[len(warm) // 2]), None),
        ("warm (most Sci-Fi history)", scifi_user, None),
        ("cold-start simulation, 5 revealed", cold_user, 5),
        ("cold-start simulation, 0 revealed", cold_user, 0),
    ]
    return picks


def run_one(name: str) -> None:
    data = load_movielens(RAW_DIR)
    split = build_split(data.ratings, data.movies, data.tags)
    fit: FitData = fit_data(split, data.movies, "validation")
    users = sample_users(split, data.movies)
    baseline = peak_mb()
    if name == "none":
        print(f"[none] load + split + fit data only: peak memory {baseline:.0f} MB")
        return
    model = make_model(name)
    start = time.perf_counter()
    model.fit(fit)
    fit_seconds = time.perf_counter() - start
    histories = [
        user_history(split, user, "validation", size) for _, user, size in users
    ]
    start = time.perf_counter()
    for history in histories:
        model.score(history)
    score_ms = 1000 * (time.perf_counter() - start) / len(histories)
    print(
        f"[{name}] fit {fit_seconds:.2f} s; score one user {score_ms:.1f} ms; "
        f"peak memory {peak_mb():.0f} MB (data loading alone: {baseline:.0f} MB)"
    )
    titles = fit.movies.set_index("movie_id")
    for (label, user, _), history in zip(users, histories, strict=True):
        print(
            f"  {label}, user {user}: {describe_history(data.movies, split, history)}"
        )
        for movie_id in model.recommend(history, k=TOP):
            row = titles.loc[movie_id]
            print(f"      {row['title']}  [{'|'.join(row['genres'])}]")


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--model":
        run_one(sys.argv[2])
        return
    for name in ("none", *MODELS):
        subprocess.run(
            [sys.executable, "-m", "pmrs.recommender.smoke", "--model", name],
            check=True,
        )


if __name__ == "__main__":
    main()
