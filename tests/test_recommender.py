"""Tests for the Step 6-9 models on small invented datasets with hand-checked answers.

These prove the mechanics (orderings, seen-item exclusion, protocol rules). They say
nothing about recommendation quality: that is measured in Phase 3.
"""

import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from pmrs.recommender import (
    BayesianAverageScorer,
    ContentScorer,
    FitData,
    History,
    ItemKNNScorer,
    PopularityScorer,
    RandomScorer,
    Scorer,
    SVDScorer,
    center_by_user,
    fit_data,
    rank_unseen,
    user_history,
)
from pmrs.recommender.content import genre_names
from pmrs.split import (
    IdMap,
    build_split,
    candidate_items,
    evaluation_users,
    heldout_relevant_items,
)

BASE = 1_000_000_000
NO_TAGS = pd.DataFrame(
    {
        "user_id": pd.Series(dtype="int64"),
        "movie_id": pd.Series(dtype="int64"),
        "tag": pd.Series(dtype="str"),
        "timestamp": pd.Series(dtype="int64"),
    }
)


def toy_fit(
    triples: list[tuple[int, int, float]],
    n_users: int,
    n_items: int,
    movies: pd.DataFrame | None = None,
    tags: pd.DataFrame | None = None,
) -> FitData:
    """FitData from (user_position, item_position, rating); item ids are 10, 11, ..."""
    rows, cols, vals = zip(*triples, strict=True)
    matrix = sparse.coo_matrix((vals, (rows, cols)), shape=(n_users, n_items)).tocsr()
    ids = np.arange(10, 10 + n_items)
    if movies is None:
        movies = pd.DataFrame(
            {
                "movie_id": ids,
                "title": [f"m{i}" for i in ids],
                "title_clean": [f"m{i}" for i in ids],
                "genres": [("Drama",)] * n_items,
                "year": 2000,
            }
        )
    return FitData(
        matrix=matrix,
        item_map=IdMap.from_ids(ids),
        movies=movies,
        tags=NO_TAGS if tags is None else tags,
    )


def hist(items: list[int], ratings: list[float]) -> History:
    return History(np.array(items, dtype=np.intp), np.array(ratings, dtype=np.float64))


# ---- shared ranker ------------------------------------------------------------------


def test_rank_unseen_orders_by_score_and_skips_seen() -> None:
    scores = np.array([0.1, 0.9, 0.5, 0.7, 0.3])
    ranked = rank_unseen(scores, np.array([1]), k=10)
    assert ranked.tolist() == [3, 2, 4, 0]  # item 1 has the top score but is seen


def test_rank_unseen_breaks_ties_by_lower_position() -> None:
    ranked = rank_unseen(np.array([2.0, 2.0, 2.0, 5.0]), np.array([], dtype=np.intp), 4)
    assert ranked.tolist() == [3, 0, 1, 2]


def test_rank_unseen_puts_no_evidence_last_and_never_returns_seen() -> None:
    scores = np.array([-np.inf, 1.0, np.nan, 0.5])
    ranked = rank_unseen(scores, np.array([1]), k=10)
    assert ranked.tolist() == [3, 0, 2]
    assert 1 not in ranked


def test_rank_unseen_respects_k_and_rejects_negative_k() -> None:
    assert len(rank_unseen(np.arange(5.0), np.array([], dtype=np.intp), 2)) == 2
    with pytest.raises(ValueError):
        rank_unseen(np.arange(3.0), np.array([], dtype=np.intp), -1)


def test_history_rejects_repeated_items_and_length_mismatch() -> None:
    with pytest.raises(ValueError):
        hist([1, 1], [3.0, 4.0])
    with pytest.raises(ValueError):
        hist([1, 2], [3.0])


def test_center_by_user_subtracts_each_users_own_mean() -> None:
    matrix = sparse.csr_matrix(np.array([[5.0, 3.0, 0.0], [0.0, 0.0, 0.0]]))
    centred, means = center_by_user(matrix)
    assert means.tolist() == [4.0, 0.0]
    assert centred.toarray().tolist() == [[1.0, -1.0, 0.0], [0.0, 0.0, 0.0]]


# ---- Step 6 baselines ---------------------------------------------------------------

# Items 0..4 (ids 10..14). Counts 3,2,3,1,0; rating sums 12,5,14,1,0.
BASELINE_TRIPLES = [
    (0, 0, 5.0),
    (0, 1, 3.0),
    (1, 0, 4.0),
    (1, 1, 2.0),
    (1, 2, 5.0),
    (2, 0, 3.0),
    (2, 2, 4.0),
    (2, 3, 1.0),
    (3, 2, 5.0),
]


