"""Real-data smoke run for Steps 6-12: fit time, scoring time, peak memory, samples.

``uv run python -m pmrs.recommender.smoke`` fits each model on the validation fit data
(train ratings only) in its own subprocess, so peak memory is per model, then runs the
hybrid ``Recommender`` the same way (with an artifact save/load round trip in a
temporary folder). It prints a few recommendation lists for a human spot check. It
never reads or prints held-out items and computes no accuracy: metrics belong to
Phase 3, and a glance at sample lists is not evidence of quality.

Reminder of the claim limit: the fit still contains other users' ratings dated after a
scored user's own cutoff, so anything later measured on this protocol supports only
"methods compared under the same per-user holdout protocol".
"""

import resource
import subprocess
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

from pmrs.data import load_movielens
from pmrs.recommender.artifact import (
    data_fingerprint,
    load_recommender,
    save_recommender,
)
from pmrs.recommender.base import FitData, History, Scorer, fit_data, user_history
from pmrs.recommender.baselines import (
    BayesianAverageScorer,
    PopularityScorer,
    RandomScorer,
)
from pmrs.recommender.content import ContentScorer, genre_names
from pmrs.recommender.knn import ItemKNNScorer
from pmrs.recommender.recommender import (
    Recommender,
    UserProfile,
    profile_from_history,
)
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
    if name == "hybrid":
        run_hybrid(split, fit, users, baseline)
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


COLD_SIZES = (0, 3, 5, 10)  # revealed-rating counts in the cold-start simulation
STRATEGY_ORDER = (
    "random",
    "popularity",
    "bayesian_average",
    "content",
    "item_knn",
    "svd",
    "hybrid",
)


def show(
    label: str,
    profile: UserProfile,
    strategy: str,
    rec: Recommender,
    loaded: Recommender,
) -> None:
    """Print one top-``TOP`` list with its sentences and the user's average rating.

    Also checks that the model loaded back from the artifact gives the same list and
    the same sentences.
    """
    before = rec.recommend(profile, strategy, k=TOP)
    after = loaded.recommend(profile, strategy, k=TOP)
    same = before.movie_ids == after.movie_ids and [
        i.explanation for i in before.items
    ] == [i.explanation for i in after.items]
    count = len(profile.ratings)
    average = (
        f"; average rating {sum(profile.ratings.values()) / count:.4f}" if count else ""
    )
    rung = f"; rung {before.branch}" if before.branch else ""
    print(
        f"  {label} [{strategy}]: {count} ratings{average}{rung}; "
        f"round trip identical: {same}"
    )
    for note in before.notes:
        print(f"      note: {note}")
    for item in before.items:
        print(f"      {item.title}  [{'|'.join(item.genres)}]")
        print(f"          {item.explanation}")


def run_hybrid(
    split: Split,
    fit: FitData,
    users: list[tuple[str, int, int | None]],
    baseline: float,
) -> None:
    """Fit the whole ``Recommender``, round-trip it through an artifact, print lists.

    Shown: every strategy for one warm user; the hybrid for two more warm users; the
    hybrid for one cold-start simulation user at 0, 3, 5 and 10 revealed ratings; and
    the no-ratings-with-favourite-genre case. Only pre-cutoff or revealed ratings are
    used, so no held-out item is read.
    """
    start = time.perf_counter()
    rec = Recommender.fit(fit, target="validation", data_hash=data_fingerprint(RAW_DIR))
    fit_seconds = time.perf_counter() - start

    def profile_of(user: int, size: int | None) -> UserProfile:
        history = user_history(split, user, "validation", size)
        return profile_from_history(history, split.item_map)

    warm_label, warm_user, _ = users[0]
    cold_user = users[3][1]
    shown: list[tuple[str, UserProfile, str]] = [
        (f"{warm_label}, user {warm_user}", profile_of(warm_user, None), strategy)
        for strategy in STRATEGY_ORDER
    ]
    for label, user, _ in users[1:3]:
        shown.append((f"{label}, user {user}", profile_of(user, None), "hybrid"))
    for size in COLD_SIZES:
        label = f"cold-start simulation, {size} revealed, user {cold_user}"
        shown.append((label, profile_of(cold_user, size), "hybrid"))
    shown.append(
        (
            "cold-start, 0 ratings, favourite genre Sci-Fi",
            UserProfile(genres=("sci-fi",)),
            "hybrid",
        )
    )
    with tempfile.TemporaryDirectory() as scratch:
        start = time.perf_counter()
        folder = save_recommender(rec, Path(scratch) / "artifact")
        save_seconds = time.perf_counter() - start
        size_mb = sum(p.stat().st_size for p in folder.iterdir()) / (1024 * 1024)
        start = time.perf_counter()
        loaded = load_recommender(folder)
        load_seconds = time.perf_counter() - start
        start = time.perf_counter()
        for _, profile, strategy in shown:
            rec.recommend(profile, strategy, k=TOP)
        recommend_ms = 1000 * (time.perf_counter() - start) / len(shown)
        print(
            f"[hybrid] fit all models {fit_seconds:.2f} s; recommend one list "
            f"{recommend_ms:.0f} ms; artifact {size_mb:.1f} MB "
            f"(save {save_seconds:.2f} s, load {load_seconds:.2f} s); "
            f"peak memory {peak_mb():.0f} MB "
            f"(data loading alone: {baseline:.0f} MB)"
        )
        for label, profile, strategy in shown:
            show(label, profile, strategy, rec, loaded)


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--model":
        run_one(sys.argv[2])
        return
    for name in ("none", *MODELS, "hybrid"):
        subprocess.run(
            [sys.executable, "-m", "pmrs.recommender.smoke", "--model", name],
            check=True,
        )


if __name__ == "__main__":
    main()
