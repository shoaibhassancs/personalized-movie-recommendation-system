"""Tests for Steps 10-12: hybrid ladder, explanations, candidates, artifacts, CLI.

These prove mechanics on a small invented catalogue (orderings, the ladder rungs,
seen-movie exclusion, sentences that only mention real evidence, save/load round trips).
They say nothing about recommendation quality: that is measured in Phase 3.
"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest
from scipy import sparse

from pmrs.recommender import FitData, History
from pmrs.recommender.artifact import (
    METADATA_FILE,
    MODEL_FILE,
    ArtifactError,
    data_fingerprint,
    load_recommender,
    read_metadata,
    save_recommender,
    sha256_of,
)
from pmrs.recommender.cli import main as cli_main
from pmrs.recommender.cli import parse_genres, parse_ratings
from pmrs.recommender.explain import Catalog, Evidence, render
from pmrs.recommender.hybrid import (
    HybridConfig,
    blend,
    genre_match,
    min_max_scale,
)
from pmrs.recommender.recommender import (
    STRATEGIES,
    TRUSTED_ARTIFACT_WARNING,
    Recommender,
    UserProfile,
    profile_from_history,
)
from pmrs.split import IdMap

IDS = np.arange(10, 24)  # 14 movies: 10-16 sci-fi, 17-23 romance
SCIFI = [int(i) for i in IDS[:7]]
ROMANCE = [int(i) for i in IDS[7:]]
WORDS = (
    "alpha bravo charlie delta echo foxtrot golf hotel india juliet kilo lima mike"
    " november"
).split()
NO_TAGS = pd.DataFrame(
    {
        "user_id": pd.Series(dtype="int64"),
        "movie_id": pd.Series(dtype="int64"),
        "tag": pd.Series(dtype="str"),
        "timestamp": pd.Series(dtype="int64"),
    }
)


def toy_fit() -> FitData:
    """12 taste-split users (6 love sci-fi, 6 love romance) plus 3 light users."""
    rows, cols, vals = [], [], []
    for user in range(12):
        skipped = {user % 14, (user + 1) % 14}
        for item in range(14):
            if item in skipped:
                continue
            likes = (item < 7) == (user < 6)
            rows.append(user)
            cols.append(item)
            vals.append((5.0 if (item + user) % 2 else 4.0) if likes else 1.0)
    for user in (12, 13, 14):  # light users make movies 0 and 1 more popular
        for item in (0, 1):
            rows.append(user)
            cols.append(item)
            vals.append(4.0)
    matrix = sparse.coo_matrix((vals, (rows, cols)), shape=(15, 14)).tocsr()
    genres = [
        ("Sci-Fi", "Adventure") if i in (1, 3) else ("Sci-Fi",) if i < 7 else
        ("Romance", "Drama") if i in (8, 10) else ("Romance",)
        for i in range(14)
    ]  # fmt: skip
    movies = pd.DataFrame(
        {
            "movie_id": IDS,
            "title": [f"{WORDS[i].title()} Story ({2000 + i})" for i in range(14)],
            "title_clean": [f"{WORDS[i]} story" for i in range(14)],
            "genres": genres,
            "year": 2000 + np.arange(14),
        }
    )
    return FitData(matrix, IdMap.from_ids(IDS), movies, NO_TAGS)


@pytest.fixture(scope="module")
def rec() -> Recommender:
    return Recommender.fit(toy_fit(), target="validation", data_hash="toy-hash")


def profile(
    ids: list[int], rating: float = 5.0, **kwargs: tuple[str, ...]
) -> UserProfile:
    return UserProfile({i: rating for i in ids}, **kwargs)


# ---- the ladder: which rung, which weights ------------------------------------------


@pytest.mark.parametrize(
    ("count", "branch"),
    [
        (0, "no_ratings"),
        (1, "few_ratings"),
        (9, "few_ratings"),
        (10, "many_ratings"),
        (500, "many_ratings"),
    ],
)
def test_ladder_rung_boundaries(count: int, branch: str) -> None:
    assert HybridConfig().branch(count) == branch


def test_ladder_boundary_follows_few_max_and_rejects_negative_counts() -> None:
    config = HybridConfig(few_max=3)
    assert [config.branch(n) for n in (0, 3, 4)] == [
        "no_ratings",
        "few_ratings",
        "many_ratings",
    ]
    with pytest.raises(ValueError):
        config.branch(-1)


def test_default_weights_sum_to_one_and_lean_on_content_when_few() -> None:
    config = HybridConfig()
    few, many = config.weights_for("few_ratings"), config.weights_for("many_ratings")
    assert sum(few.values()) == pytest.approx(1.0)
    assert sum(many.values()) == pytest.approx(1.0)
    assert few["content"] > many["content"]
    assert few["content"] == max(few.values())
    with pytest.raises(ValueError):
        config.weights_for("no_ratings")  # that rung does not blend methods


def test_config_rejects_bad_weights() -> None:
    with pytest.raises(ValueError):
        HybridConfig(few_weights={"content": 0.5, "svd": 0.4})  # sums to 0.9
    with pytest.raises(ValueError):
        HybridConfig(many_weights={"content": 1.5, "svd": -0.5})  # negative
    with pytest.raises(ValueError):
        HybridConfig(few_weights={"magic": 1.0})  # unknown method
    with pytest.raises(ValueError):
        HybridConfig(genre_weight=0.9, popularity_weight=0.9)
    with pytest.raises(ValueError):
        HybridConfig(few_max=0)


# ---- blending -----------------------------------------------------------------------


def test_min_max_scale_uses_candidates_only_and_zeroes_missing_evidence() -> None:
    scores = np.array([100.0, 2.0, 4.0, -np.inf, 6.0])
    candidates = np.array(
        [1, 2, 3, 4]
    )  # item 0 is seen: its 100 must not stretch scale
    scaled = min_max_scale(scores, candidates)
    assert scaled.tolist() == [0.0, 0.0, 0.5, 0.0, 1.0]


def test_min_max_scale_all_equal_or_no_evidence_gives_zeros() -> None:
    assert min_max_scale(np.array([3.0, 3.0, 3.0]), np.array([0, 1, 2])).sum() == 0
    assert min_max_scale(np.full(3, -np.inf), np.array([0, 1, 2])).sum() == 0
    assert min_max_scale(np.array([1.0, 2.0]), np.array([], dtype=np.intp)).sum() == 0


def test_blend_is_the_hand_computed_weighted_sum() -> None:
    raw = {
        "content": np.array([0.0, 1.0, 2.0, 4.0]),
        "item_knn": np.array([0.0, 0.0, 0.0, 0.0]),
        "svd": np.array([4.0, 2.0, 0.0, 0.0]),
        "popularity": np.array([10.0, 20.0, 30.0, 50.0]),
    }
    candidates = np.array([1, 2, 3])  # item 0 seen
    weights = {"content": 0.5, "item_knn": 0.1, "svd": 0.2, "popularity": 0.2}
    total, scaled = blend(raw, weights, candidates)
    # scaled over candidates 1,2,3 only:
    #   content (0, 1/3, 1); svd (1, 0, 0); popularity (20,30,50) -> (0, 1/3, 1)
    expected = 0.5 * np.array([0, 0, 1 / 3, 1]) + 0.2 * np.array([0, 1, 0, 0])
    expected += 0.2 * np.array([0, 0, 1 / 3, 1])
    assert total == pytest.approx(expected)
    assert scaled["item_knn"].sum() == 0  # constant scores separate nothing
    assert total.min() >= 0 and total.max() <= 1 + 1e-12


def test_genre_match_is_share_of_chosen_genres() -> None:
    sets = [
        frozenset({"sci-fi"}),
        frozenset({"sci-fi", "drama"}),
        frozenset({"romance"}),
    ]
    assert genre_match(sets, ["sci-fi", "drama"]).tolist() == [0.5, 1.0, 0.0]
    assert genre_match(sets, []).tolist() == [0.0, 0.0, 0.0]


# ---- explanation text comes only from evidence --------------------------------------


def title(movie_id: int) -> str:
    return f"T{movie_id}"


def test_render_each_kind_mentions_only_what_the_evidence_holds() -> None:
    content = Evidence("content", (11,), (5.0,), ("sci-fi",), ("space",), 0.8)
    text = render(content, title)
    assert "'T11' (5)" in text and "sci-fi" in text and "space" in text
    plain = render(Evidence("content", (11,), (4.5,)), title)
    assert "'T11' (4.5)" in plain and "genres" not in plain
    near = render(Evidence("neighbours", (11, 12), (5.0, 4.0), count=2), title)
    assert "'T11' (5) and 'T12' (4)" in near
    assert "which you rated" in near
    assert "statistical match" in render(Evidence("taste_pattern"), title)
    assert "'T11'" in render(Evidence("taste_pattern", (11,), (5.0,)), title)
    assert "not based on your taste" in render(Evidence("popularity", count=7), title)
    assert "7 people" in render(Evidence("popularity", count=7), title)
    overall = render(Evidence("overall_rating", value=4.26, count=30), title)
    assert "4.3" in overall and "30 ratings" in overall
    genre = render(
        Evidence("genre_popularity", genres=("Sci-Fi", "Drama"), count=9), title
    )
    assert "Sci-Fi and Drama" in genre and "not based on any ratings from you" in genre
    assert "not based on your taste" in render(Evidence("random"), title)
    assert "not a recommendation" in render(Evidence("no_evidence"), title)


def test_catalog_lookups_and_validation() -> None:
    catalog = Catalog(np.array([5, 9]), ["A", "B"], [("Sci-Fi",), ("Drama", "War")])
    assert catalog.title_of(9) == "B"
    assert catalog.genre_set(1) == {"drama", "war"}
    with pytest.raises(ValueError):
        Catalog(np.array([5]), ["A", "B"], [("x",)])


def test_every_evidence_movie_is_one_the_user_rated(rec: Recommender) -> None:
    rated = [10, 11, 12, 13, 17, 18, 19, 20, 21, 22]
    user = UserProfile({m: (5.0 if m < 14 else 1.0) for m in rated})
    for strategy in STRATEGIES:
        for item in rec.recommend(user, strategy, k=14).items:
            assert set(item.evidence.movies) <= set(rated), strategy
            assert len(item.evidence.movies) == len(item.evidence.ratings)
            for movie_id, rating in zip(
                item.evidence.movies, item.evidence.ratings, strict=True
            ):
                assert rating == user.ratings[movie_id]  # the user's real rating
            assert item.explanation  # always some sentence
            assert item.evidence.kind in {
                "content", "neighbours", "taste_pattern", "popularity",
                "overall_rating", "random", "no_evidence",
            }  # fmt: skip


def test_content_explanation_names_a_rated_movie_and_a_shared_genre(
    rec: Recommender,
) -> None:
    result = rec.recommend(profile([10, 11, 12]), "content", k=3)
    for item in result.items:
        assert item.evidence.kind == "content"
        assert "Sci-Fi" in item.explanation or "sci-fi" in item.explanation
        assert item.evidence.movies[0] in (10, 11, 12)
        assert rec.catalog.title_of(item.evidence.movies[0]) in item.explanation


def test_no_evidence_is_said_plainly_not_invented(rec: Recommender) -> None:
    result = rec.recommend(UserProfile(), "item_knn", k=3)
    assert all(item.score is None for item in result.items)
    assert all(item.evidence.kind == "no_evidence" for item in result.items)
    assert all("not a recommendation" in item.explanation for item in result.items)


# ---- hybrid ladder behaviour on a real fitted Recommender ---------------------------


def test_zero_ratings_without_genres_is_pure_popularity(rec: Recommender) -> None:
    result = rec.recommend(UserProfile(), "hybrid", k=14)
    assert result.branch == "no_ratings"
    assert result.score_kind == "rating count"
    assert any("popularity alone" in note for note in result.notes)
    counts = [item.score for item in result.items]
    assert counts == sorted(counts, reverse=True)  # high to low
    fit_counts = np.diff(toy_fit().matrix.tocsc().indptr)
    assert counts[0] == fit_counts.max()
    assert all(item.evidence.kind == "popularity" for item in result.items)


def test_zero_ratings_with_genres_prefers_those_genres_and_says_so(
    rec: Recommender,
) -> None:
    result = rec.recommend(UserProfile(genres=("romance",)), "hybrid", k=14)
    assert result.branch == "no_ratings"
    assert result.score_kind == "genre and popularity blend (0 to 1)"
    assert set(result.movie_ids[:7]) == set(ROMANCE)  # all romance rank above sci-fi
    for item in result.items:
        assert 0.0 <= (item.score or 0.0) <= 1.0
        if item.movie_id in ROMANCE:
            assert "Romance" in item.explanation
            assert "not based on any ratings from you" in item.explanation
        else:  # never claims a genre match that did not happen
            assert "genres you chose" not in item.explanation
            assert item.evidence.kind == "popularity"


def test_genre_names_are_case_insensitive_and_unknown_ones_are_refused(
    rec: Recommender,
) -> None:
    lower = rec.recommend(UserProfile(genres=("sci-fi",)), "hybrid", k=5)
    upper = rec.recommend(UserProfile(genres=(" SCI-FI ",)), "hybrid", k=5)
    assert lower.movie_ids == upper.movie_ids
    with pytest.raises(ValueError, match="unknown genres"):
        rec.recommend(UserProfile(genres=("western",)), "hybrid")


def test_one_to_nine_ratings_use_the_content_heavy_rung(rec: Recommender) -> None:
    result = rec.recommend(profile([10, 11, 12]), "hybrid", k=14)
    assert result.branch == "few_ratings"
    assert result.score_kind == "hybrid blend (0 to 1)"
    assert set(result.movie_ids[:4]) == {13, 14, 15, 16}  # unrated sci-fi first
    assert all(0.0 <= (item.score or 0.0) <= 1.0 for item in result.items)
    scores = [item.score or 0.0 for item in result.items]
    assert scores == sorted(scores, reverse=True)


def test_ten_or_more_ratings_use_the_balanced_rung(rec: Recommender) -> None:
    nine = rec.recommend(profile(SCIFI + ROMANCE[:2]), "hybrid", k=14)
    ten = rec.recommend(profile(SCIFI + ROMANCE[:3]), "hybrid", k=14)
    assert nine.branch == "few_ratings"
    assert ten.branch == "many_ratings"


def test_hybrid_with_all_weight_on_one_method_equals_that_method() -> None:
    only_content = {"content": 1.0, "item_knn": 0.0, "svd": 0.0, "popularity": 0.0}
    config = HybridConfig(many_weights=only_content)
    fitted = Recommender.fit(toy_fit(), target="validation", config=config)
    user = profile(SCIFI[:3] + ROMANCE[:7])
    assert fitted.recommend(user, "hybrid", k=14).movie_ids == (
        fitted.recommend(user, "content", k=14).movie_ids
    )


def test_favourite_genres_are_ignored_once_there_are_ratings(rec: Recommender) -> None:
    with_genres = rec.recommend(profile([10, 11], genres=("romance",)), "hybrid", k=5)
    without = rec.recommend(profile([10, 11]), "hybrid", k=5)
    assert with_genres.movie_ids == without.movie_ids
    assert with_genres.notes and not without.notes


def test_recommendations_are_deterministic(rec: Recommender) -> None:
    user = profile([10, 12, 17])
    for strategy in STRATEGIES:
        first = rec.recommend(user, strategy, k=6)
        second = rec.recommend(user, strategy, k=6)
        assert first.movie_ids == second.movie_ids, strategy
        assert [i.explanation for i in first.items] == [
            i.explanation for i in second.items
        ]


# ---- candidate handling (D-023) -----------------------------------------------------


@pytest.mark.parametrize("strategy", STRATEGIES)
def test_a_rated_movie_is_never_recommended(rec: Recommender, strategy: str) -> None:
    for rated in ([], [10], SCIFI[:3], SCIFI + ROMANCE[:3]):
        result = rec.recommend(profile(rated), strategy, k=100)
        assert not set(result.movie_ids) & set(rated)
        # everything not rated stays eligible: nothing else is filtered out
        assert len(result.items) == 14 - len(rated)


def test_zero_revealed_ratings_excludes_nothing(rec: Recommender) -> None:
    assert len(rec.recommend(UserProfile(), "hybrid", k=100).items) == 14


def test_profile_from_history_round_trips_protocol_histories(rec: Recommender) -> None:
    history = History(np.array([0, 3, 9]), np.array([5.0, 4.0, 1.0]))
    user = profile_from_history(history, rec.item_map, ("sci-fi",))
    assert user.ratings == {10: 5.0, 13: 4.0, 19: 1.0}
    assert rec.history(user).items.tolist() == [0, 3, 9]


def test_bad_input_is_refused(rec: Recommender) -> None:
    with pytest.raises(ValueError, match="not in the catalogue"):
        rec.recommend(UserProfile({999: 4.0}))
    with pytest.raises(ValueError, match="ratings must be between"):
        rec.recommend(UserProfile({10: 6.0}))
    with pytest.raises(ValueError, match="ratings must be between"):
        rec.recommend(UserProfile({10: float("nan")}))
    with pytest.raises(ValueError, match="unknown strategy"):
        rec.recommend(UserProfile(), "magic")
    with pytest.raises(ValueError, match="k must not be negative"):
        rec.recommend(UserProfile(), k=-1)
    assert rec.recommend(UserProfile(), k=0).items == ()


# ---- artifacts: save, load, damage --------------------------------------------------


def test_save_then_load_gives_identical_recommendations(
    rec: Recommender, tmp_path: Path
) -> None:
    folder = save_recommender(rec, tmp_path / "art")
    assert {p.name for p in folder.iterdir()} == {MODEL_FILE, METADATA_FILE}
    loaded = load_recommender(folder)
    for user in (
        UserProfile(),
        UserProfile(genres=("romance",)),
        profile([10, 11, 12]),
        profile(SCIFI + ROMANCE[:3]),
    ):
        for strategy in STRATEGIES:
            before = rec.recommend(user, strategy, k=14)
            after = loaded.recommend(user, strategy, k=14)
            assert before.movie_ids == after.movie_ids, strategy
            assert [i.explanation for i in before.items] == [
                i.explanation for i in after.items
            ]
            assert [i.score for i in before.items] == [i.score for i in after.items]


def test_metadata_records_version_information_and_the_warning(
    rec: Recommender, tmp_path: Path
) -> None:
    folder = save_recommender(rec, tmp_path / "art")
    record = read_metadata(folder)
    assert record["schema_version"] == 1
    assert record["target"] == "validation"
    assert record["seed"] == 42
    assert record["data_hash"] == "toy-hash"
    assert record["n_items"] == 14 and record["n_fit_users"] == 15
    assert record["n_fit_ratings"] == int(toy_fit().matrix.nnz)
    assert {"numpy", "pandas", "scipy", "scikit-learn"} <= set(record["libraries"])
    assert record["config"]["few_max"] == 9
    assert record["model_params"]["item_knn"]["neighbours"] == 50
    assert record["model_sha256"] == sha256_of(folder / MODEL_FILE)
    assert record["model_bytes"] == (folder / MODEL_FILE).stat().st_size
    assert record["warning"] == TRUSTED_ARTIFACT_WARNING
    assert "pickle" in TRUSTED_ARTIFACT_WARNING


def test_saving_never_overwrites_an_existing_artifact(
    rec: Recommender, tmp_path: Path
) -> None:
    folder = save_recommender(rec, tmp_path / "art")
    before = sha256_of(folder / MODEL_FILE)
    with pytest.raises(ArtifactError, match="never overwritten"):
        save_recommender(rec, folder)
    assert sha256_of(folder / MODEL_FILE) == before


def test_a_changed_model_byte_is_caught_before_unpickling(
    rec: Recommender, tmp_path: Path
) -> None:
    folder = save_recommender(rec, tmp_path / "art")
    path = folder / MODEL_FILE
    data = bytearray(path.read_bytes())
    data[len(data) // 2] ^= 0xFF  # same size, one byte different
    path.write_bytes(bytes(data))
    with pytest.raises(ArtifactError, match="SHA-256"):
        load_recommender(folder)


def test_a_truncated_model_file_is_caught(rec: Recommender, tmp_path: Path) -> None:
    folder = save_recommender(rec, tmp_path / "art")
    path = folder / MODEL_FILE
    path.write_bytes(path.read_bytes()[:-10])
    with pytest.raises(ArtifactError, match="size"):
        load_recommender(folder)


def test_missing_files_and_wrong_schema_are_refused(
    rec: Recommender, tmp_path: Path
) -> None:
    with pytest.raises(ArtifactError, match="no metadata.json"):
        load_recommender(tmp_path / "nothing")
    folder = save_recommender(rec, tmp_path / "art")
    record = read_metadata(folder)
    (folder / METADATA_FILE).write_text(json.dumps({**record, "schema_version": 99}))
    with pytest.raises(ArtifactError, match="schema"):
        load_recommender(folder)
    (folder / METADATA_FILE).write_text(json.dumps(record))
    (folder / MODEL_FILE).unlink()
    with pytest.raises(ArtifactError, match="missing model file"):
        load_recommender(folder)


def test_metadata_that_disagrees_with_the_model_is_refused(
    rec: Recommender, tmp_path: Path
) -> None:
    folder = save_recommender(rec, tmp_path / "art")
    record = read_metadata(folder)
    (folder / METADATA_FILE).write_text(json.dumps({**record, "data_hash": "other"}))
    with pytest.raises(ArtifactError, match="does not match"):
        load_recommender(folder)


def test_a_model_file_that_is_not_a_recommender_is_refused(tmp_path: Path) -> None:
    folder = tmp_path / "art"
    folder.mkdir()
    path = folder / MODEL_FILE
    joblib.dump({"not": "a recommender"}, path)
    record = {
        "schema_version": 1,
        "model_file": MODEL_FILE,
        "model_bytes": path.stat().st_size,
        "model_sha256": sha256_of(path),
    }
    (folder / METADATA_FILE).write_text(json.dumps(record))
    with pytest.warns(UserWarning, match="library versions differ"):
        with pytest.raises(ArtifactError, match="does not hold a Recommender"):
            load_recommender(folder)


def test_data_fingerprint_changes_when_any_source_file_changes(tmp_path: Path) -> None:
    for name in ("ratings.csv", "movies.csv", "tags.csv"):
        (tmp_path / name).write_text(f"{name}\n1\n")
    first = data_fingerprint(tmp_path)
    assert first == data_fingerprint(tmp_path)
    (tmp_path / "tags.csv").write_text("tags.csv\n2\n")
    assert data_fingerprint(tmp_path) != first


# ---- command line -------------------------------------------------------------------


def test_cli_parsing_helpers() -> None:
    assert parse_ratings("318:5, 296:4.5") == {318: 5.0, 296: 4.5}
    assert parse_ratings("") == {}
    assert parse_genres("Sci-Fi, Drama,,") == ("Sci-Fi", "Drama")
    with pytest.raises(ValueError):
        parse_ratings("318")
    with pytest.raises(ValueError, match="twice"):
        parse_ratings("1:3,1:4")


def test_cli_recommend_prints_the_warning_and_the_list(
    rec: Recommender, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = save_recommender(rec, tmp_path / "art")
    code = cli_main(
        ["recommend", "--artifact", str(folder), "--ratings", "10:5,11:5", "-k", "3"]
    )
    out = capsys.readouterr()
    assert code == 0
    assert "pickle" in out.err  # the trusted-artifact warning is always shown
    assert "ladder rung: few_ratings" in out.out
    assert out.out.count("Story") >= 3


def test_cli_reports_errors_without_a_traceback(
    rec: Recommender, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    folder = save_recommender(rec, tmp_path / "art")
    assert (
        cli_main(["recommend", "--artifact", str(folder), "--genres", "western"]) == 1
    )
    assert "unknown genres" in capsys.readouterr().err
    assert cli_main(["recommend", "--artifact", str(tmp_path / "missing")]) == 1


def test_knn_evidence_names_only_the_users_own_rated_neighbours(
    rec: Recommender,
) -> None:
    user = profile(SCIFI[:3] + ROMANCE[:3])
    seen = {rec.item_map.to_index(np.array([m]))[0] for m in user.ratings}
    history = rec.history(user)
    found = 0
    for position in range(14):
        if position in seen:
            continue
        evidence = rec.scorers["item_knn"].evidence(history, position)
        if evidence.kind == "neighbours":
            found += 1
            assert set(evidence.movies) <= set(user.ratings)
            assert 1 <= len(evidence.movies) <= 3
            assert evidence.count >= len(evidence.movies)  # count = all such neighbours
    assert found > 0  # the toy data does give some movies neighbour evidence


def test_render_names_at_most_five_shared_tags() -> None:
    tags = tuple(f"tag{n}" for n in range(8))
    text = render(Evidence("content", (11,), (5.0,), ("drama",), tags), title)
    assert "tag4" in text and "tag5" not in text
    assert "drama" in text


# ---- content wording: "above your average" is stated, never implied -----------------


def test_render_content_says_the_movie_beat_the_users_own_average() -> None:
    evidence = Evidence("content", (11,), (2.5,), ("drama",), average=1.5)
    text = render(evidence, title)
    assert "'T11' (2.5)" in text
    assert "above your own average of 1.50" in text
    assert "shares the genres drama" in text
    bare = render(Evidence("content", (11,), (2.5,), average=1.5), title)
    assert "above your own average of 1.50" in bare and "genres" not in bare


def test_render_content_fallback_does_not_imply_the_user_liked_it() -> None:
    evidence = Evidence(
        "content", (11,), (3.0,), ("drama",), average=3.0, above_average=False
    )
    text = render(evidence, title)
    assert "Because you rated" not in text  # that phrasing implies a liked movie
    assert "which you rated" in text and "'T11' (3)" in text
    assert "None of your ratings is above your own average of 3.00" in text
    assert "which is above your own average" not in text  # the "liked" phrasing


def test_a_low_rating_is_explained_by_the_users_even_lower_average(
    rec: Recommender,
) -> None:
    # 2.5 is the only rating above this user's mean (1.50), so it is the "liked" one
    user = UserProfile({10: 2.5, 11: 1.0, 12: 1.0})
    items = rec.recommend(user, "content", k=5).items
    assert items
    for item in items:
        assert item.evidence.kind == "content"
        assert item.evidence.movies == (10,) and item.evidence.ratings == (2.5,)
        assert item.evidence.average == pytest.approx(1.5)
        assert item.evidence.above_average
        assert "(2.5)" in item.explanation
        assert "above your own average of 1.50" in item.explanation


def test_content_evidence_average_is_the_users_real_mean_and_is_beaten(
    rec: Recommender,
) -> None:
    user = UserProfile({10: 5.0, 11: 4.0, 12: 1.0, 17: 3.0})
    mean = sum(user.ratings.values()) / 4
    for strategy in ("content", "hybrid"):
        for item in rec.recommend(user, strategy, k=14).items:
            if item.evidence.kind != "content":
                continue
            assert item.evidence.average == pytest.approx(mean)
            assert item.evidence.above_average
            assert item.evidence.ratings[0] > mean  # the cited rating beats the mean
            assert f"{mean:.2f}" in item.explanation


def test_when_no_rating_is_above_average_the_sentence_is_neutral(
    rec: Recommender,
) -> None:
    user = UserProfile({10: 3.0, 11: 3.0})  # all equal: nothing is above the mean
    items = rec.recommend(user, "content", k=5).items
    assert items
    for item in items:
        assert item.evidence.kind == "content"
        assert not item.evidence.above_average
        assert "Because you rated" not in item.explanation
        assert "None of your ratings is above your own average of 3.00" in (
            item.explanation
        )


def test_a_mean_that_rounds_up_to_the_rating_is_shown_with_more_digits() -> None:
    # real case: a 2.5 cited against a mean of 2.4967, which prints as "2.50"
    evidence = Evidence("content", (11,), (2.5,), ("drama",), average=2.4967)
    text = render(evidence, title)
    assert "'T11' (2.5)" in text
    assert "above your own average of 2.497" in text
    assert "2.50" not in text  # would read as "2.5 is above 2.50"
    clear = render(Evidence("content", (11,), (4.0,), average=3.4), title)
    assert "average of 3.40" in clear  # normal cases keep two places
