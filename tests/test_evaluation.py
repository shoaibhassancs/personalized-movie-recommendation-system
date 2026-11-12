"""Step 14 tests: the harness follows the protocol on a small invented dataset.

The dataset is built so the right answer is known in advance. Users 1-40 rate three
"hit" movies early (so the hits are popular in the training data). Users 41-60 rate the
same hits *late*, in their validation period, so for them the relevant held-out movies
are exactly the hits. A popularity ranking must therefore beat random by a mile.

These are mechanics tests: they show the harness applies the protocol and scores
correctly. They are not evidence about any method's quality on real data.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from pmrs.evaluation import (
    BASELINES,
    CLAIM,
    KS,
    METHODS,
    ProtectedTargetError,
    compare,
    evaluate,
    summarize,
    verify_fit_respects_cutoffs,
)
from pmrs.evaluation import harness as harness_module
from pmrs.evaluation.__main__ import main as cli_main
from pmrs.evaluation.harness import RATING_METHODS, all_slices, default_pairs
from pmrs.evaluation.report import format_report, save_result
from pmrs.recommender import fit_data, rank_unseen, user_history
from pmrs.recommender.baselines import PopularityScorer
from pmrs.split import (
    Split,
    build_split,
    candidate_items,
    evaluation_users,
    heldout_relevant_items,
    seen_items,
)

BASE = 1_000_000_000
HITS = [1, 2, 3]
N_BOOT = 100  # small: these tests check mechanics, not interval quality


def toy_movies() -> pd.DataFrame:
    ids = np.arange(1, 201)
    return pd.DataFrame(
        {
            "movie_id": ids,
            "title": [f"movie{i} (1999)" for i in ids],
            "title_clean": [f"movie{i}" for i in ids],
            "genres": [("Sci-Fi",) if i % 2 else ("Romance",) for i in ids],
            "year": 1999,
        }
    )


def toy_ratings() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for user in range(1, 61):
        fillers = [int(m) for m in rng.choice(np.arange(4, 201), 27, replace=False)]
        if user <= 40:  # hits early: they end up in the training data
            movies = [*HITS, *fillers]
            ratings = [5.0] * 3 + [3.0] * 24 + [4.0] * 3
        else:  # hits late: they are this user's validation period
            movies = [*fillers[:24], *HITS, *fillers[24:]]
            ratings = [3.0] * 24 + [5.0] * 3 + [4.0] * 3
        for i, (movie, rating) in enumerate(zip(movies, ratings, strict=True)):
            rows.append(
                {
                    "user_id": user,
                    "movie_id": movie,
                    "rating": rating,
                    "timestamp": BASE + user * 100_000 + i * 10,
                }
            )
    return pd.DataFrame(rows)


def toy_tags() -> pd.DataFrame:
    user = 45  # validation cutoff is position 24 (BASE + user * 100_000 + 240)
    return pd.DataFrame(
        {
            "user_id": [user, user],
            "movie_id": [10, 11],
            "tag": ["early tag", "late tag"],
            "timestamp": [BASE + user * 100_000 + 50, BASE + user * 100_000 + 260],
        }
    )


@pytest.fixture(scope="module")
def toy() -> tuple[Split, pd.DataFrame]:
    movies = toy_movies()
    return build_split(toy_ratings(), movies, toy_tags()), movies


@pytest.fixture(scope="module")
def result(toy: tuple[Split, pd.DataFrame]):  # type: ignore[no-untyped-def]
    split, movies = toy
    return evaluate(split, movies, "validation", n_boot=N_BOOT)


# ---- the test period is protected ---------------------------------------------------


def test_the_test_period_is_refused_unless_explicitly_unlocked(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    split, movies = toy
    with pytest.raises(ProtectedTargetError, match="protected"):
        evaluate(split, movies, "test")
    with pytest.raises(ProtectedTargetError):
        evaluate(split, movies, "test", allow_test=False)
    unlocked = evaluate(split, movies, "test", allow_test=True, n_boot=N_BOOT)
    assert unlocked.target == "test"
    assert unlocked.users_per_slice["warm"] == len(
        evaluation_users(split, "test", "warm")
    )


def test_the_command_line_only_offers_validation() -> None:
    with pytest.raises(SystemExit):
        cli_main(["--target", "test"])


# ---- protocol: candidates and cutoffs -----------------------------------------------


def test_held_out_movies_are_eligible_and_known_movies_are_not(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    split, movies = toy
    fit = fit_data(split, movies, "validation")
    popularity = PopularityScorer().fit(fit)
    user = int(evaluation_users(split, "validation", "warm")[0])
    history = user_history(split, user, "validation")
    full = popularity.recommend(history, k=1000)  # every candidate, ranked
    held = set(heldout_relevant_items(split, user, "validation").tolist())
    known = set(seen_items(split, user, "validation").tolist())
    assert held and known
    assert held <= set(full.tolist())  # (a) held-out items are in the candidate list
    assert not known & set(full.tolist())  # (a) known pre-cutoff items are not
    assert set(full.tolist()) == set(
        candidate_items(split, user, "validation").tolist()
    )
    assert rank_unseen(popularity.score(history), history.items, 5).size == 5


def test_cold_start_candidates_exclude_only_the_revealed_movies(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    split, movies = toy
    fit = fit_data(split, movies, "validation")
    popularity = PopularityScorer().fit(fit)
    user = int(evaluation_users(split, "validation", "cold_start")[0])
    for size in (0, 3, 5, 10):
        history = user_history(split, user, "validation", size)
        full = set(popularity.recommend(history, k=1000).tolist())
        revealed = set(seen_items(split, user, "validation", size).tolist())
        assert len(revealed) == size
        assert not revealed & full
        assert len(full) == 200 - size  # hidden train and held-out stay eligible


def test_every_list_obeys_the_candidate_rule(
    toy: tuple[Split, pd.DataFrame],
    result,  # type: ignore[no-untyped-def]
) -> None:
    split, _ = toy
    checked = 0
    for part in all_slices():
        for method in METHODS:
            lists = result.lists[(part.label, method)]
            users = result.list_users[part.label]
            assert len(lists) == len(users)
            for ranked, user in zip(lists, users, strict=True):
                known = seen_items(split, user, "validation", part.history_size)
                assert len(ranked) == max(KS) == len(set(ranked.tolist()))
                assert not set(ranked.tolist()) & set(known.tolist())
                checked += 1
    assert checked == len(METHODS) * sum(result.users_per_slice.values())


def test_the_fit_respects_every_cutoff_for_both_targets(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    split, _ = toy
    verify_fit_respects_cutoffs(split, "validation")  # (b) no error
    verify_fit_respects_cutoffs(split, "test")


def test_the_cutoff_check_catches_a_late_rating_a_late_tag_and_cold_users(
    toy: tuple[Split, pd.DataFrame], monkeypatch: pytest.MonkeyPatch
) -> None:
    split, _ = toy
    # validation-period and test-period ratings smuggled into the fit
    monkeypatch.setattr(harness_module, "fit_ratings", lambda s, t: s.ratings)
    with pytest.raises(ValueError, match="at or after their cutoff"):
        verify_fit_respects_cutoffs(split, "validation")
    monkeypatch.undo()
    # a tag dated after its author's cutoff
    monkeypatch.setattr(harness_module, "fit_tags", lambda s, t: s.tags)
    with pytest.raises(ValueError, match="tag"):
        verify_fit_respects_cutoffs(split, "validation")
    monkeypatch.undo()
    # a cold-start simulation user's early ratings (all before their own cutoff)
    cold = split.users.index[split.users["is_cold_start"]]
    early = split.ratings[split.ratings["period"] == "train"]
    monkeypatch.setattr(harness_module, "fit_ratings", lambda s, t: early)
    with pytest.raises(ValueError, match="cold-start"):
        verify_fit_respects_cutoffs(split, "validation")
    assert len(cold)


def test_the_late_toy_tag_really_is_excluded_from_the_fit(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    split, movies = toy
    tags = fit_data(split, movies, "validation").tags
    assert tags["tag"].tolist() in (["early tag"], [])  # never "late tag"
    assert "late tag" not in tags["tag"].tolist()


# ---- results ------------------------------------------------------------------------


def test_every_method_and_slice_is_scored_with_finite_metrics(
    toy: tuple[Split, pd.DataFrame],
    result,  # type: ignore[no-untyped-def]
) -> None:
    split, _ = toy
    per_user = result.per_user
    assert set(per_user["method"]) == set(METHODS)
    assert set(per_user["slice"]) == {s.label for s in all_slices()}
    assert set(per_user["k"]) == set(KS)
    for column in ("precision", "recall", "map", "ndcg", "diversity"):
        assert np.isfinite(per_user[column]).all()
        assert per_user[column].between(0, 1).all()
    warm = len(evaluation_users(split, "validation", "warm"))
    cold = len(evaluation_users(split, "validation", "cold_start"))
    assert result.users_per_slice == {
        "warm": warm,
        "cold_start_0": cold,
        "cold_start_3": cold,
        "cold_start_5": cold,
        "cold_start_10": cold,
    }
    assert warm > 0 and cold > 0
    assert len(per_user) == len(METHODS) * len(KS) * (warm + 4 * cold)


def test_popularity_beats_random_where_the_answer_is_known(
    result,  # type: ignore[no-untyped-def]
) -> None:
    ndcg = (
        result.per_user[result.per_user["k"] == 10]
        .groupby(["slice", "method"])["ndcg"]
        .mean()
    )
    for label in ("warm", "cold_start_0", "cold_start_10"):
        assert ndcg[(label, "popularity")] > 0.9  # hits are the 3 most-rated movies
        assert ndcg[(label, "random")] < 0.3
        assert ndcg[(label, "popularity")] > ndcg[(label, "random")] + 0.5


def test_coverage_is_the_share_of_the_catalogue_that_is_ever_shown(
    result,  # type: ignore[no-untyped-def]
) -> None:
    cover = result.coverage
    pop = cover[(cover["slice"] == "warm") & (cover["method"] == "popularity")]
    rnd = cover[(cover["slice"] == "warm") & (cover["method"] == "random")]
    assert pop[pop["k"] == 10]["coverage"].iloc[0] <= 0.1  # the same top movies
    assert rnd[rnd["k"] == 20]["coverage"].iloc[0] > 0.3  # random shows many
    assert cover["coverage"].between(0, 1).all()


def test_summaries_and_paired_comparisons(
    result,  # type: ignore[no-untyped-def]
) -> None:
    summary = summarize(result.per_user, n_boot=N_BOOT)
    assert (summary["ndcg_low"] <= summary["ndcg"]).all()
    assert (summary["ndcg"] <= summary["ndcg_high"]).all()
    warm = summary[(summary["slice"] == "warm") & (summary["k"] == 10)]
    assert set(warm["n_users"]) == {result.users_per_slice["warm"]}
    diffs = compare(result.per_user, n_boot=N_BOOT)
    row = diffs[
        (diffs["slice"] == "warm")
        & (diffs["method"] == "popularity")
        & (diffs["reference"] == "random")
    ]
    assert row.empty  # popularity is itself a baseline: not compared with baselines
    row = diffs[
        (diffs["slice"] == "warm")
        & (diffs["method"] == "bayesian_average")
        & (diffs["reference"] == "random")
    ]
    assert row.empty
    pairs = default_pairs(METHODS)
    assert ("hybrid", "svd") in pairs and ("content", "popularity") in pairs
    assert not any(m in BASELINES for m, _ in pairs)
    forced = compare(result.per_user, pairs=[("popularity", "random")], n_boot=N_BOOT)
    gap = forced[forced["slice"] == "warm"].iloc[0]
    assert gap["difference"] > 0.5 and gap["interval_excludes_zero"]


def test_rating_errors_cover_the_reference_and_rating_predictors(
    result,  # type: ignore[no-untyped-def]
) -> None:
    errors = result.rating_errors
    assert list(errors["method"]) == list(RATING_METHODS)
    assert (errors["rmse"] >= errors["mae"] - 1e-9).all()
    assert (errors["rmse_low"] <= errors["rmse"]).all()
    assert (errors["rmse"] <= errors["rmse_high"]).all()
    assert (errors["n_ratings"] == errors["n_ratings"].iloc[0]).all()


def test_the_same_run_twice_gives_identical_results(
    toy: tuple[Split, pd.DataFrame],
    result,  # type: ignore[no-untyped-def]
) -> None:
    split, movies = toy
    again = evaluate(split, movies, "validation", n_boot=N_BOOT)
    pd.testing.assert_frame_equal(result.per_user, again.per_user)
    pd.testing.assert_frame_equal(result.coverage, again.coverage)
    pd.testing.assert_frame_equal(result.rating_errors, again.rating_errors)


def test_unknown_methods_are_refused(toy: tuple[Split, pd.DataFrame]) -> None:
    split, movies = toy
    with pytest.raises(ValueError, match="unknown methods"):
        evaluate(split, movies, "validation", methods=("magic",))


def test_subset_of_methods_can_be_run(toy: tuple[Split, pd.DataFrame]) -> None:
    split, movies = toy
    small = evaluate(
        split, movies, "validation", methods=("random", "popularity"), n_boot=N_BOOT
    )
    assert set(small.per_user["method"]) == {"random", "popularity"}


# ---- report and saved files ---------------------------------------------------------


def test_report_carries_the_claim_limit_and_labels_the_stage(
    result,
    tmp_path: Path,  # type: ignore[no-untyped-def]
) -> None:
    summary = summarize(result.per_user, n_boot=N_BOOT)
    diffs = compare(result.per_user, n_boot=N_BOOT)
    report = format_report(result, summary, diffs)
    assert CLAIM in report
    assert "VALIDATION period" in report and "test period was not read" in report
    assert "cold-start SIMULATION" in report
    assert "NDCG@10" in report and "[95% CI]" in report
    assert "popularity" in report and "random" in report
    folder = save_result(result, summary, diffs, report, tmp_path)
    assert {p.name for p in folder.iterdir()} == {
        "per_user.csv",
        "summary.csv",
        "comparisons.csv",
        "coverage.csv",
        "rating_errors.csv",
        "report.txt",
        "run.json",
    }
    info = json.loads((folder / "run.json").read_text())
    assert info["claim"] == CLAIM and info["target"] == "validation"
    assert info["users_per_slice"] == result.users_per_slice
    assert len(pd.read_csv(folder / "per_user.csv")) == len(result.per_user)


def test_validation_results_do_not_depend_on_anything_in_the_test_period(
    toy: tuple[Split, pd.DataFrame],
    result,  # type: ignore[no-untyped-def]
) -> None:
    """Rewrite every test-period rating value; validation numbers must not move.

    Only the *number* of a user's test ratings matters (it decides eligibility, fixed
    at Step 5); their values and the movies are never read in validation mode.
    """
    split, movies = toy
    altered = split.ratings.copy()
    in_test = altered["period"] == "test"
    assert in_test.any()
    altered.loc[in_test, "rating"] = 0.5  # was 4.0: now a different relevance story
    changed = build_split(altered.drop(columns="period"), movies, toy_tags())
    assert (changed.users["n_test"] == split.users["n_test"]).all()
    again = evaluate(changed, movies, "validation", n_boot=N_BOOT)
    pd.testing.assert_frame_equal(result.per_user, again.per_user)
    pd.testing.assert_frame_equal(result.rating_errors, again.rating_errors)
