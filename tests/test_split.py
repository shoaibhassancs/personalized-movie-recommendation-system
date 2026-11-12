"""Tests for the per-user holdout, candidate sets, tag cutoffs and cold-start isolation.

All data here is invented. Timestamps differ between users on purpose, because the
protocol is per-user (not a global cutoff).
"""

import numpy as np
import pandas as pd
import pytest

from pmrs.split import (
    IdMap,
    Split,
    assign_periods,
    build_interaction_matrix,
    build_split,
    candidate_items,
    choose_cold_start_users,
    cold_start_history,
    evaluation_users,
    fit_matrix,
    fit_ratings,
    fit_tags,
    heldout_relevant_items,
    seen_items,
    summarize_users,
)
from pmrs.split.holdout import _ceil_percent

BASE = 1_000_000_000


def make_ratings(
    user_ids: list[int], per_user: int = 30, shift: int = 100_000
) -> pd.DataFrame:
    """Distinct timestamps per user; each user starts at a different date."""
    rows = []
    for user in user_ids:
        for i in range(per_user):
            rows.append(
                {
                    "user_id": user,
                    "movie_id": i + 1,
                    "rating": 4.0 if i % 2 == 0 else 3.0,
                    "timestamp": BASE + user * shift + i * 10,
                }
            )
    return pd.DataFrame(rows)


def make_movies(count: int = 40) -> pd.DataFrame:
    return pd.DataFrame({"movie_id": np.arange(1, count + 1)})


def empty_tags() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "user_id": pd.Series(dtype="int64"),
            "movie_id": pd.Series(dtype="int64"),
            "tag": pd.Series(dtype="str"),
            "timestamp": pd.Series(dtype="int64"),
        }
    )


def periods_of(assigned: pd.DataFrame, user: int) -> dict[str, pd.DataFrame]:
    rows = assigned[assigned["user_id"] == user]
    return {
        name: rows[rows["period"] == name] for name in ("train", "validation", "test")
    }


# ---- holdout sizes and ordering -------------------------------------------------


@pytest.mark.parametrize(
    ("count", "expected"), [(1, 1), (10, 1), (11, 2), (20, 2), (30, 3), (31, 4)]
)
def test_ceil_percent_is_exact_integer_arithmetic(count: int, expected: int) -> None:
    # 30 * 0.1 is 3.0000000000000004 in floats, which would wrongly round up to 4
    assert _ceil_percent(count, 10) == expected


def test_sizes_are_ceil_ten_percent_each() -> None:
    ratings = make_ratings([1], per_user=25).sample(frac=1, random_state=1)  # shuffled
    parts = periods_of(assign_periods(ratings), 1)
    assert (len(parts["train"]), len(parts["validation"]), len(parts["test"])) == (
        19,
        3,
        3,
    )


def test_periods_are_in_time_order_for_every_user() -> None:
    assigned = assign_periods(make_ratings([1, 2, 3]).sample(frac=1, random_state=2))
    for user in (1, 2, 3):
        parts = periods_of(assigned, user)
        assert (
            parts["train"]["timestamp"].max() < parts["validation"]["timestamp"].min()
        )
        assert parts["validation"]["timestamp"].max() < parts["test"]["timestamp"].min()


def test_users_have_different_cutoffs() -> None:
    users = summarize_users(assign_periods(make_ratings([1, 2, 3])))
    assert users["test_cutoff"].nunique() == 3


# ---- ties ------------------------------------------------------------------------


def _with_stamps(stamps: list[int]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "user_id": 1,
            "movie_id": np.arange(1, len(stamps) + 1),
            "rating": 4.0,
            "timestamp": stamps,
        }
    )


def test_boundary_tie_goes_to_the_later_test_period() -> None:
    # 20 ratings, target 2 per period; the last 3 share a timestamp, so test grows to 3
    stamps = list(range(1, 18)) + [50, 50, 50]
    parts = periods_of(assign_periods(_with_stamps(stamps)), 1)
    assert sorted(parts["test"]["timestamp"]) == [50, 50, 50]
    assert len(parts["validation"]) == 2


