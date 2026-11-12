"""Step 14 evaluation harness: every method, one protocol, per-user results.

What it does. For each evaluated user it builds a top-20 list per method and scores it
against that user's held-out relevant movies (rated 4.0 or higher in the target period),
at K = 5, 10 and 20. Results are kept per user so intervals can be computed, and the
cold-start simulation is reported separately (0, 3, 5 and 10 revealed ratings).

Protocol (unchanged from Step 5, D-021 and D-023):

* Validation mode fits on train data only. The test period is protected: ``evaluate``
  refuses ``target="test"`` unless the caller passes ``allow_test=True``, which only the
  final evaluation (Step 16) is meant to do. Tuning code never passes it.
* Candidate set for a warm user: the whole catalogue minus the user's own pre-cutoff
  movies. Held-out movies stay eligible, so a relevant held-out movie must beat every
  other unknown movie. For a cold-start simulation user: minus only the revealed
  ratings.
  Every list is checked against this rule as it is built.
* ``verify_fit_respects_cutoffs`` checks the data really handed to the models: every
  rating and tag used is strictly earlier than its own user's or author's cutoff in
  force.

Claim limit, printed with every result: this compares methods under one per-user holdout
protocol. It does not show leakage-safe or future prediction, because the models are
fitted once and still see other users' later ratings and tags.
"""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from itertools import product
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from pmrs.metrics import (
    average_precision_at_k,
    bootstrap_ci,
    bootstrap_ratio_ci,
    catalogue_coverage,
    genre_diversity,
    ndcg_at_k,
    paired_bootstrap_difference,
    precision_at_k,
    recall_at_k,
)
from pmrs.metrics.intervals import DEFAULT_BOOTSTRAPS
from pmrs.recommender.base import FitData, Scorer, fit_data, user_history
from pmrs.recommender.baselines import BayesianAverageScorer
from pmrs.recommender.content import ContentScorer
from pmrs.recommender.hybrid import HybridConfig
from pmrs.recommender.recommender import Recommender, profile_from_history
from pmrs.recommender.settings import ModelSettings
from pmrs.recommender.svd import SVDScorer
from pmrs.split import (
    HISTORY_SIZES,
    Group,
    Split,
    Target,
    evaluation_users,
    fit_ratings,
    fit_tags,
    heldout_relevant_items,
)

CLAIM = (
    "Methods compared under the same per-user holdout protocol (D-021). This is not "
    "globally leakage-safe and not a prediction of future behaviour: models are fitted "
    "once and still see other users' ratings and tags dated after a scored user's own "
    "cutoff."
)
KS = (5, 10, 20)
METHODS = (
    "random",
    "popularity",
    "bayesian_average",
    "content",
    "content_no_tags",
    "item_knn",
    "svd",
    "hybrid",
)
BASELINES = ("random", "popularity", "bayesian_average")
SINGLE_PERSONALISED = ("content", "item_knn", "svd")
METRICS = ("precision", "recall", "map", "ndcg", "diversity")
PRIMARY_METRIC = "ndcg"  # chosen in advance: NDCG@10 is the headline comparison
PRIMARY_K = 10
RATING_METHODS = ("global_mean", "user_mean", "bayesian_average", "svd")


class ProtectedTargetError(RuntimeError):
    """Raised when code tries to evaluate on the protected test period."""


@dataclass(frozen=True)
class Slice:
    """One group of evaluated users: warm, or cold-start (``history_size`` revealed)."""

    group: Group
    history_size: int | None

    @property
    def label(self) -> str:
        return "warm" if self.group == "warm" else f"cold_start_{self.history_size}"


def all_slices() -> list[Slice]:
    return [Slice("warm", None), *(Slice("cold_start", h) for h in HISTORY_SIZES)]


@dataclass
class EvaluationResult:
    target: Target
    per_user: pd.DataFrame  # one row per slice, user, method and K
    coverage: pd.DataFrame
    rating_errors: pd.DataFrame
    users_per_slice: dict[str, int]
    # the top-20 movie ids behind every number, so tests and reviewers can inspect them
    lists: dict[tuple[str, str], list[npt.NDArray[np.int64]]] = field(
        default_factory=dict
    )
    list_users: dict[str, list[int]] = field(default_factory=dict)
    info: dict[str, Any] = field(default_factory=dict)