def test_popularity_order_is_the_hand_checked_order() -> None:
    model = PopularityScorer().fit(toy_fit(BASELINE_TRIPLES, 4, 5))
    # counts 3,2,3,1,0; the 3-vs-3 tie goes to the lower position
    assert model.recommend(History.empty(), k=5).tolist() == [10, 12, 11, 13, 14]


def test_bayesian_average_matches_hand_calculation() -> None:
    model = BayesianAverageScorer(prior_strength=2).fit(toy_fit(BASELINE_TRIPLES, 4, 5))
    c = 32 / 9  # overall mean of the 9 ratings
    expected = [
        (12 + 2 * c) / 5,
        (5 + 2 * c) / 4,
        (14 + 2 * c) / 5,
        (1 + 2 * c) / 3,
        c,  # never rated: sits exactly at the overall mean
    ]
    assert model.score(History.empty()).tolist() == pytest.approx(expected)
    assert model.recommend(History.empty(), k=5).tolist() == [12, 10, 14, 11, 13]


def test_bayesian_average_pulls_a_single_rating_toward_the_mean() -> None:
    # item 0: one 5-star rating; item 1: twenty 4.5s; item 2: thirty 2s (low mean)
    triples = [(0, 0, 5.0)]
    triples += [(u, 1, 4.5) for u in range(1, 21)]
    triples += [(u, 2, 2.0) for u in range(21, 51)]
    plain = BayesianAverageScorer(prior_strength=0).fit(toy_fit(triples, 51, 3))
    shrunk = BayesianAverageScorer(prior_strength=10).fit(toy_fit(triples, 51, 3))
    assert plain.score(History.empty()).argmax() == 0  # raw mean: the lone 5 wins
    # overall mean is 155/51 = 3.04, so the lone 5 becomes (5 + 30.4) / 11 = 3.22,
    # while the well-supported 4.5 stays at (90 + 30.4) / 30 = 4.01
    assert shrunk.score(History.empty()).argmax() == 1


def test_baselines_never_return_a_seen_item() -> None:
    data = toy_fit(BASELINE_TRIPLES, 4, 5)
    history = hist([2, 0], [5.0, 4.0])
    for model in (RandomScorer(), PopularityScorer(), BayesianAverageScorer()):
        got = model.fit(data).recommend(history, k=10)
        assert set(got.tolist()) == {11, 13, 14}
        assert len(got) == 3


def test_random_is_reproducible_and_seed_dependent() -> None:
    data = toy_fit(BASELINE_TRIPLES, 4, 5)
    a = RandomScorer(seed=1).fit(data).score(History.empty())
    b = RandomScorer(seed=1).fit(data).score(History.empty())
    c = RandomScorer(seed=2).fit(data).score(History.empty())
    assert a.tolist() == b.tolist()
    assert a.tolist() != c.tolist()


# ---- Step 7 content-based -----------------------------------------------------------


def genre_movies(genres: list[tuple[str, ...]], titles: list[str]) -> pd.DataFrame:
    ids = np.arange(10, 10 + len(genres))
    return pd.DataFrame(
        {
            "movie_id": ids,
            "title": titles,
            "title_clean": titles,
            "genres": genres,
            "year": 1999,
        }
    )


# genres use the loader's real format: a tuple of names per movie
SCIFI_MOVIES = genre_movies(
    [
        ("Sci-Fi",),
        ("Sci-Fi",),
        ("Romance",),
        ("Romance",),
        ("Sci-Fi", "Romance"),
        ("Sci-Fi",),
    ],
    ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot"],
)


def scifi_fit(tags: pd.DataFrame | None = None) -> FitData:
    return toy_fit([(0, 0, 4.0)], 1, 6, movies=SCIFI_MOVIES, tags=tags)


def test_genre_parsing_accepts_tuples_and_pipe_strings_and_skips_empty() -> None:
    assert genre_names(("Sci-Fi", "Film-Noir")) == ["sci-fi", "film-noir"]
    assert genre_names("Sci-Fi|Film-Noir") == ["sci-fi", "film-noir"]
    assert genre_names(()) == [] and genre_names("(no genres listed)") == []
    as_text = SCIFI_MOVIES.assign(genres=["|".join(g) for g in SCIFI_MOVIES["genres"]])
    a = ContentScorer().fit(scifi_fit()).item_vectors.toarray()
    b = ContentScorer().fit(toy_fit([(0, 0, 4.0)], 1, 6, movies=as_text)).item_vectors
    assert a.tolist() == b.toarray().tolist()


