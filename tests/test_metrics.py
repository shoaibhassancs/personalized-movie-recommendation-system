"""Step 13 tests: every metric against a value worked out by hand.

These prove the formulas are implemented as written. They say nothing about how good any
recommender is.
"""

import math

import numpy as np
import pytest

from pmrs.metrics import (
    average_precision_at_k,
    bootstrap_ci,
    bootstrap_ratio_ci,
    catalogue_coverage,
    genre_diversity,
    mae,
    ndcg_at_k,
    paired_bootstrap_difference,
    precision_at_k,
    recall_at_k,
    rmse,
)

RANKED = [1, 2, 3, 4, 5]
RELEVANT = {2, 5, 9}  # 9 is never recommended


# ---- ranking metrics ----------------------------------------------------------------


def test_precision_at_k_hand_values() -> None:
    assert precision_at_k(RANKED, RELEVANT, 1) == 0.0
    assert precision_at_k(RANKED, RELEVANT, 2) == 0.5  # movie 2 is a hit
    assert precision_at_k(RANKED, RELEVANT, 5) == pytest.approx(2 / 5)


def test_recall_at_k_hand_values() -> None:
    assert recall_at_k(RANKED, RELEVANT, 1) == 0.0
    assert recall_at_k(RANKED, RELEVANT, 2) == pytest.approx(1 / 3)
    assert recall_at_k(RANKED, RELEVANT, 5) == pytest.approx(2 / 3)  # 9 was missed


def test_average_precision_hand_value() -> None:
    # hits at rank 2 (precision 1/2) and rank 5 (precision 2/5); divided by min(3, 5)
    assert average_precision_at_k(RANKED, RELEVANT, 5) == pytest.approx(
        (1 / 2 + 2 / 5) / 3
    )
    # cut at 3: only the rank-2 hit counts; divided by min(3, 3)
    assert average_precision_at_k(RANKED, RELEVANT, 3) == pytest.approx((1 / 2) / 3)


def test_ndcg_hand_value() -> None:
    dcg = 1 / math.log2(3) + 1 / math.log2(6)  # hits at ranks 2 and 5
    ideal = 1 + 1 / math.log2(3) + 1 / math.log2(4)  # three relevant, best order
    assert ndcg_at_k(RANKED, RELEVANT, 5) == pytest.approx(dcg / ideal)


def test_perfect_lists_score_one_and_all_misses_score_zero() -> None:
    perfect = [2, 5, 9, 1, 3]
    assert ndcg_at_k(perfect, RELEVANT, 5) == pytest.approx(1.0)
    assert average_precision_at_k(perfect, RELEVANT, 5) == pytest.approx(1.0)
    assert recall_at_k(perfect, RELEVANT, 3) == 1.0
    misses = [1, 3, 4, 6, 7]
    for metric in (precision_at_k, recall_at_k, average_precision_at_k, ndcg_at_k):
        assert metric(misses, RELEVANT, 5) == 0.0


def test_ideal_dcg_is_capped_at_k_when_there_are_more_relevant_than_k() -> None:
    # 10 relevant movies but K = 2 and both shown are hits: perfect for that K
    assert ndcg_at_k([1, 2], set(range(1, 11)), 2) == pytest.approx(1.0)
    assert average_precision_at_k([1, 2], set(range(1, 11)), 2) == pytest.approx(1.0)
    assert recall_at_k([1, 2], set(range(1, 11)), 2) == pytest.approx(0.2)


def test_k_larger_than_the_list_scores_what_is_there() -> None:
    short = [2, 7]  # only 2 recommended, K = 10; movie 2 is a hit at rank 1
    assert precision_at_k(short, RELEVANT, 10) == pytest.approx(1 / 10)  # not 1/2
    assert recall_at_k(short, RELEVANT, 10) == pytest.approx(1 / 3)
    # one hit at rank 1 (precision 1), divided by min(3 relevant, K = 10) = 3
    assert average_precision_at_k(short, RELEVANT, 10) == pytest.approx(1 / 3)
    ideal = 1 + 1 / math.log2(3) + 1 / math.log2(4)
    assert ndcg_at_k(short, RELEVANT, 10) == pytest.approx(1 / ideal)


def test_no_relevant_items_is_undefined_not_a_fake_zero() -> None:
    assert precision_at_k(RANKED, set(), 5) == 0.0  # nothing could be a hit
    assert math.isnan(recall_at_k(RANKED, set(), 5))
    assert math.isnan(average_precision_at_k(RANKED, set(), 5))
    assert math.isnan(ndcg_at_k(RANKED, set(), 5))


def test_empty_list_scores_zero_where_defined() -> None:
    assert precision_at_k([], RELEVANT, 5) == 0.0
    assert recall_at_k([], RELEVANT, 5) == 0.0
    assert ndcg_at_k([], RELEVANT, 5) == 0.0


def test_ranking_metrics_reject_bad_input() -> None:
    for metric in (precision_at_k, recall_at_k, average_precision_at_k, ndcg_at_k):
        with pytest.raises(ValueError):
            metric(RANKED, RELEVANT, 0)
        with pytest.raises(ValueError, match="repeat"):
            metric([1, 1, 2], RELEVANT, 3)
    # a repeat beyond K is not inside the scored part, so it is not an error
    assert precision_at_k([1, 2, 3, 3], RELEVANT, 3) == pytest.approx(1 / 3)