# ---- guard rails ---------------------------------------------------------------------


def verify_fit_respects_cutoffs(split: Split, target: Target) -> None:
    """Raise if any fitted rating or tag is at or after its own cutoff in force.

    Validation: ratings must be earlier than the user's validation cutoff. Test: earlier
    than the user's test cutoff. Tags use the author's cutoff the same way. Cold-start
    users must have no ratings or tags in the fit at all.
    """
    column = "validation_cutoff" if target == "validation" else "test_cutoff"
    cold = split.users.index[split.users["is_cold_start"]]
    ratings = fit_ratings(split, target)
    cut = ratings["user_id"].map(split.users[column])
    late = ratings[~(ratings["timestamp"] < cut)]
    if len(late):
        raise ValueError(f"{len(late)} fitted ratings are at or after their cutoff")
    if ratings["user_id"].isin(cold).any():
        raise ValueError("a cold-start simulation user's ratings are in the fit")
    tags = fit_tags(split, target)
    tag_cut = tags["user_id"].map(split.users[column])
    if len(tags) and not (tags["timestamp"] < tag_cut).all():
        raise ValueError("a fitted tag is at or after its author's cutoff")
    if tags["user_id"].isin(cold).any():
        raise ValueError("a cold-start simulation user's tags are in the fit")


def _check_list(
    ranked: npt.NDArray[np.int64], seen: npt.NDArray[np.int64], user: int, method: str
) -> None:
    """Candidate rule: a list never holds a movie the user is known to have rated."""
    if len(ranked) != max(KS) or len(np.unique(ranked)) != len(ranked):
        raise ValueError(f"{method} gave user {user} a short or repeating list")
    if np.isin(ranked, seen).any():
        raise ValueError(f"{method} recommended a known movie to user {user}")


# ---- running -------------------------------------------------------------------------


def _top(
    method: str,
    history: Any,
    rec: Recommender,
    scorers: dict[str, Scorer],
    split: Split,
) -> npt.NDArray[np.int64]:
    if method == "hybrid":
        profile = profile_from_history(history, split.item_map)
        listing = rec.recommend(profile, "hybrid", k=max(KS))
        return np.array(listing.movie_ids, dtype=np.int64)
    return np.asarray(scorers[method].recommend(history, k=max(KS)), dtype=np.int64)