def test_scifi_only_user_gets_scifi_first_and_romance_last() -> None:
    model = ContentScorer().fit(scifi_fit())
    history = hist([0, 1], [5.0, 5.0])  # rated the two sci-fi movies, nothing else
    ranked = model.recommend(history, k=4)
    assert ranked[0] == 15  # the remaining pure sci-fi movie
    assert ranked[1] == 14  # sci-fi/romance mix
    assert set(ranked[2:].tolist()) == {12, 13}  # pure romance last


def test_content_profile_uses_only_items_above_the_users_own_mean() -> None:
    model = ContentScorer().fit(scifi_fit())
    liked_scifi = model.profile(hist([0, 2], [5.0, 1.0]))  # romance disliked
    scifi_only = model.profile(hist([0], [5.0]))
    assert liked_scifi.tolist() == pytest.approx(scifi_only.tolist())


def test_content_equal_ratings_fall_back_to_all_items_and_empty_is_zero() -> None:
    model = ContentScorer().fit(scifi_fit())
    assert np.linalg.norm(model.profile(hist([0], [3.0]))) == pytest.approx(1.0)
    assert not model.score(History.empty()).any()


def test_content_scores_are_cosine_similarities() -> None:
    model = ContentScorer().fit(scifi_fit())
    scores = model.score(hist([0], [5.0]))
    assert scores.max() <= 1.0 + 1e-9
    assert scores[0] == pytest.approx(1.0)  # an item is identical to itself