def test_ranking_metrics_accept_numpy_arrays_and_ignore_duplicate_relevant() -> None:
    assert precision_at_k(np.array([2, 5, 1]), np.array([2, 5, 5]), 2) == 1.0
    assert recall_at_k(np.array([2, 1]), [2, 2, 5], 2) == pytest.approx(1 / 2)


# ---- rating metrics -----------------------------------------------------------------


def test_rmse_and_mae_hand_values() -> None:
    predicted = np.array([3.0, 4.0, 2.0])
    actual = np.array([5.0, 4.0, 1.0])  # errors -2, 0, +1
    assert rmse(predicted, actual) == pytest.approx(math.sqrt((4 + 0 + 1) / 3))
    assert mae(predicted, actual) == pytest.approx(1.0)
    assert rmse(actual, actual) == 0.0


def test_rating_metrics_empty_is_nan_and_shape_mismatch_is_an_error() -> None:
    assert math.isnan(rmse(np.array([]), np.array([])))
    assert math.isnan(mae(np.array([]), np.array([])))
    with pytest.raises(ValueError):
        rmse(np.array([1.0]), np.array([1.0, 2.0]))


# ---- list metrics -------------------------------------------------------------------


def test_catalogue_coverage_counts_distinct_movies_in_the_top_k() -> None:
    lists = [[1, 2, 3], [2, 3, 4]]
    assert catalogue_coverage(lists, n_items=10, k=3) == pytest.approx(4 / 10)
    assert catalogue_coverage(lists, n_items=10, k=1) == pytest.approx(2 / 10)  # {1, 2}
    assert catalogue_coverage([[1, 2]], n_items=10, k=20) == pytest.approx(2 / 10)
    assert catalogue_coverage([], n_items=10, k=3) == 0.0
    with pytest.raises(ValueError):
        catalogue_coverage(lists, n_items=0, k=3)


def test_genre_diversity_hand_values() -> None:
    sets = [{"a", "b"}, {"a"}, {"c"}]
    # distances: (ab,a) = 1 - 1/2; (ab,c) = 1; (a,c) = 1  ->  mean 2.5 / 3
    assert genre_diversity(sets) == pytest.approx(2.5 / 3)
    assert genre_diversity([{"a"}, {"a"}]) == 0.0  # identical genres
    assert genre_diversity([{"a"}, {"b"}]) == 1.0  # nothing shared
    assert genre_diversity([set(), set()]) == 0.0  # both unlisted: no distance
    assert math.isnan(genre_diversity([{"a"}]))  # no pairs
    assert math.isnan(genre_diversity([]))


# ---- bootstrap intervals ------------------------------------------------------------


def test_bootstrap_of_a_constant_is_that_constant() -> None:
    mean, low, high = bootstrap_ci(np.full(20, 0.3))
    assert (mean, low, high) == (pytest.approx(0.3),) * 3


def test_bootstrap_interval_contains_the_mean_and_is_reproducible() -> None:
    values = np.random.default_rng(0).random(200)
    first = bootstrap_ci(values, seed=7)
    assert first == bootstrap_ci(values, seed=7)  # same seed, same answer
    assert first != bootstrap_ci(values, seed=8)
    mean, low, high = first
    assert mean == pytest.approx(values.mean())
    assert low < mean < high
    assert high - low < 0.2  # 200 users: a tight interval


def test_bootstrap_interval_is_wider_with_fewer_users() -> None:
    rng = np.random.default_rng(1)
    big = bootstrap_ci(rng.random(400))
    small = bootstrap_ci(rng.random(20))
    assert (small[2] - small[1]) > (big[2] - big[1])


def test_bootstrap_rejects_nan_empty_and_bad_settings() -> None:
    with pytest.raises(ValueError):
        bootstrap_ci(np.array([0.1, np.nan]))
    with pytest.raises(ValueError):
        bootstrap_ci(np.array([]))
    with pytest.raises(ValueError):
        bootstrap_ci(np.ones(5), n_boot=0)
    with pytest.raises(ValueError):
        bootstrap_ci(np.ones(5), level=1.5)


def test_paired_difference_detects_a_consistent_gap_and_a_null() -> None:
    rng = np.random.default_rng(2)
    base = rng.random(150)
    mean, low, high = paired_bootstrap_difference(base + 0.1, base)
    assert mean == pytest.approx(0.1)
    assert low > 0  # the gap held in every resample of users
    mean, low, high = paired_bootstrap_difference(base, base)
    assert (mean, low, high) == (0.0, 0.0, 0.0)
    noise = rng.normal(0, 0.3, 150)
    _, low, high = paired_bootstrap_difference(base + noise, base)
    assert low < 0 < high  # pure noise: the interval spans zero
    with pytest.raises(ValueError):
        paired_bootstrap_difference(np.ones(3), np.ones(4))


def test_ratio_bootstrap_is_a_pooled_rate() -> None:
    squared_error = np.array([4.0, 0.0, 9.0])
    counts = np.array([2.0, 2.0, 1.0])
    mean, low, high = bootstrap_ratio_ci(squared_error, counts)
    assert mean == pytest.approx(13 / 5)  # pooled, not the mean of per-user rates
    assert low <= mean <= high
    with pytest.raises(ValueError):
        bootstrap_ratio_ci(np.ones(3), np.zeros(3))