def test_boundary_tie_goes_to_the_later_validation_period() -> None:
    # test = last 2 (stamps 90, 91); validation boundary falls inside a tie of three 40s
    stamps = list(range(1, 15)) + [40, 40, 40, 80, 90, 91]
    parts = periods_of(assign_periods(_with_stamps(sorted(stamps))), 1)
    assert sorted(parts["test"]["timestamp"]) == [90, 91]
    assert sorted(parts["validation"]["timestamp"]) == [40, 40, 40, 80]


def test_a_timestamp_never_appears_in_two_periods() -> None:
    rng = np.random.default_rng(0)
    rows = []
    for user in range(1, 40):
        n = int(rng.integers(5, 80))
        stamps = rng.integers(0, 12, size=n)  # heavy ties
        rows += [
            {"user_id": user, "movie_id": i + 1, "rating": 3.0, "timestamp": int(t)}
            for i, t in enumerate(stamps)
        ]
    assigned = assign_periods(pd.DataFrame(rows))
    spread = assigned.groupby(["user_id", "timestamp"], observed=True)[
        "period"
    ].nunique()
    assert (spread == 1).all()
    # ordering still holds with ties: later periods never start earlier
    for _, user_rows in assigned.groupby("user_id"):
        order = user_rows["period"].cat.codes.to_numpy()
        assert (np.diff(order) >= 0).all()


# ---- overlap and coverage --------------------------------------------------------


def test_each_rating_lands_in_exactly_one_period_and_nothing_is_lost() -> None:
    ratings = make_ratings([1, 2, 3, 4])
    assigned = assign_periods(ratings)
    assert len(assigned) == len(ratings)
    assert not assigned.duplicated(["user_id", "movie_id"]).any()
    assert assigned["period"].notna().all()
    merged = assigned.merge(ratings, on=["user_id", "movie_id"], suffixes=("", "_orig"))
    assert (merged["timestamp"] == merged["timestamp_orig"]).all()


def test_duplicate_user_movie_pairs_are_rejected() -> None:
    ratings = pd.concat([make_ratings([1], 12), make_ratings([1], 12).head(1)])
    with pytest.raises(ValueError, match="duplicate"):
        assign_periods(ratings)


def test_train_validation_test_item_sets_are_disjoint_per_user() -> None:
    assigned = assign_periods(make_ratings([1, 2, 3]))
    for user in (1, 2, 3):
        parts = periods_of(assigned, user)
        sets = [set(parts[name]["movie_id"]) for name in parts]
        assert (
            not (sets[0] & sets[1])
            and not (sets[0] & sets[2])
            and not (sets[1] & sets[2])
        )


# ---- eligibility and evaluation groups ----------------------------------------------


def _split_for(
    ratings: pd.DataFrame, tags: pd.DataFrame | None = None, seed: int = 0
) -> Split:
    return build_split(
        ratings, make_movies(), tags if tags is not None else empty_tags(), seed
    )


def test_user_with_big_heldout_share_is_excluded_but_keeps_train_in_fit() -> None:
    normal = make_ratings([1, 2, 3, 4, 5], per_user=30)
    # user 9: 20 ratings, the last 8 share one timestamp -> test is 40% > 30%
    stamps = list(range(1, 13)) + [99] * 8
    big = _with_stamps(stamps).assign(user_id=9)
    split = _split_for(pd.concat([normal, big]))
    row = split.users.loc[9]
    assert (
        not row["eligible"] and "heldout_share_above_maximum" in row["exclusion_reason"]
    )
    assert 9 not in evaluation_users(split, "test", "warm")
    assert 9 not in evaluation_users(split, "test", "cold_start")
    if not row["is_cold_start"]:
        in_fit = fit_ratings(split, "validation")
        assert (in_fit["user_id"] == 9).sum() == row["n_train"]
        # excluded users' validation ratings are not used even in the test refit
        refit = fit_ratings(split, "test")
        assert (refit["user_id"] == 9).sum() == row["n_train"]


def test_user_with_too_little_training_is_excluded() -> None:
    # 20 ratings: two tie groups of 6 make validation and test 30% each (allowed),
    # leaving only 8 train ratings (< 10)
    stamps = list(range(1, 9)) + [50] * 6 + [90] * 6
    short = _with_stamps(stamps).assign(user_id=7)
    split = _split_for(pd.concat([make_ratings([1, 2, 3]), short]))
    row = split.users.loc[7]
    assert (row["n_train"], row["n_validation"], row["n_test"]) == (8, 6, 6)
    assert not row["eligible"]
    assert row["exclusion_reason"] == "train_below_minimum"


