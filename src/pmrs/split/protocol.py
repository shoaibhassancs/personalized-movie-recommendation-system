"""The evaluation protocol: what a model may be fitted on, scored on, and recommended.

Rules (see ``holdout`` for how periods are assigned):

* Validation runs: fit on ``train`` ratings only. Test runs: refit on ``train`` +
  ``validation``. Validation is for tuning only; test is read once, after the refit.
* A user who is not ``eligible`` keeps their train ratings in the fit but is never
  scored, and their validation ratings are not used to refit.
* Tags: a tag is usable only if it is earlier than its own author's first held-out
  rating for the target (validation or test). Tags with no author cutoff are dropped.
* Candidate set, warm users: the whole catalogue minus the user's known pre-cutoff
  items. Held-out items stay eligible.
* Cold-start simulation: a fixed-seed 20% of users is kept out of every fit (ratings and
  tags). Such a user is scored with only their first ``h`` train ratings revealed
  (h = 0, 3, 5, 10). Their candidate set excludes **only those h revealed items**.
  Hidden train, validation and test ratings are unknown to the simulated new user, so
  they never filter the candidates and held-out items stay eligible. This is stricter
  on the models (hidden train items are ranked as unknown movies).

Known limit, stated plainly: cutoffs differ per user, so a fit still contains other
users' ratings and tags from *after* a scored user's own cutoff. Results support
"methods compared under the same per-user holdout protocol", not global leakage safety
or future prediction.
"""

from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy import sparse

from pmrs.split.holdout import (
    RELEVANT_THRESHOLD,
    assign_periods,
    summarize_users,
)
from pmrs.split.matrix import IdMap, build_interaction_matrix

Target = Literal["validation", "test"]
Group = Literal["warm", "cold_start"]

COLD_START_PERCENT = 20
COLD_START_SEED = 42
HISTORY_SIZES = (0, 3, 5, 10)


@dataclass(frozen=True)
class Split:
    """Everything the evaluation harness needs; built once by ``build_split``."""

    ratings: pd.DataFrame  # sorted by user, time; has ``period``
    users: pd.DataFrame  # per-user summary, indexed by user_id; has ``is_cold_start``
    tags: pd.DataFrame
    user_map: IdMap
    item_map: IdMap
    seed: int


def choose_cold_start_users(
    user_ids: npt.NDArray[np.int64], seed: int
) -> npt.NDArray[np.int64]:
    """Fixed-seed 20% of users (rounded down), returned sorted."""
    ordered = np.sort(user_ids)
    size = len(ordered) * COLD_START_PERCENT // 100
    chosen = np.random.default_rng(seed).choice(ordered, size=size, replace=False)
    return np.sort(chosen)


def build_split(
    ratings: pd.DataFrame,
    movies: pd.DataFrame,
    tags: pd.DataFrame,
    seed: int = COLD_START_SEED,
) -> Split:
    """Assign periods, summarise users, pick the cold-start users and build ID maps."""
    assigned = assign_periods(ratings)
    users = summarize_users(assigned)
    cold = choose_cold_start_users(users.index.to_numpy(dtype=np.int64), seed)
    users["is_cold_start"] = users.index.isin(cold)
    item_map = IdMap.from_ids(movies["movie_id"])
    user_map = IdMap.from_ids(users.index.to_numpy(dtype=np.int64))
    item_map.to_index(assigned["movie_id"])  # fails loudly if a rated movie is unknown
    return Split(
        ratings=assigned,
        users=users,
        tags=tags.reset_index(drop=True),
        user_map=user_map,
        item_map=item_map,
        seed=seed,
    )


def _cold_ids(split: Split) -> npt.NDArray[np.int64]:
    return split.users.index[split.users["is_cold_start"]].to_numpy(dtype=np.int64)


def fit_ratings(split: Split, target: Target) -> pd.DataFrame:
    """Ratings a model scored on ``target`` may be fitted on."""
    ratings = split.ratings
    period = ratings["period"]
    is_train = period == "train"
    if target == "validation":
        allowed = is_train
    else:
        eligible_ids = split.users.index[split.users["eligible"]]
        allowed = is_train | (
            (period == "validation") & ratings["user_id"].isin(eligible_ids)
        )
    not_cold = ~ratings["user_id"].isin(_cold_ids(split))
    return ratings[allowed & not_cold]


