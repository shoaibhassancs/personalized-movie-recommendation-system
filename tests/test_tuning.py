"""Step 15 tests: tuning mechanics, the selection rule, and the test-period guard.

They show the tuning code follows the approved rules on a small invented dataset.
They say nothing about which settings are good on the real data.
"""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pytest

from pmrs.evaluation import evaluate
from pmrs.evaluation import tuning as tuning_module
from pmrs.evaluation.tuning import (
    KNN_GRID,
    Context,
    SliceScores,
    Trial,
    analyse,
    canonical_hash,
    choose,
    config_payload,
    load_frozen,
    log_to_mlflow,
    run_stages,
)
from pmrs.recommender import fit_data
from pmrs.recommender.baselines import PopularityScorer
from pmrs.recommender.hybrid import HybridConfig
from pmrs.recommender.knn import ItemKNNScorer
from pmrs.recommender.recommender import Recommender
from pmrs.recommender.settings import ModelSettings
from pmrs.split import Split, build_split
from test_evaluation import toy_movies, toy_ratings, toy_tags

N_BOOT = 100


@pytest.fixture(scope="module")
def toy() -> tuple[Split, pd.DataFrame]:
    movies = toy_movies()
    return build_split(toy_ratings(), movies, toy_tags()), movies


# ---- item-kNN minimum support --------------------------------------------------------