def test_user_is_evaluated_only_with_a_relevant_item_in_that_period() -> None:
    ratings = make_ratings([1, 2, 3, 4, 5])
    # user 1: make every test rating irrelevant (< 4.0); exactly 4.0 counts as relevant
    assigned = assign_periods(ratings)
    test_keys = assigned.loc[
        (assigned["user_id"] == 1) & (assigned["period"] == "test"), "movie_id"
    ]
    ratings.loc[
        (ratings["user_id"] == 1) & ratings["movie_id"].isin(test_keys), "rating"
    ] = 3.5
    split = _split_for(ratings)
    assert not split.users.loc[1, "evaluated_test"]
    assert split.users.loc[1, "eligible"]
    on_threshold = ratings.copy()
    on_threshold.loc[
        (on_threshold["user_id"] == 1) & on_threshold["movie_id"].isin(test_keys),
        "rating",
    ] = 4.0
    assert _split_for(on_threshold).users.loc[1, "evaluated_test"]


def test_warm_and_cold_groups_are_disjoint_and_cover_evaluated_users() -> None:
    split = _split_for(make_ratings(list(range(1, 31))))
    for target in ("validation", "test"):
        warm = set(evaluation_users(split, target, "warm"))
        cold = set(evaluation_users(split, target, "cold_start"))
        assert not warm & cold
        flagged = set(split.users.index[split.users[f"evaluated_{target}"]])
        assert warm | cold == flagged


# ---- what a fit may use ------------------------------------------------------------


def test_fits_never_contain_test_ratings_and_validation_fit_is_train_only() -> None:
    split = _split_for(make_ratings(list(range(1, 21))))
    validation_fit = fit_ratings(split, "validation")
    test_fit = fit_ratings(split, "test")
    assert set(validation_fit["period"].astype(str)) == {"train"}
    assert set(test_fit["period"].astype(str)) == {"train", "validation"}
    assert len(test_fit) > len(validation_fit)


def test_each_users_fit_data_is_strictly_before_their_own_cutoff() -> None:
    split = _split_for(make_ratings(list(range(1, 21))))
    for target, column in (
        ("validation", "validation_cutoff"),
        ("test", "test_cutoff"),
    ):
        fit = fit_ratings(split, target)
        cutoff = fit["user_id"].map(split.users[column])
        assert (fit["timestamp"] < cutoff).all()


# ---- tags ---------------------------------------------------------------------------