def fit_tags(split: Split, target: Target) -> pd.DataFrame:
    """Tags usable for content features: earlier than the author's own cutoff for
    ``target``.
    """
    column = "validation_cutoff" if target == "validation" else "test_cutoff"
    cutoff = split.tags["user_id"].map(split.users[column])
    earlier = (
        split.tags["timestamp"] < cutoff
    )  # False when the author has no cutoff (NaN)
    not_cold = ~split.tags["user_id"].isin(_cold_ids(split))
    return split.tags[earlier & not_cold]


def fit_matrix(split: Split, target: Target) -> "sparse.csr_matrix":
    """Sparse users x items matrix of ``fit_ratings``; cold-start users' rows stay
    empty.
    """
    return build_interaction_matrix(
        fit_ratings(split, target), split.user_map, split.item_map
    )


def _user_rows(split: Split, user_id: int) -> pd.DataFrame:
    ids = split.ratings["user_id"].to_numpy()
    low = int(np.searchsorted(ids, user_id, side="left"))
    high = int(np.searchsorted(ids, user_id, side="right"))
    return split.ratings.iloc[low:high]


def seen_items(
    split: Split, user_id: int, target: Target, history_size: int | None = None
) -> npt.NDArray[np.int64]:
    """Movie IDs the user is known to have rated when recommendations are made.

    Warm users (``history_size`` must be None): everything rated before the target
    period's cutoff. Cold-start simulation users (``history_size`` required): only the
    first ``history_size`` train ratings that are revealed to the model; nothing else.
    """
    is_cold = bool(split.users.loc[user_id, "is_cold_start"])
    if is_cold:
        if history_size is None:
            raise ValueError(
                f"user {user_id} is a cold-start simulation user: give history_size"
            )
        revealed = cold_start_history(split, user_id, history_size)
        return revealed["movie_id"].to_numpy(dtype=np.int64)
    if history_size is not None:
        raise ValueError(f"user {user_id} is a warm user: history_size does not apply")
    rows = _user_rows(split, user_id)
    before = ["train"] if target == "validation" else ["train", "validation"]
    return rows.loc[rows["period"].isin(before), "movie_id"].to_numpy(dtype=np.int64)


def candidate_items(
    split: Split, user_id: int, target: Target, history_size: int | None = None
) -> npt.NDArray[np.int64]:
    """Whole catalogue minus the items the user is known to have rated.

    Warm users: minus their pre-cutoff items. Cold-start simulation users: minus only
    the ``history_size`` revealed items (0 excludes nothing). Held-out items always stay
    eligible, and so do the cold-start user's hidden train ratings.
    """
    known = seen_items(split, user_id, target, history_size)
    return np.setdiff1d(split.item_map.ids, known)


def heldout_relevant_items(
    split: Split, user_id: int, target: Target
) -> npt.NDArray[np.int64]:
    """Movie IDs the user rated >= 4.0 in the target period."""
    rows = _user_rows(split, user_id)
    mask = (rows["period"] == target) & (rows["rating"] >= RELEVANT_THRESHOLD)
    return rows.loc[mask, "movie_id"].to_numpy(dtype=np.int64)


def evaluation_users(
    split: Split, target: Target, group: Group
) -> npt.NDArray[np.int64]:
    """Users scored on ``target``: eligible, with at least 1 relevant held-out item."""
    users = split.users
    flag = users[f"evaluated_{target}"]
    in_group = (
        users["is_cold_start"] if group == "cold_start" else ~users["is_cold_start"]
    )
    return users.index[flag & in_group].to_numpy(dtype=np.int64)


def cold_start_history(split: Split, user_id: int, size: int) -> pd.DataFrame:
    """The first ``size`` train ratings (by time) revealed for a simulated new user.

    Only users in the cold-start holdout may be asked for, so a model can never be
    handed a history for someone it was fitted on. ``size`` 0 returns an empty frame.
    """
    if not bool(split.users.loc[user_id, "is_cold_start"]):
        raise ValueError(f"user {user_id} is not in the cold-start holdout")
    train = _user_rows(split, user_id)
    train = train[train["period"] == "train"]
    if size > len(train):
        raise ValueError(
            f"user {user_id} has only {len(train)} train ratings, asked for {size}"
        )
    return train.iloc[:size]