def tag_frame(rows: list[tuple[int, int, str, int]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["user_id", "movie_id", "tag", "timestamp"])


def test_tags_change_content_scores_and_no_tags_variant_ignores_them() -> None:
    tags = tag_frame([(1, 10, "  Killer   ROBOTS ", 5), (1, 15, "killer robots", 6)])
    with_tags = ContentScorer().fit(scifi_fit(tags))
    without = ContentScorer(use_tags=False).fit(scifi_fit(tags))
    plain = ContentScorer(use_tags=False).fit(scifi_fit())
    history = hist([0], [5.0])
    assert with_tags.name == "content"
    assert without.name == "content_no_tags"
    # Both sci-fi, but only foxtrot (15) shares alpha's tag: the tag breaks the tie
    assert with_tags.score(history)[5] > with_tags.score(history)[1]
    assert without.score(history).tolist() == plain.score(history).tolist()
    assert without.score(history)[5] == pytest.approx(without.score(history)[1])


def test_content_survives_titles_and_tags_with_no_usable_words() -> None:
    ids = np.arange(10, 13)
    movies = pd.DataFrame(
        {
            "movie_id": ids,
            "title": ["1984", "It", "Up"],
            "title_clean": ["1984", "It", "Up"],  # numbers and stop words only
            "genres": "(no genres listed)",
            "year": np.nan,
        }
    )
    tags = tag_frame([(1, 10, "1984", 5)])  # digits only: no usable word
    model = ContentScorer().fit(toy_fit([(0, 0, 4.0)], 1, 3, movies, tags))
    assert model.item_vectors.shape == (3, 0)  # nothing to learn from
    assert not model.score(hist([0], [5.0])).any()
    assert len(model.recommend(hist([0], [5.0]), k=5)) == 2


def test_content_recommend_excludes_seen_items() -> None:
    model = ContentScorer().fit(scifi_fit())
    got = model.recommend(hist([0, 1], [5.0, 5.0]), k=10)
    assert {10, 11}.isdisjoint(got.tolist())


# ---- Step 8 item-kNN ----------------------------------------------------------------

# Users centre on their own mean, giving item columns A=(1,1,-1), B=(1,1,0) and
# C=(-2,-2,1).
# cos(A,B) = 2/sqrt(6) = 0.8165 and 3 users rated both, so shrinkage 3 multiplies by
# 3/(3+3) = 0.5, giving 0.40825. A-C and B-C are negative, so they are not neighbours.
KNN_TRIPLES = [
    (0, 0, 5.0),
    (0, 1, 5.0),
    (0, 2, 2.0),
    (1, 0, 4.0),
    (1, 1, 4.0),
    (1, 2, 1.0),
    (2, 0, 2.0),
    (2, 1, 3.0),
    (2, 2, 4.0),
]


def test_knn_similarity_matches_hand_calculation() -> None:
    model = ItemKNNScorer(neighbours=5, shrinkage=3).fit(toy_fit(KNN_TRIPLES, 3, 4))
    dense = model.similarity.toarray()
    assert dense[0, 1] == pytest.approx(0.5 * 2 / np.sqrt(6))
    assert dense[1, 0] == pytest.approx(dense[0, 1])
    assert dense[2].tolist() == [0.0, 0.0, 0.0, 0.0]  # C has no positive neighbour
    assert dense[3].tolist() == [0.0, 0.0, 0.0, 0.0]  # D was never rated
    assert np.diag(dense).tolist() == [0.0, 0.0, 0.0, 0.0]


def test_knn_scores_a_user_from_their_own_history_without_refit() -> None:
    model = ItemKNNScorer(neighbours=5, shrinkage=3).fit(toy_fit(KNN_TRIPLES, 3, 4))
    likes_a = hist([0, 2], [5.0, 1.0])  # mean 3: A is +2, C is -2
    dislikes_a = hist([0, 2], [1.0, 5.0])  # mean 3: A is -2, C is +2
    # B's only neighbour is A, so the score is exactly A's centred rating
    assert model.score(likes_a)[1] == pytest.approx(2.0)
    assert model.score(dislikes_a)[1] == pytest.approx(-2.0)
    assert model.recommend(likes_a, k=3).tolist()[0] == 11
    assert model.score(likes_a)[3] == -np.inf  # D: no evidence
    assert model.recommend(likes_a, k=3).tolist() == [11, 13]  # evidence first, no seen


def test_knn_empty_history_has_no_evidence() -> None:
    model = ItemKNNScorer(neighbours=5, shrinkage=3).fit(toy_fit(KNN_TRIPLES, 3, 4))
    assert np.all(model.score(History.empty()) == -np.inf)


def random_fit(seed: int, users: int = 40, items: int = 30) -> FitData:
    rng = np.random.default_rng(seed)
    observed = rng.random((users, items)) < 0.3
    values = rng.integers(1, 11, size=(users, items)) / 2
    dense = np.where(observed, values, 0.0)
    return FitData(
        matrix=sparse.csr_matrix(dense),
        item_map=IdMap.from_ids(np.arange(100, 100 + items)),
        movies=pd.DataFrame(),
        tags=NO_TAGS,
    )


def brute_force_similarity(matrix: sparse.csr_matrix, shrinkage: float) -> np.ndarray:
    dense = matrix.toarray()
    mask = dense > 0
    means = np.array(
        [row[m].mean() if m.any() else 0.0 for row, m in zip(dense, mask, strict=True)]
    )
    centred = np.where(mask, dense - means[:, None], 0.0)
    norms = np.linalg.norm(centred, axis=0)
    shared = mask.T.astype(float) @ mask.astype(float)
    sim = np.zeros((dense.shape[1],) * 2)
    for i in range(dense.shape[1]):
        for j in range(dense.shape[1]):
            if i != j and norms[i] > 0 and norms[j] > 0:
                cosine = centred[:, i] @ centred[:, j] / (norms[i] * norms[j])
                sim[i, j] = cosine * shared[i, j] / (shared[i, j] + shrinkage)
    return sim


@pytest.mark.parametrize("block_items", [1, 7, 500])
def test_knn_blocked_computation_equals_brute_force(block_items: int) -> None:
    data = random_fit(seed=3)
    expected = brute_force_similarity(data.matrix, shrinkage=5)
    model = ItemKNNScorer(neighbours=100, shrinkage=5, block_items=block_items).fit(
        data
    )
    kept = np.where(expected > 0, expected, 0.0)  # only positive similarities are kept
    assert model.similarity.toarray() == pytest.approx(kept, abs=1e-10)


def test_knn_keeps_at_most_n_neighbours_per_item_and_no_dense_square() -> None:
    data = random_fit(seed=4)
    model = ItemKNNScorer(neighbours=3, shrinkage=5, block_items=8).fit(data)
    per_item = np.diff(model.similarity.indptr)
    assert per_item.max() <= 3
    assert sparse.issparse(model.similarity)
    full = brute_force_similarity(data.matrix, shrinkage=5)
    for i in range(30):  # the kept ones are the largest positive similarities
        want = np.sort(full[i][full[i] > 0])[::-1][:3]
        got = np.sort(model.similarity.toarray()[i][model.similarity.toarray()[i] > 0])
        assert got[::-1] == pytest.approx(want)


# ---- Step 9 SVD ---------------------------------------------------------------------

# Two taste groups: users 0-2 like items 0-2 and dislike 3-5; users 3-5 the opposite.
SVD_TRIPLES = (
    [(u, i, 5.0) for u in range(3) for i in range(3) if (u + i) % 3 != 0]
    + [(u, i, 1.0) for u in range(3) for i in range(3, 6) if (u + i) % 3 != 0]
    + [(u, i, 1.0) for u in range(3, 6) for i in range(3) if (u + i) % 3 != 0]
    + [(u, i, 5.0) for u in range(3, 6) for i in range(3, 6) if (u + i) % 3 != 0]
)


def test_svd_fold_in_ranks_the_users_taste_group_first() -> None:
    model = SVDScorer(factors=2).fit(toy_fit(SVD_TRIPLES, 6, 6))
    group_a = hist([0, 3], [5.0, 1.0])  # likes item 0, dislikes item 3
    group_b = hist([0, 3], [1.0, 5.0])
    assert set(model.recommend(group_a, k=2).tolist()) == {11, 12}
    assert set(model.recommend(group_b, k=2).tolist()) == {14, 15}


def test_svd_fold_in_does_not_change_the_model() -> None:
    model = SVDScorer(factors=2).fit(toy_fit(SVD_TRIPLES, 6, 6))
    before = model.item_factors.copy()
    model.score(hist([0, 3], [5.0, 1.0]))
    assert model.item_factors.tolist() == before.tolist()


def test_svd_predictions_stay_in_the_rating_range() -> None:
    model = SVDScorer(factors=2).fit(toy_fit(SVD_TRIPLES, 6, 6))
    history = hist([0, 3], [5.0, 0.5])
    normal = model.predict_ratings(history)
    assert normal.min() >= 0.5 and normal.max() <= 5.0
    model.item_factors = model.item_factors * 50  # force huge raw predictions
    forced = model.predict_ratings(history)
    assert forced.min() == 0.5 and forced.max() == 5.0
    assert model.score(history).max() > 5.0  # ranking scores are not clipped


def test_svd_is_deterministic_for_a_seed_and_handles_empty_history() -> None:
    data = toy_fit(SVD_TRIPLES, 6, 6)
    a = SVDScorer(factors=2, seed=7).fit(data)
    b = SVDScorer(factors=2, seed=7).fit(data)
    assert a.item_factors.tolist() == b.item_factors.tolist()
    assert not a.score(History.empty()).any()
    assert len(a.recommend(History.empty(), k=3)) == 3


def test_svd_clamps_factors_to_what_the_matrix_allows() -> None:
    model = SVDScorer(factors=50).fit(toy_fit(SVD_TRIPLES, 6, 6))
    assert model.item_factors.shape[1] <= 5


# ---- protocol: leakage guards and candidate sets -------------------------------------


def protocol_movies() -> pd.DataFrame:
    ids = np.arange(1, 41)
    return pd.DataFrame(
        {
            "movie_id": ids,
            "title": [f"movie{i} (1999)" for i in ids],
            "title_clean": [f"movie{i}" for i in ids],
            "genres": [("Sci-Fi",) if i % 2 else ("Romance",) for i in ids],
            "year": 1999,
        }
    )


def protocol_ratings() -> pd.DataFrame:
    rows = [
        {
            "user_id": user,
            "movie_id": i + 1,
            "rating": 4.0 if i % 2 == 0 else 3.0,
            "timestamp": BASE + user * 100_000 + i * 10,
        }
        for user in range(1, 11)
        for i in range(30)
    ]
    return pd.DataFrame(rows)


def protocol_tags(users: list[int]) -> pd.DataFrame:
    early, late = users[0], users[1]
    return tag_frame(
        [
            (early, 5, "early tag", BASE + early * 100_000),  # before own cutoff
            (late, 6, "latetag", BASE + late * 100_000 + 29 * 10 + 5),  # after test cut
        ]
    )


def toy_split_and_movies() -> tuple["object", pd.DataFrame]:
    ratings = protocol_ratings()
    movies = protocol_movies()
    split = build_split(ratings, movies, NO_TAGS)
    warm = [u for u in range(1, 11) if not split.users.loc[u, "is_cold_start"]]
    split = build_split(ratings, movies, protocol_tags(warm))
    return split, movies


def test_late_tags_never_reach_the_content_features() -> None:
    split, movies = toy_split_and_movies()
    data = fit_data(split, movies, "validation")  # type: ignore[arg-type]
    assert data.tags["tag"].tolist() == ["early tag"]  # the late tag was dropped
    assert "latetag" not in data.tags["tag"].tolist()
    # Content features built from the allowed tags equal features built from just those
    just_early = FitData(data.matrix, data.item_map, data.movies, data.tags.copy())
    a = ContentScorer().fit(data).item_vectors.toarray()
    b = ContentScorer().fit(just_early).item_vectors.toarray()
    assert a.tolist() == b.tolist()
    # ...and differ from features that wrongly included the late tag
    wrong = FitData(
        data.matrix,
        data.item_map,
        data.movies,
        pd.concat([data.tags, protocol_tags([1, 2]).iloc[[1]]]),
    )
    assert ContentScorer().fit(wrong).item_vectors.toarray().tolist() != a.tolist()


def test_cold_start_users_are_absent_from_every_fit() -> None:
    split, movies = toy_split_and_movies()
    cold = split.users.index[split.users["is_cold_start"]].tolist()
    assert cold  # the toy data has at least one cold-start user
    for target in ("validation", "test"):
        data = fit_data(split, movies, target)  # type: ignore[arg-type]
        rows = split.user_map.to_index(np.array(cold))
        assert data.matrix[rows].nnz == 0
        assert not data.tags["user_id"].isin(cold).any()


def test_validation_fit_has_no_validation_or_test_ratings() -> None:
    split, movies = toy_split_and_movies()
    data = fit_data(split, movies, "validation")  # type: ignore[arg-type]
    train = split.ratings[
        (split.ratings["period"] == "train")
        & ~split.ratings["user_id"].isin(
            split.users.index[split.users["is_cold_start"]]
        )
    ]
    assert data.matrix.nnz == len(train)


def test_fit_data_needs_a_row_for_every_catalogue_movie() -> None:
    split, movies = toy_split_and_movies()
    with pytest.raises(ValueError):
        fit_data(split, movies.iloc[:-5], "validation")  # type: ignore[arg-type]


def fitted_models(data: FitData) -> list[Scorer]:
    return [
        RandomScorer().fit(data),
        PopularityScorer().fit(data),
        BayesianAverageScorer().fit(data),
        ContentScorer().fit(data),
        ContentScorer(use_tags=False).fit(data),
        ItemKNNScorer(neighbours=5, shrinkage=2).fit(data),
        SVDScorer(factors=3).fit(data),
    ]


@pytest.mark.parametrize("target", ["validation", "test"])
def test_every_model_recommends_only_protocol_candidates_for_warm_users(
    target: str,
) -> None:
    split, movies = toy_split_and_movies()
    data = fit_data(split, movies, target)  # type: ignore[arg-type]
    users = evaluation_users(split, target, "warm")  # type: ignore[arg-type]
    assert len(users)
    user = int(users[0])
    candidates = set(candidate_items(split, user, target).tolist())  # type: ignore[arg-type]
    history = user_history(split, user, target)  # type: ignore[arg-type]
    assert set(split.item_map.ids.tolist()) - candidates == set(
        split.item_map.ids[history.items].tolist()
    )
    for model in fitted_models(data):
        got = set(model.recommend(history, k=1000).tolist())
        assert got <= candidates, model.name
        # held-out relevant items stay eligible: nothing hides them
        held = set(heldout_relevant_items(split, user, target).tolist())  # type: ignore[arg-type]
        assert held <= candidates


@pytest.mark.parametrize("size", [0, 3, 5, 10])
def test_cold_start_history_and_candidates_follow_the_revealed_ratings_only(
    size: int,
) -> None:
    split, movies = toy_split_and_movies()
    data = fit_data(split, movies, "validation")
    cold = split.users.index[split.users["is_cold_start"]]
    user = int(cold[0])
    history = user_history(split, user, "validation", size)
    assert len(history) == size
    candidates = set(candidate_items(split, user, "validation", size).tolist())
    assert len(candidates) == 40 - size  # hidden ratings never filter candidates
    for model in fitted_models(data):
        got = set(model.recommend(history, k=1000).tolist())
        assert got <= candidates, model.name
        assert len(got) == len(candidates)  # every candidate can be ranked


def test_user_history_rules_match_the_protocol_guard_rails() -> None:
    split, _ = toy_split_and_movies()
    warm = int(split.users.index[~split.users["is_cold_start"]][0])
    cold = int(split.users.index[split.users["is_cold_start"]][0])
    with pytest.raises(ValueError):
        user_history(split, warm, "validation", 3)  # warm users take no history size
    with pytest.raises(ValueError):
        user_history(split, cold, "validation")  # cold-start users need one