def evaluate(
    split: Split,
    movies: pd.DataFrame,
    target: Target,
    *,
    methods: Sequence[str] = METHODS,
    allow_test: bool = False,
    seed: int = 42,
    data_hash: str = "",
    n_boot: int = DEFAULT_BOOTSTRAPS,
    settings: ModelSettings | None = None,
    config: HybridConfig | None = None,
) -> EvaluationResult:
    """Score every method for every evaluated user; see the module note."""
    if target == "test" and not allow_test:
        raise ProtectedTargetError(
            "the test period is protected: it is read once, by the final evaluation "
            "(Step 16), after the configuration is frozen"
        )
    unknown = set(methods) - set(METHODS)
    if unknown:
        raise ValueError(f"unknown methods {sorted(unknown)}")
    verify_fit_respects_cutoffs(split, target)
    fit = fit_data(split, movies, target)
    rec = Recommender.fit(
        fit,
        target=target,
        seed=seed,
        config=config,
        settings=settings,
        data_hash=data_hash,
    )
    scorers = dict(rec.scorers)
    scorers["content_no_tags"] = ContentScorer(
        use_tags=False, weights=(settings or ModelSettings()).content_weights
    ).fit(fit)
    genre_sets = [rec.catalog.genre_set(i) for i in range(len(fit.item_map))]

    rows: list[dict[str, Any]] = []
    lists: dict[tuple[str, str], list[npt.NDArray[np.int64]]] = defaultdict(list)
    users_per_slice: dict[str, int] = {}
    list_users: dict[str, list[int]] = {}
    for part in all_slices():
        users = evaluation_users(split, target, part.group)
        users_per_slice[part.label] = len(users)
        list_users[part.label] = [int(u) for u in users.tolist()]
        for user in users.tolist():
            history = user_history(split, int(user), target, part.history_size)
            seen = split.item_map.ids[history.items]
            relevant = heldout_relevant_items(split, int(user), target)
            if relevant.size == 0:
                raise ValueError(f"user {user} has no relevant held-out movie")
            for method in methods:
                ranked = _top(method, history, rec, scorers, split)
                _check_list(ranked, seen, int(user), method)
                lists[(part.label, method)].append(ranked)
                positions = split.item_map.to_index(ranked)
                for k in KS:
                    rows.append(
                        {
                            "slice": part.label,
                            "group": part.group,
                            "history_size": part.history_size,
                            "user_id": int(user),
                            "method": method,
                            "k": k,
                            "n_relevant": int(relevant.size),
                            "precision": precision_at_k(ranked, relevant, k),
                            "recall": recall_at_k(ranked, relevant, k),
                            "map": average_precision_at_k(ranked, relevant, k),
                            "ndcg": ndcg_at_k(ranked, relevant, k),
                            "diversity": genre_diversity(
                                [genre_sets[p] for p in positions[:k]]
                            ),
                        }
                    )
    per_user = pd.DataFrame(rows)
    if per_user[list(METRICS)].isna().any().any():
        raise ValueError(
            "a per-user metric is undefined (NaN): check the evaluated users"
        )

    coverage = pd.DataFrame(
        [
            {
                "slice": label,
                "method": method,
                "k": k,
                "n_users": len(found),
                "coverage": catalogue_coverage(
                    [list(x) for x in found], len(fit.item_map), k
                ),
            }
            for (label, method), found in lists.items()
            for k in KS
        ]
    )
    errors = rating_errors(split, target, fit, scorers, n_boot=n_boot)
    info = {
        "target": target,
        "claim": CLAIM,
        "seed": seed,
        "n_boot": n_boot,
        "ks": list(KS),
        "methods": list(methods),
        "users_per_slice": users_per_slice,
        "n_items": len(fit.item_map),
        "n_fit_ratings": int(fit.matrix.nnz),
        "data_hash": data_hash,
    }
    return EvaluationResult(
        target,
        per_user,
        coverage,
        errors,
        users_per_slice,
        dict(lists),
        list_users,
        info,
    )


# ---- rating error (secondary) --------------------------------------------------------


def rating_errors(
    split: Split,
    target: Target,
    fit: FitData,
    scorers: dict[str, Scorer],
    *,
    n_boot: int = DEFAULT_BOOTSTRAPS,
) -> pd.DataFrame:
    """RMSE and MAE on warm users' held-out ratings, with intervals over users.

    Secondary to the ranking comparison: how close a predicted number is to the rating
    is a different question from whether the right movies are at the top. Only the SVD,
    Bayesian-average and two reference predictors produce a rating; the others are
    ranking-only. ``global_mean`` and ``user_mean`` are references, not models.
    """
    svd = scorers["svd"]
    bayes = scorers["bayesian_average"]
    assert isinstance(svd, SVDScorer) and isinstance(bayes, BayesianAverageScorer)
    held = split.ratings[split.ratings["period"] == target].set_index("user_id")
    global_mean = float(fit.matrix.data.mean())
    sums: dict[str, tuple[list[float], list[float], list[float]]] = {
        m: ([], [], []) for m in RATING_METHODS
    }
    for user in evaluation_users(split, target, "warm").tolist():
        rows = held.loc[[int(user)]]
        positions = split.item_map.to_index(rows["movie_id"])
        actual = rows["rating"].to_numpy(dtype=np.float64)
        history = user_history(split, int(user), target)
        predictions = {
            "global_mean": np.full(len(actual), global_mean),
            "user_mean": np.full(len(actual), float(history.ratings.mean())),
            "bayesian_average": bayes.values[positions],
            "svd": svd.predict_ratings(history)[positions],
        }
        for method, predicted in predictions.items():
            error = predicted - actual
            squared, absolute, count = sums[method]
            squared.append(float((error**2).sum()))
            absolute.append(float(np.abs(error).sum()))
            count.append(float(len(actual)))
    out = []
    for method, (squared, absolute, count) in sums.items():
        n = np.array(count)
        mse, mse_low, mse_high = bootstrap_ratio_ci(np.array(squared), n, n_boot=n_boot)
        mae, mae_low, mae_high = bootstrap_ratio_ci(
            np.array(absolute), n, n_boot=n_boot
        )
        out.append(
            {
                "method": method,
                "n_users": len(count),
                "n_ratings": int(n.sum()),
                "rmse": float(np.sqrt(mse)),
                "rmse_low": float(np.sqrt(mse_low)),
                "rmse_high": float(np.sqrt(mse_high)),
                "mae": mae,
                "mae_low": mae_low,
                "mae_high": mae_high,
            }
        )
    return pd.DataFrame(out)