def test_tags_must_be_strictly_earlier_than_their_authors_cutoff() -> None:
    ratings = make_ratings([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
    probe = _split_for(ratings)
    author = int(probe.users.index[~probe.users["is_cold_start"]][0])
    val_cut = int(probe.users.loc[author, "validation_cutoff"])
    test_cut = int(probe.users.loc[author, "test_cutoff"])
    tags = pd.DataFrame(
        {
            "user_id": [author] * 5 + [999],  # 999 has no ratings
            "movie_id": [1] * 6,
            "tag": ["a", "b", "c", "d", "e", "f"],
            "timestamp": [
                val_cut - 1,
                val_cut,
                test_cut - 1,
                test_cut,
                test_cut + 5,
                1,
            ],
        }
    )
    split = _split_for(ratings, tags)
    assert list(fit_tags(split, "validation")["tag"]) == ["a"]
    assert list(fit_tags(split, "test")["tag"]) == ["a", "b", "c"]
    # the tag by a user with no ratings ("f") is never used


# ---- candidate sets ------------------------------------------------------------------


def test_candidates_exclude_pre_cutoff_items_but_keep_heldout_items() -> None:
    split = _split_for(make_ratings([1, 2, 3, 4, 5]))
    user = 1
    parts = periods_of(split.ratings, user)
    train_items = set(parts["train"]["movie_id"])
    val_items = set(parts["validation"]["movie_id"])
    test_items = set(parts["test"]["movie_id"])

    val_candidates = set(candidate_items(split, user, "validation"))
    assert not val_candidates & train_items
    assert val_items <= val_candidates and test_items <= val_candidates

    test_candidates = set(candidate_items(split, user, "test"))
    assert not test_candidates & (train_items | val_items)
    assert test_items <= test_candidates
    # catalogue movies this user never rated (31..40) stay eligible
    assert set(range(31, 41)) <= test_candidates
    assert set(seen_items(split, user, "test")) == train_items | val_items


def test_heldout_relevant_items_are_the_target_periods_ratings_at_or_above_four() -> (
    None
):
    split = _split_for(make_ratings([1, 2, 3]))
    parts = periods_of(split.ratings, 1)
    expected = set(parts["test"].query("rating >= 4.0")["movie_id"])
    assert set(heldout_relevant_items(split, 1, "test")) == expected


# ---- cold-start simulation isolation ----------------------------------------------


def test_cold_start_choice_is_fixed_seed_twenty_percent_and_sorted() -> None:
    ids = np.arange(1, 611, dtype=np.int64)
    first = choose_cold_start_users(ids, seed=42)
    assert len(first) == 122
    assert np.array_equal(first, choose_cold_start_users(ids, seed=42))
    assert not np.array_equal(first, choose_cold_start_users(ids, seed=43))
    assert (np.diff(first) > 0).all()


def test_cold_start_users_are_absent_from_every_fit() -> None:
    ratings = make_ratings(list(range(1, 31)))
    users = list(range(1, 31))
    tags = pd.DataFrame(
        {
            "user_id": users,
            "movie_id": 1,
            "tag": "x",
            "timestamp": BASE,  # before every cutoff: only isolation can drop it
        }
    )
    split = _split_for(ratings, tags)
    cold = set(split.users.index[split.users["is_cold_start"]])
    assert len(cold) == 6
    for target in ("validation", "test"):
        assert not cold & set(fit_ratings(split, target)["user_id"])
        assert not cold & set(fit_tags(split, target)["user_id"])
        matrix = fit_matrix(split, target)
        rows = split.user_map.to_index(np.array(sorted(cold)))
        assert matrix[rows].nnz == 0  # their rows are entirely empty
        assert matrix.nnz == len(fit_ratings(split, target))


def test_cold_start_history_is_the_first_train_ratings_in_time_order() -> None:
    split = _split_for(make_ratings(list(range(1, 31))))
    user = int(split.users.index[split.users["is_cold_start"]][0])
    assert len(cold_start_history(split, user, 0)) == 0
    history = cold_start_history(split, user, 5)
    train = periods_of(split.ratings, user)["train"]
    assert list(history["movie_id"]) == list(train["movie_id"].head(5))
    assert set(history["period"].astype(str)) == {"train"}
    with pytest.raises(ValueError, match="only"):
        cold_start_history(split, user, len(train) + 1)


def test_history_cannot_be_requested_for_a_user_the_models_were_fitted_on() -> None:
    split = _split_for(make_ratings(list(range(1, 31))))
    warm = int(split.users.index[~split.users["is_cold_start"]][0])
    with pytest.raises(ValueError, match="not in the cold-start holdout"):
        cold_start_history(split, warm, 3)


def test_building_the_split_twice_gives_identical_results() -> None:
    ratings = make_ratings(list(range(1, 31)))
    one, two = _split_for(ratings), _split_for(ratings.sample(frac=1, random_state=5))
    assert one.users.equals(two.users)
    assert one.ratings.equals(two.ratings)


# ---- ID maps and the sparse matrix -------------------------------------------------


def test_id_map_is_sorted_and_rejects_unknown_ids() -> None:
    id_map = IdMap.from_ids(np.array([30, 10, 20, 10], dtype=np.int64))
    assert id_map.ids.tolist() == [10, 20, 30]
    assert id_map.to_index(np.array([30, 10], dtype=np.int64)).tolist() == [2, 0]
    assert 20 in id_map and 25 not in id_map
    with pytest.raises(KeyError):
        id_map.to_index(np.array([10, 25], dtype=np.int64))


def test_interaction_matrix_holds_ratings_in_the_right_cells() -> None:
    ratings = make_ratings([1, 2], per_user=12)
    users = IdMap.from_ids(np.array([1, 2, 3], dtype=np.int64))  # user 3 has no ratings
    items = IdMap.from_ids(np.arange(1, 21, dtype=np.int64))  # items 13..20 unrated
    matrix = build_interaction_matrix(ratings, users, items)
    assert matrix.shape == (3, 20)
    assert matrix.nnz == len(ratings)
    assert matrix[0, 0] == 4.0 and matrix[0, 1] == 3.0
    assert matrix[2].nnz == 0


# ---- cold-start candidate sets: only the revealed history may filter -----------------


def _cold_user_and_parts(split: Split) -> tuple[int, dict[str, pd.DataFrame]]:
    user = int(split.users.index[split.users["is_cold_start"]][0])
    return user, periods_of(split.ratings, user)


def test_history_zero_excludes_nothing_so_hidden_ratings_stay_candidates() -> None:
    split = _split_for(make_ratings(list(range(1, 31))))
    user, parts = _cold_user_and_parts(split)
    for target in ("validation", "test"):
        candidates = set(candidate_items(split, user, target, 0).tolist())
        assert candidates == set(make_movies()["movie_id"])  # the full catalogue
        for name in ("train", "validation", "test"):
            assert set(parts[name]["movie_id"]) <= candidates  # nothing hidden removed
    assert len(seen_items(split, user, "test", 0)) == 0


@pytest.mark.parametrize("history", [3, 5, 10])
def test_candidates_exclude_exactly_the_revealed_items(history: int) -> None:
    split = _split_for(make_ratings(list(range(1, 31))))
    user, parts = _cold_user_and_parts(split)
    revealed = set(parts["train"]["movie_id"].head(history))
    hidden_train = set(parts["train"]["movie_id"]) - revealed
    catalogue = set(make_movies()["movie_id"])
    for target in ("validation", "test"):
        candidates = set(candidate_items(split, user, target, history).tolist())
        assert candidates == catalogue - revealed
        assert len(candidates) == len(catalogue) - history
        # hidden training ratings do NOT filter a simulated new user's candidates
        assert hidden_train <= candidates
        # validation ratings never filter either, even for the test target
        assert set(parts["validation"]["movie_id"]) <= candidates
        # held-out items of the target period stay eligible
        assert set(parts[target]["movie_id"]) <= candidates


def test_candidate_set_shrinks_step_by_step_as_history_grows() -> None:
    split = _split_for(make_ratings(list(range(1, 31))))
    user, _ = _cold_user_and_parts(split)
    sets = [
        set(candidate_items(split, user, "test", h).tolist()) for h in (0, 3, 5, 10)
    ]
    assert [len(s) for s in sets] == [40, 37, 35, 30]
    assert all(later <= earlier for earlier, later in zip(sets, sets[1:], strict=False))


def test_relevant_heldout_items_are_always_candidates_for_cold_start_users() -> None:
    split = _split_for(make_ratings(list(range(1, 31))))
    users = evaluation_users(split, "test", "cold_start")
    assert len(users) > 0
    for user in users:
        wanted = set(heldout_relevant_items(split, int(user), "test").tolist())
        for history in (0, 3, 5, 10):
            assert wanted <= set(
                candidate_items(split, int(user), "test", history).tolist()
            )


def test_cold_start_candidates_demand_a_history_size_and_warm_users_refuse_one() -> (
    None
):
    split = _split_for(make_ratings(list(range(1, 31))))
    cold, _ = _cold_user_and_parts(split)
    warm = int(split.users.index[~split.users["is_cold_start"]][0])
    with pytest.raises(ValueError, match="give history_size"):
        candidate_items(split, cold, "test")  # would silently use hidden ratings
    with pytest.raises(ValueError, match="does not apply"):
        candidate_items(split, warm, "test", 3)
    with pytest.raises(ValueError, match="only"):
        candidate_items(split, cold, "test", 999)


def test_warm_candidates_still_exclude_all_pre_cutoff_items() -> None:
    split = _split_for(make_ratings(list(range(1, 31))))
    warm = int(split.users.index[~split.users["is_cold_start"]][0])
    parts = periods_of(split.ratings, warm)
    train, validation = (
        set(parts["train"]["movie_id"]),
        set(parts["validation"]["movie_id"]),
    )
    assert not set(candidate_items(split, warm, "validation").tolist()) & train
    assert not set(candidate_items(split, warm, "test").tolist()) & (train | validation)
    assert set(parts["test"]["movie_id"]) <= set(
        candidate_items(split, warm, "test").tolist()
    )
