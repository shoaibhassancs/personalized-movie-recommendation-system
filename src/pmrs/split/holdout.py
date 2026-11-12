"""Per-user temporal holdout (owner decision, Step 5).

Each user's own ratings are ordered by time. The latest ``ceil(10%)`` become test and
the
preceding ``ceil(10%)`` become validation; everything earlier is train. Ratings with
equal
timestamps are never separated: a tie at a boundary goes to the later period.

This is NOT a global chronological split. Different users have different cutoff dates,
so a
model fitted on everyone's training data still sees other users' later ratings. The only
claim it supports is "methods compared under the same per-user holdout protocol".
"""

import numpy as np
import pandas as pd

HOLDOUT_PERCENT = 10  # of a user's ratings, rounded up, for each of validation and test
MIN_TRAIN_RATINGS = 10
MAX_HELDOUT_SHARE = 0.30
RELEVANT_THRESHOLD = 4.0

PERIOD_ORDER = ("train", "validation", "test")


def _ceil_percent(count: int, percent: int) -> int:
    """ceil(count * percent / 100) in integer arithmetic (avoids float error at 30 *
    0.1).
    """
    return -(-count * percent // 100)


def _tail_start(timestamps: np.ndarray, target_size: int) -> int:
    """Index where the latest-in-time tail starts, keeping equal timestamps together.

    ``timestamps`` is sorted ascending. The tail holds at least ``target_size`` items
    (or
    everything if there are fewer), and grows to include any ties at its boundary.
    """
    count = len(timestamps)
    if target_size >= count:
        return 0
    boundary = timestamps[count - target_size]
    return int(np.searchsorted(timestamps, boundary, side="left"))


def assign_periods(ratings: pd.DataFrame) -> pd.DataFrame:
    """Return ratings sorted by (user, time, movie) with a ``period`` column added."""
    needed = {"user_id", "movie_id", "rating", "timestamp"}
    if not needed <= set(ratings.columns):
        raise ValueError(f"ratings must have columns {sorted(needed)}")
    if ratings.duplicated(["user_id", "movie_id"]).any():
        raise ValueError("duplicate (user_id, movie_id) pairs in ratings")

    ordered = ratings.sort_values(
        ["user_id", "timestamp", "movie_id"], kind="stable"
    ).reset_index(drop=True)
    stamps = ordered["timestamp"].to_numpy()
    codes = np.zeros(len(ordered), dtype=np.int8)
    start = 0
    for size in ordered.groupby("user_id", sort=True).size().tolist():
        count = int(size)
        user_stamps = stamps[start : start + count]
        target = _ceil_percent(count, HOLDOUT_PERCENT)
        test_start = _tail_start(user_stamps, target)
        validation_start = _tail_start(user_stamps[:test_start], target)
        codes[start + test_start : start + count] = 2
        codes[start + validation_start : start + test_start] = 1
        start += count
    dtype = pd.CategoricalDtype(categories=list(PERIOD_ORDER), ordered=True)
    ordered["period"] = pd.Categorical.from_codes(codes, dtype=dtype)
    return ordered


def summarize_users(assigned: pd.DataFrame) -> pd.DataFrame:
    """One row per user: period sizes, cutoffs, eligibility and evaluation flags.

    ``eligible`` users may be scored. Others keep their train ratings in the fit (the
    caller decides which periods feed a fit) but are never scored.
    ``validation_cutoff`` / ``test_cutoff`` are the user's first held-out timestamps;
    they
    also bound which tags may be used (see ``protocol.fit_tags``).
    """
    periods = assigned["period"].astype(str)
    sizes = (
        assigned.groupby([assigned["user_id"], periods]).size().unstack(fill_value=0)
    ).reindex(columns=list(PERIOD_ORDER), fill_value=0)
    sizes.columns = [f"n_{name}" for name in PERIOD_ORDER]
    users = sizes.copy()
    users["n_ratings"] = users[[f"n_{p}" for p in PERIOD_ORDER]].sum(axis=1)

    relevant = assigned[assigned["rating"] >= RELEVANT_THRESHOLD]
    relevant_counts = (
        relevant.groupby([relevant["user_id"], relevant["period"].astype(str)])
        .size()
        .unstack(fill_value=0)
        .reindex(index=users.index, columns=list(PERIOD_ORDER), fill_value=0)
    )
    for name in PERIOD_ORDER:
        users[f"n_relevant_{name}"] = relevant_counts[name]

    first = (
        assigned.groupby([assigned["user_id"], periods])["timestamp"]
        .min()
        .unstack()
        .reindex(columns=list(PERIOD_ORDER))
    )
    test_cut = first["test"]
    users["test_cutoff"] = test_cut
    users["validation_cutoff"] = first["validation"].fillna(test_cut)

    users["validation_share"] = users["n_validation"] / users["n_ratings"]
    users["test_share"] = users["n_test"] / users["n_ratings"]
    small_train = users["n_train"] < MIN_TRAIN_RATINGS
    big_heldout = (users["validation_share"] > MAX_HELDOUT_SHARE) | (
        users["test_share"] > MAX_HELDOUT_SHARE
    )
    users["exclusion_reason"] = np.select(
        [small_train & big_heldout, small_train, big_heldout],
        [
            "train_below_minimum and heldout_share_above_maximum",
            "train_below_minimum",
            "heldout_share_above_maximum",
        ],
        default="",
    )
    users["eligible"] = ~(small_train | big_heldout)
    users["evaluated_validation"] = users["eligible"] & (
        users["n_relevant_validation"] > 0
    )
    users["evaluated_test"] = users["eligible"] & (users["n_relevant_test"] > 0)
    return users