# ---- summaries -----------------------------------------------------------------------


def summarize(
    per_user: pd.DataFrame, *, n_boot: int = DEFAULT_BOOTSTRAPS
) -> pd.DataFrame:
    """Mean of each metric per slice, method and K with a 95% bootstrap interval."""
    rows: list[dict[str, Any]] = []
    for label, method, k in product(
        per_user["slice"].unique(), per_user["method"].unique(), KS
    ):
        part = per_user[
            (per_user["slice"] == label)
            & (per_user["method"] == method)
            & (per_user["k"] == k)
        ].sort_values("user_id")
        if part.empty:
            continue
        row: dict[str, Any] = {
            "slice": str(label),
            "method": str(method),
            "k": k,
            "n_users": len(part),
        }
        for metric in METRICS:
            mean, low, high = bootstrap_ci(
                part[metric].to_numpy(dtype=np.float64), n_boot=n_boot
            )
            row[metric], row[f"{metric}_low"], row[f"{metric}_high"] = mean, low, high
        rows.append(row)
    return pd.DataFrame(rows)


def default_pairs(methods: Sequence[str]) -> list[tuple[str, str]]:
    """Each personalised method against each baseline; the hybrid against each single
    personalised method (the plan asks whether the blend beats its best part).
    """
    present = set(methods)
    pairs = [
        (m, b)
        for m, b in product(METHODS, BASELINES)
        if m in present and b in present and m not in BASELINES
    ]
    pairs += [
        ("hybrid", s)
        for s in SINGLE_PERSONALISED
        if "hybrid" in present and s in present
    ]
    return pairs


def compare(
    per_user: pd.DataFrame,
    *,
    k: int = PRIMARY_K,
    metric: str = PRIMARY_METRIC,
    pairs: Sequence[tuple[str, str]] | None = None,
    n_boot: int = DEFAULT_BOOTSTRAPS,
) -> pd.DataFrame:
    """Paired difference (method minus reference) on the same users, 95% interval."""
    wanted = (
        list(pairs)
        if pairs is not None
        else default_pairs(sorted(per_user["method"].unique()))
    )
    rows: list[dict[str, Any]] = []
    at_k = per_user[per_user["k"] == k]
    for label in at_k["slice"].unique():
        wide = at_k[at_k["slice"] == label].pivot(
            index="user_id", columns="method", values=metric
        )
        for method, reference in wanted:
            if method not in wide.columns or reference not in wide.columns:
                continue
            diff, low, high = paired_bootstrap_difference(
                wide[method].to_numpy(dtype=np.float64),
                wide[reference].to_numpy(dtype=np.float64),
                n_boot=n_boot,
            )
            rows.append(
                {
                    "slice": str(label),
                    "metric": metric,
                    "k": k,
                    "method": method,
                    "reference": reference,
                    "n_users": len(wide),
                    "difference": diff,
                    "low": low,
                    "high": high,
                    "interval_excludes_zero": bool(low > 0 or high < 0),
                }
            )
    return pd.DataFrame(rows)