def test_min_support_ranks_thin_movies_last_but_keeps_them_eligible(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    split, movies = toy
    fit = fit_data(split, movies, "validation")
    plain = ItemKNNScorer().fit(fit)
    strict = ItemKNNScorer(min_support=30).fit(fit)
    raters = np.diff(fit.matrix.tocsc().indptr)
    assert (plain.support == raters).all()  # support = fit users who rated the movie
    thin = raters < 30
    assert thin.any() and (~thin).any()
    from pmrs.recommender import user_history

    history = user_history(split, 1, "validation")
    before, after = plain.score(history), strict.score(history)
    assert np.isneginf(after[thin]).all()  # thin movies have no usable score
    assert np.allclose(after[~thin], before[~thin])  # nothing else changes
    # not a candidate filter: the same movies are listed, thin ones only come later
    everything = len(fit.item_map) - len(history)
    assert set(plain.recommend(history, k=everything).tolist()) == set(
        strict.recommend(history, k=everything).tolist()
    )


def test_min_support_zero_is_the_original_behaviour(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    split, movies = toy
    fit = fit_data(split, movies, "validation")
    from pmrs.recommender import user_history

    history = user_history(split, 1, "validation")
    assert np.array_equal(
        ItemKNNScorer().fit(fit).score(history),
        ItemKNNScorer(min_support=0).fit(fit).score(history),
    )
    with pytest.raises(ValueError):
        ItemKNNScorer(min_support=-1)


def test_model_settings_reach_the_models_and_defaults_change_nothing(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    split, movies = toy
    fit = fit_data(split, movies, "validation")
    rec = Recommender.fit(
        fit,
        target="validation",
        settings=ModelSettings(neighbours=20, shrinkage=5.0, min_support=7, factors=9),
    )
    params = rec.metadata.model_params
    assert params["item_knn"] == {
        "neighbours": 20,
        "shrinkage": 5.0,
        "min_support": 7,
    }
    assert params["svd"]["factors"] == 9
    default = evaluate(split, movies, "validation", n_boot=N_BOOT)
    explicit = evaluate(
        split,
        movies,
        "validation",
        n_boot=N_BOOT,
        settings=ModelSettings(),
        config=HybridConfig(),
    )
    pd.testing.assert_frame_equal(default.per_user, explicit.per_user)


# ---- the selection rule --------------------------------------------------------------


def make_trial(name: str, values: np.ndarray) -> Trial:
    zeros = np.zeros_like(values)
    scores = {"warm": SliceScores(values, zeros, zeros, zeros, 0.1)}
    return Trial("stage", "m", name, {}, ("warm",), scores)


def run_choice(reference: np.ndarray, others: dict[str, np.ndarray]) -> list[Trial]:
    trials = [make_trial("default", reference)]
    trials += [make_trial(name, v) for name, v in others.items()]
    popularity = make_trial("popularity", reference)
    analyse(trials, trials[0], popularity, N_BOOT)
    choose(trials, trials[0])
    return trials


def test_a_clear_paired_gain_is_adopted() -> None:
    base = np.random.default_rng(0).random(120) * 0.2
    trials = run_choice(base, {"better": base + 0.05, "worse": base - 0.01})
    assert trials[1].status.startswith("adopted")
    assert trials[0].status == "not adopted"
    assert trials[2].status == "not adopted"


def test_a_noisy_best_mean_is_inconclusive_and_the_default_is_kept() -> None:
    rng = np.random.default_rng(1)
    base = rng.random(120) * 0.2
    noise = rng.normal(0, 0.15, 120)
    noisy = base + noise - noise.mean() + 0.004  # best mean, but pure noise
    trials = run_choice(base, {"noisy": noisy})
    assert trials[1].stats["ndcg10"] > trials[0].stats["ndcg10"]
    assert trials[1].stats["diff_vs_reference_low"] < 0
    assert trials[0].status.startswith("adopted")
    assert "INCONCLUSIVE" in trials[0].status
    assert trials[1].status == "not adopted"


def test_the_default_wins_when_it_has_the_best_mean_or_ties() -> None:
    base = np.random.default_rng(2).random(60) * 0.2
    trials = run_choice(base, {"same": base.copy(), "worse": base - 0.05})
    assert trials[0].status.startswith("adopted")
    assert all(t.status == "not adopted" for t in trials[1:])


# ---- the test period stays unread ----------------------------------------------------


def test_tuning_code_cannot_name_the_test_period() -> None:
    source = Path(tuning_module.__file__).read_text()
    assert tuning_module.TARGET == "validation"
    assert "allow_test" not in source
    assert '"test"' not in source and "'test'" not in source


@pytest.fixture(scope="module")
def toy_run(toy: tuple[Split, pd.DataFrame]):  # type: ignore[no-untyped-def]
    split, movies = toy
    seen: dict[str, set[Any]] = {"targets": set()}

    def spy(real: Any, position: int) -> Any:
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            seen["targets"].add(args[position] if len(args) > position else None)
            return real(*args, **kwargs)

        return wrapper

    patch = pytest.MonkeyPatch()
    patch.setattr(tuning_module, "user_history", spy(tuning_module.user_history, 2))
    patch.setattr(
        tuning_module, "evaluation_users", spy(tuning_module.evaluation_users, 1)
    )
    patch.setattr(
        tuning_module,
        "heldout_relevant_items",
        spy(tuning_module.heldout_relevant_items, 2),
    )
    real_fit = Recommender.fit.__func__  # type: ignore[attr-defined]

    def fit_spy(cls: Any, data: Any, *, target: str, **kw: Any) -> Any:
        seen["targets"].add(target)
        return real_fit(cls, data, target=target, **kw)

    patch.setattr(Recommender, "fit", classmethod(fit_spy))
    try:
        fit = fit_data(split, movies, "validation")
        ctx = Context(split, fit)
        outcome = run_stages(ctx, N_BOOT, lambda _: None)
    finally:
        patch.undo()
    return ctx, outcome, seen["targets"]


def test_every_tuning_read_is_validation(toy_run) -> None:  # type: ignore[no-untyped-def]
    _, _, targets = toy_run
    assert targets == {"validation"}


def test_the_whole_approved_grid_is_tried_once(toy_run) -> None:  # type: ignore[no-untyped-def]
    _, outcome, _ = toy_run
    stages = pd.Series([t.stage for t in outcome.trials]).value_counts().to_dict()
    assert stages == {
        "item_knn grid": len(KNN_GRID),  # 9 (neighbours x shrinkage)
        "item_knn min_support": 3,  # 5, 10, 20 (0 is the grid winner)
        "svd factors": 3,
        "content weights": 9,  # default + 4 groups x (0.5, 2)
        "hybrid many-ratings weights": 6,
        "hybrid few-ratings weights": 6,
    }
    assert len(outcome.trials) == 36
    for stage in stages:
        adopted = [
            t
            for t in outcome.trials
            if t.stage == stage and t.status.startswith("adopted")
        ]
        assert len(adopted) == 1


def test_the_adopted_settings_come_from_the_adopted_trials(toy_run) -> None:  # type: ignore[no-untyped-def]
    _, outcome, _ = toy_run
    knn = outcome.adopted["item_knn grid"].params
    assert outcome.settings.neighbours == knn["neighbours"]
    assert outcome.settings.shrinkage == knn["shrinkage"]
    assert (
        outcome.settings.min_support
        == outcome.adopted["item_knn min_support"].params["min_support"]
    )
    assert outcome.settings.factors == outcome.adopted["svd factors"].params["factors"]
    assert (
        outcome.config.many_weights
        == (outcome.adopted["hybrid many-ratings weights"].params["many_weights"])
    )
    assert (
        outcome.config.few_weights
        == (outcome.adopted["hybrid few-ratings weights"].params["few_weights"])
    )


def test_the_default_hybrid_trial_reproduces_the_normal_recommender(
    toy: tuple[Split, pd.DataFrame], toy_run
) -> None:  # type: ignore[no-untyped-def]
    """A trial uses the one real Recommender, so the default trial equals plain use."""
    split, movies = toy
    ctx, outcome, _ = toy_run
    many_default = next(
        t
        for t in outcome.trials
        if t.stage == "hybrid many-ratings weights" and t.name == "default"
    )
    rec = Recommender.fit(ctx.fit, target="validation", settings=outcome.settings)
    ranker = tuning_module.hybrid_ranker(rec, split)
    again = ctx.score(("warm",), ranker)["warm"]
    assert np.array_equal(many_default.scores["warm"].ndcg, again.ndcg)


# ---- frozen configuration and MLflow -------------------------------------------------


def test_the_frozen_config_round_trips_and_detects_tampering(
    tmp_path: Path,
) -> None:
    settings = ModelSettings(neighbours=100, shrinkage=25.0, min_support=10)
    config = HybridConfig(
        few_weights={
            "content": 0.1,
            "item_knn": 0.1,
            "svd": 0.1,
            "popularity": 0.7,
        }
    )
    payload = config_payload(settings, config, "abc")
    payload["sha256"] = canonical_hash(payload)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(payload))
    loaded_settings, loaded_config = load_frozen(path)
    assert loaded_settings == settings and loaded_config == config
    assert "GRID WINNER" in payload["status"]  # the owner has not chosen it yet
    payload["status"] = "something else"  # the status line is not part of the hash
    assert canonical_hash(payload) == payload["sha256"]
    payload["settings"]["neighbours"] = 5
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="SHA-256"):
        load_frozen(path)


def test_each_configuration_becomes_one_mlflow_run(
    toy_run,  # type: ignore[no-untyped-def]
    tmp_path: Path,
) -> None:
    import mlflow

    _, outcome, _ = toy_run
    uri = log_to_mlflow(outcome.trials, outcome, "abc", tmp_path / "mlruns")
    mlflow.set_tracking_uri(uri)
    experiment = mlflow.get_experiment_by_name(tuning_module.EXPERIMENT)
    assert experiment is not None
    runs = mlflow.search_runs([experiment.experiment_id])
    assert len(runs) == len(outcome.trials) + 1  # one per configuration + the parent
    assert "metrics.ndcg10" in runs.columns
    assert PopularityScorer.name == "popularity"


# ---- the owner's popularity fallback (D-030) -----------------------------------------


def test_owner_decisions_change_only_the_low_rating_rungs() -> None:
    from pmrs.evaluation.selection import (
        FALLBACK_MAX_RATINGS,
        POPULARITY_ONLY,
        apply_owner_decisions,
    )

    grid_settings = ModelSettings(neighbours=20, shrinkage=5.0, min_support=20)
    grid = HybridConfig(
        few_weights={"content": 0.0, "item_knn": 0.0, "svd": 0.3, "popularity": 0.7},
        many_weights={"content": 0.2, "item_knn": 0.2, "svd": 0.4, "popularity": 0.2},
    )
    settings, config = apply_owner_decisions(grid_settings, grid)
    assert settings == grid_settings  # kNN, SVD and content settings untouched
    assert config.few_weights == POPULARITY_ONLY
    assert config.many_weights == grid.many_weights
    assert (config.genre_weight, config.popularity_weight) == (0.6, 0.4)
    assert config.few_max == FALLBACK_MAX_RATINGS == 10
    assert [config.branch(n) for n in (0, 1, 3, 5, 10, 11, 50)] == [
        "no_ratings",
        "few_ratings",
        "few_ratings",
        "few_ratings",
        "few_ratings",
        "many_ratings",
        "many_ratings",
    ]


def test_selected_file_labels_owner_decisions_and_round_trips(tmp_path: Path) -> None:
    from pmrs.evaluation.selection import apply_owner_decisions, selected_payload

    settings, config = apply_owner_decisions(ModelSettings(), HybridConfig())
    grid = {"claim": "c", "data_hash": "h", "seed": 42, "sha256": "g"}
    payload = selected_payload(settings, config, grid)
    text = json.dumps(payload)
    assert "OWNER DECISION" in text and "tuning-grid winner" in text
    assert payload["routing"]["1 to 10 ratings"].startswith("popularity")
    assert payload["routing"]["11+ ratings"].startswith("warm-user hybrid")
    path = tmp_path / "selected.json"
    path.write_text(text)
    assert load_frozen(path) == (settings, config)


def test_the_popularity_rung_gives_exactly_the_popularity_ranking(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    from pmrs.evaluation.selection import apply_owner_decisions
    from pmrs.recommender import user_history
    from pmrs.split import evaluation_users

    split, movies = toy
    fit = fit_data(split, movies, "validation")
    settings, config = apply_owner_decisions(ModelSettings(), HybridConfig())
    rec = Recommender.fit(fit, target="validation", settings=settings, config=config)
    popularity = PopularityScorer().fit(fit)
    user = int(evaluation_users(split, "validation", "cold_start")[0])
    for size in (0, 3, 5, 10):
        history = user_history(split, user, "validation", size)
        profile = tuning_module.profile_from_history(history, split.item_map)
        listing = rec.recommend(profile, "hybrid", k=20)
        assert listing.branch == ("no_ratings" if size == 0 else "few_ratings")
        assert listing.movie_ids == popularity.recommend(history, k=20).tolist()
