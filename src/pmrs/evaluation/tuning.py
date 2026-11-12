"""Step 15: tune settings on the VALIDATION period only, then propose a frozen config.

Rules (owner-approved, D-029):

* Validation data only. Nothing here can name the test period: ``TARGET`` is fixed to
  ``"validation"``; no function takes a target argument or unlocks the protected
  period.
* Headline metric: NDCG@10 (precision, recall, MAP and coverage at 10 are supporting).
* Selection rule: take the configuration with the best mean NDCG@10 on the objective
  users; adopt it only if its paired bootstrap difference against the reference (the
  default, or the previously adopted setting) has a 95% interval entirely above 0.
  Otherwise keep the reference and call the comparison inconclusive.
* One stage at a time (no full cross-product): item-kNN, then SVD, then content, then
  the many-ratings hybrid weights, then the few-ratings hybrid weights. Later stages use
  the settings adopted earlier.
* Objectives: single models and the many-ratings rung use the warm users; the
  few-ratings rung uses the cold-start simulation users at 3 and 5 revealed ratings
  (each user's NDCG@10 averaged over the two). Cold-start at 10 is reported as a check.

Winner's curse: choosing the best of many tries on the same users makes the winner's
validation score optimistic. Intervals cover sampling noise between users only. The
claim limit is unchanged: methods compared under the same per-user holdout protocol
(D-021).
"""

import argparse
import hashlib
import json
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from pmrs.data import load_movielens
from pmrs.evaluation.harness import (
    CLAIM,
    KS,
    PRIMARY_K,
    EvaluationResult,
    _check_list,
    compare,
    evaluate,
    summarize,
    verify_fit_respects_cutoffs,
)
from pmrs.metrics import (
    average_precision_at_k,
    bootstrap_ci,
    catalogue_coverage,
    ndcg_at_k,
    paired_bootstrap_difference,
    precision_at_k,
    recall_at_k,
)
from pmrs.metrics.intervals import DEFAULT_BOOTSTRAPS
from pmrs.recommender.artifact import data_fingerprint
from pmrs.recommender.base import FitData, History, Scorer, fit_data, user_history
from pmrs.recommender.baselines import PopularityScorer
from pmrs.recommender.content import DEFAULT_WEIGHTS, ContentScorer
from pmrs.recommender.hybrid import HybridConfig
from pmrs.recommender.knn import ItemKNNScorer
from pmrs.recommender.recommender import (
    Recommender,
    profile_from_history,
)
from pmrs.recommender.settings import ModelSettings
from pmrs.recommender.svd import SVDScorer
from pmrs.split import (
    Group,
    Split,
    Target,
    build_split,
    evaluation_users,
    heldout_relevant_items,
)

TARGET: Target = "validation"  # tuning never reads anything else
RAW_DIR = Path("data/raw/ml-latest-small")
OUT_DIR = Path("data/processed/tuning")
MLFLOW_DIR = Path("mlruns")
GRID_WINNER_FILE = "grid_winner_config.json"  # what the selection rule alone chose
EXPERIMENT = "pmrs-step15-validation-tuning"
SLICES = {"warm": None, "cold_start_3": 3, "cold_start_5": 5, "cold_start_10": 10}

# ---- the approved grids (D-029). The reference (default) is always first. -----------

KNN_GRID = [(50, 10.0)] + [
    (n, s) for n in (20, 50, 100) for s in (5.0, 10.0, 25.0) if (n, s) != (50, 10.0)
]
SUPPORT_GRID = (5, 10, 20)  # 0 is the reference
SVD_GRID = (50, 20, 100)
CONTENT_GROUPS = ("genres", "tags", "title", "decade")
CONTENT_FACTORS = (0.5, 2.0)
Weights = dict[str, float]


def _w(content: float, knn: float, svd: float, pop: float) -> Weights:
    return {"content": content, "item_knn": knn, "svd": svd, "popularity": pop}


MANY_GRID: list[tuple[str, Weights]] = [
    ("default", _w(0.35, 0.25, 0.25, 0.15)),
    ("svd-leaning", _w(0.20, 0.20, 0.40, 0.20)),
    ("popularity-heavier", _w(0.15, 0.15, 0.30, 0.40)),
    ("no-content", _w(0.00, 0.20, 0.50, 0.30)),
    ("equal", _w(0.25, 0.25, 0.25, 0.25)),
    ("svd+popularity", _w(0.10, 0.10, 0.40, 0.40)),
]
FEW_GRID: list[tuple[str, Weights]] = [
    ("default", _w(0.60, 0.15, 0.15, 0.10)),
    ("popularity 0.30", _w(0.40, 0.15, 0.15, 0.30)),
    ("popularity 0.45", _w(0.25, 0.15, 0.15, 0.45)),
    ("popularity 0.70", _w(0.10, 0.10, 0.10, 0.70)),
    ("svd+popularity 0.60", _w(0.10, 0.00, 0.30, 0.60)),
    ("svd+popularity 0.70", _w(0.00, 0.00, 0.30, 0.70)),
]


# ---- per-user scoring ----------------------------------------------------------------


@dataclass(frozen=True)
class Case:
    """One evaluated user in one slice: what the model is told and what is held out."""

    user: int
    history: History
    seen: npt.NDArray[np.int64]
    relevant: npt.NDArray[np.int64]


@dataclass
class SliceScores:
    ndcg: npt.NDArray[np.float64]
    precision: npt.NDArray[np.float64]
    recall: npt.NDArray[np.float64]
    map: npt.NDArray[np.float64]
    coverage: float


Ranker = Callable[[History], npt.NDArray[np.int64]]  # top-20 raw movie ids


class Context:
    """Validation users, histories and held-out sets, built once for every trial."""

    def __init__(self, split: Split, fit: FitData) -> None:
        self.split = split
        self.fit = fit
        verify_fit_respects_cutoffs(split, TARGET)
        self.cases: dict[str, list[Case]] = {}
        for label, size in SLICES.items():
            group: Group = "warm" if size is None else "cold_start"
            cases = []
            for user in evaluation_users(split, TARGET, group).tolist():
                history = user_history(split, int(user), TARGET, size)
                relevant = heldout_relevant_items(split, int(user), TARGET)
                if relevant.size == 0:
                    raise ValueError(f"user {user} has no relevant held-out movie")
                seen = split.item_map.ids[history.items]
                cases.append(Case(int(user), history, seen, relevant))
            self.cases[label] = cases
        warm = self.cases["warm"]
        self.warm_many = sum(len(c.history) >= HybridConfig().few_max + 1 for c in warm)

    def score(self, labels: Sequence[str], rank: Ranker) -> dict[str, SliceScores]:
        out: dict[str, SliceScores] = {}
        for label in labels:
            cases = self.cases[label]
            lists = []
            metrics: dict[str, list[float]] = {
                "ndcg": [],
                "precision": [],
                "recall": [],
                "map": [],
            }
            for case in cases:
                ranked = rank(case.history)
                _check_list(ranked, case.seen, case.user, label)
                lists.append(ranked[:PRIMARY_K].tolist())
                metrics["ndcg"].append(ndcg_at_k(ranked, case.relevant, PRIMARY_K))
                metrics["precision"].append(
                    precision_at_k(ranked, case.relevant, PRIMARY_K)
                )
                metrics["recall"].append(recall_at_k(ranked, case.relevant, PRIMARY_K))
                metrics["map"].append(
                    average_precision_at_k(ranked, case.relevant, PRIMARY_K)
                )
            out[label] = SliceScores(
                ndcg=np.array(metrics["ndcg"], dtype=np.float64),
                precision=np.array(metrics["precision"], dtype=np.float64),
                recall=np.array(metrics["recall"], dtype=np.float64),
                map=np.array(metrics["map"], dtype=np.float64),
                coverage=catalogue_coverage(lists, len(self.fit.item_map), PRIMARY_K),
            )
        return out


def scorer_ranker(scorer: Scorer) -> Ranker:
    return lambda history: np.asarray(
        scorer.recommend(history, k=max(KS)), dtype=np.int64
    )


def hybrid_ranker(rec: Recommender, split: Split) -> Ranker:
    def rank(history: History) -> npt.NDArray[np.int64]:
        profile = profile_from_history(history, split.item_map)
        return np.array(rec.recommend(profile, "hybrid", k=max(KS)).movie_ids)

    return rank


# ---- trials and the selection rule ---------------------------------------------------


@dataclass
class Trial:
    stage: str
    model: str
    name: str
    params: dict[str, Any]
    objective: tuple[str, ...]  # slices the objective averages over
    scores: dict[str, SliceScores]
    seconds: float = 0.0
    status: str = ""
    reference: str = ""
    # filled in by ``analyse``
    stats: dict[str, float] = field(default_factory=dict)

    def vector(self, key: str = "ndcg") -> npt.NDArray[np.float64]:
        """Per-user value of ``key`` averaged over the objective slices."""
        return np.mean(
            [getattr(self.scores[s], key) for s in self.objective], axis=0
        ).astype(np.float64)

    def coverage(self) -> float:
        return float(np.mean([self.scores[s].coverage for s in self.objective]))


def analyse(
    trials: list[Trial], reference: Trial, popularity: Trial, n_boot: int
) -> None:
    """Fill in each trial's mean, interval and paired differences."""
    for t in trials:
        mean, low, high = bootstrap_ci(t.vector(), n_boot=n_boot)
        d, dl, dh = paired_bootstrap_difference(
            t.vector(), reference.vector(), n_boot=n_boot
        )
        p, pl, ph = paired_bootstrap_difference(
            t.vector(), popularity.vector(), n_boot=n_boot
        )
        t.reference = reference.name
        t.stats = {
            "ndcg10": mean,
            "ndcg10_low": low,
            "ndcg10_high": high,
            "precision10": float(t.vector("precision").mean()),
            "recall10": float(t.vector("recall").mean()),
            "map10": float(t.vector("map").mean()),
            "coverage10": t.coverage(),
            "n_users": float(len(t.vector())),
            "diff_vs_reference": d,
            "diff_vs_reference_low": dl,
            "diff_vs_reference_high": dh,
            "diff_vs_popularity": p,
            "diff_vs_popularity_low": pl,
            "diff_vs_popularity_high": ph,
        }


def choose(trials: list[Trial], reference: Trial) -> Trial:
    """The selection rule; ``trials`` includes ``reference``, which wins ties."""
    best = max(trials, key=lambda t: (t.stats["ndcg10"], t is reference))
    if best is reference:
        winner, why = reference, "the reference had the best mean NDCG@10"
    elif best.stats["diff_vs_reference_low"] > 0:
        winner, why = best, "best mean, and its paired interval is entirely above 0"
    else:
        winner = reference
        why = (
            f"INCONCLUSIVE: '{best.name}' had the best mean but its paired interval "
            "against the reference spans 0, so the reference is kept"
        )
    for t in trials:
        t.status = "adopted" if t is winner else "not adopted"
    winner.status = f"adopted ({why})"
    return winner


# ---- the stages ----------------------------------------------------------------------


def _trial(
    stage: str,
    model: str,
    name: str,
    params: dict[str, Any],
    ctx: Context,
    objective: tuple[str, ...],
    rank: Ranker,
    extra: tuple[str, ...] = (),
) -> Trial:
    start = time.perf_counter()
    labels = tuple(dict.fromkeys((*objective, *extra)))
    scores = ctx.score(labels, rank)
    return Trial(
        stage, model, name, params, objective, scores, time.perf_counter() - start
    )


def _timed_fit(factory: Callable[[], Scorer], fit: FitData) -> tuple[Scorer, float]:
    start = time.perf_counter()
    scorer = factory().fit(fit)
    return scorer, time.perf_counter() - start


@dataclass
class TuningOutcome:
    trials: list[Trial]
    adopted: dict[str, Trial]
    settings: ModelSettings
    config: HybridConfig
    popularity: dict[str, Trial]


def run_stages(ctx: Context, n_boot: int, log: Callable[[str], None]) -> TuningOutcome:
    fit = ctx.fit
    warm = ("warm",)
    cold35 = ("cold_start_3", "cold_start_5")
    popularity_scorer = PopularityScorer().fit(fit)
    pop_rank = scorer_ranker(popularity_scorer)
    pop_warm = _trial(
        "reference", "popularity", "popularity", {}, ctx, warm, pop_rank, cold35
    )
    pop_cold = _trial(
        "reference",
        "popularity",
        "popularity",
        {},
        ctx,
        cold35,
        pop_rank,
        ("cold_start_10",),
    )
    all_trials: list[Trial] = []
    adopted: dict[str, Trial] = {}
    settings = ModelSettings()

    def run_stage(stage: str, candidates: list[Trial], popularity: Trial) -> Trial:
        reference = candidates[0]
        analyse(candidates, reference, popularity, n_boot)
        winner = choose(candidates, reference)
        all_trials.extend(candidates)
        log(f"  {stage}: adopted '{winner.name}' ({winner.status})")
        return winner

    # -- item-kNN grid (neighbours x shrinkage), no minimum support yet
    log("item-kNN: neighbours x shrinkage")
    candidates = []
    for neighbours, shrinkage in KNN_GRID:
        scorer, fit_s = _timed_fit(partial(ItemKNNScorer, neighbours, shrinkage), fit)
        t = _trial(
            "item_knn grid",
            "item_knn",
            f"neighbours={neighbours}, shrinkage={shrinkage:g}",
            {"neighbours": neighbours, "shrinkage": shrinkage, "min_support": 0},
            ctx,
            warm,
            scorer_ranker(scorer),
        )
        t.seconds += fit_s
        candidates.append(t)
    knn_best = run_stage("item_knn grid", candidates, pop_warm)
    adopted["item_knn grid"] = knn_best
    settings = ModelSettings(
        neighbours=int(knn_best.params["neighbours"]),
        shrinkage=float(knn_best.params["shrinkage"]),
    )

    # -- item-kNN minimum support, on top of the adopted grid point
    log("item-kNN: minimum support")
    support_trials = [knn_best]  # m = 0 is the adopted trial, reused as the reference
    for m in SUPPORT_GRID:
        scorer, fit_s = _timed_fit(
            partial(
                ItemKNNScorer,
                settings.neighbours,
                settings.shrinkage,
                min_support=m,
            ),
            fit,
        )
        t = _trial(
            "item_knn min_support",
            "item_knn",
            f"{knn_best.name}, min_support={m}",
            {**knn_best.params, "min_support": m},
            ctx,
            warm,
            scorer_ranker(scorer),
        )
        t.seconds += fit_s
        support_trials.append(t)
    # m=0 keeps its grid-stage numbers and status; only new trials are added
    grid_status = knn_best.status
    analyse(support_trials[1:], knn_best, pop_warm, n_boot)
    support_best = choose(support_trials, knn_best)
    knn_best.status = grid_status
    all_trials.extend(support_trials[1:])
    log(
        f"  item_knn min_support: adopted '{support_best.name}' ({support_best.status})"
    )
    adopted["item_knn min_support"] = support_best
    settings = ModelSettings(
        neighbours=settings.neighbours,
        shrinkage=settings.shrinkage,
        min_support=int(support_best.params["min_support"]),
    )

    # -- SVD factors
    log("SVD: factors")
    candidates = []
    for factors in SVD_GRID:
        scorer, fit_s = _timed_fit(partial(SVDScorer, factors=factors), fit)
        t = _trial(
            "svd factors",
            "svd",
            f"factors={factors}",
            {"factors": factors},
            ctx,
            warm,
            scorer_ranker(scorer),
        )
        t.seconds += fit_s
        candidates.append(t)
    svd_best = run_stage("svd factors", candidates, pop_warm)
    adopted["svd factors"] = svd_best
    settings = ModelSettings(
        neighbours=settings.neighbours,
        shrinkage=settings.shrinkage,
        min_support=settings.min_support,
        factors=int(svd_best.params["factors"]),
    )

    # -- content feature-group weights, one group at a time
    log("content: feature-group weights")
    variants: list[tuple[str, Weights]] = [("default weights", dict(DEFAULT_WEIGHTS))]
    for group in CONTENT_GROUPS:
        for factor in CONTENT_FACTORS:
            variants.append(
                (f"{group} x{factor:g}", {**DEFAULT_WEIGHTS, group: factor})
            )
    candidates = []
    for name, weights in variants:
        scorer, fit_s = _timed_fit(partial(ContentScorer, weights=weights), fit)
        t = _trial(
            "content weights",
            "content",
            name,
            {"weights": weights},
            ctx,
            warm,
            scorer_ranker(scorer),
        )
        t.seconds += fit_s
        candidates.append(t)
    content_best = run_stage("content weights", candidates, pop_warm)
    adopted["content weights"] = content_best
    settings = ModelSettings(
        neighbours=settings.neighbours,
        shrinkage=settings.shrinkage,
        min_support=settings.min_support,
        factors=settings.factors,
        content_weights=dict(content_best.params["weights"]),
    )

    # -- hybrid weights, with the adopted single-model settings
    log("hybrid: fitting all models with the adopted settings")
    base = Recommender.fit(fit, target=TARGET, settings=settings)

    def hybrid_trials(
        stage: str,
        grid: list[tuple[str, Weights]],
        key: str,
        objective: tuple[str, ...],
        extra: tuple[str, ...],
    ) -> list[Trial]:
        out = []
        for name, weights in grid:
            config = (
                HybridConfig(many_weights=weights)
                if key == "many_weights"
                else HybridConfig(few_weights=weights)
            )
            rec = Recommender(base.catalog, base.scorers, config, base.metadata)
            out.append(
                _trial(
                    stage,
                    "hybrid",
                    name,
                    {key: weights},
                    ctx,
                    objective,
                    hybrid_ranker(rec, ctx.split),
                    extra,
                )
            )
        return out

    log("hybrid: many-ratings rung (warm users)")
    many = hybrid_trials(
        "hybrid many-ratings weights",
        MANY_GRID,
        "many_weights",
        warm,
        ("cold_start_10",),
    )
    many_best = run_stage("hybrid many-ratings weights", many, pop_warm)
    adopted["hybrid many-ratings weights"] = many_best

    log("hybrid: few-ratings rung (cold-start at 3 and 5 revealed)")
    few = hybrid_trials(
        "hybrid few-ratings weights", FEW_GRID, "few_weights", cold35, ()
    )
    few_best = run_stage("hybrid few-ratings weights", few, pop_cold)
    adopted["hybrid few-ratings weights"] = few_best

    config = HybridConfig(
        many_weights=dict(many_best.params["many_weights"]),
        few_weights=dict(few_best.params["few_weights"]),
    )
    return TuningOutcome(
        all_trials,
        adopted,
        settings,
        config,
        {"warm": pop_warm, "cold": pop_cold},
    )


# ---- frozen configuration (proposed) -------------------------------------------------


def config_payload(
    settings: ModelSettings, config: HybridConfig, data_hash: str
) -> dict[str, Any]:
    return {
        "status": "GRID WINNER - chosen by the selection rule alone; see selection.py",
        "chosen_on": "validation period only",
        "claim": CLAIM,
        "data_hash": data_hash,
        "seed": 42,
        "settings": settings.to_dict(),
        "hybrid": {
            "few_max": config.few_max,
            "genre_weight": config.genre_weight,
            "popularity_weight": config.popularity_weight,
            "few_weights": config.few_weights,
            "many_weights": config.many_weights,
        },
    }


def canonical_hash(payload: dict[str, Any]) -> str:
    """SHA-256 of the settings, ignoring the free-text status line."""
    body = {k: v for k, v in payload.items() if k not in ("status", "sha256")}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode()).hexdigest()


def load_frozen(path: Path) -> tuple[ModelSettings, HybridConfig]:
    """Read a config file written by this module, checking its hash."""
    raw = json.loads(path.read_text())
    if canonical_hash(raw) != raw["sha256"]:
        raise ValueError(f"{path} does not match its recorded SHA-256")
    hybrid = raw["hybrid"]
    return ModelSettings.from_dict(raw["settings"]), HybridConfig(
        few_max=hybrid["few_max"],
        genre_weight=hybrid["genre_weight"],
        popularity_weight=hybrid["popularity_weight"],
        few_weights=hybrid["few_weights"],
        many_weights=hybrid["many_weights"],
    )


# ---- tables, MLflow, report ----------------------------------------------------------


def trials_table(trials: list[Trial]) -> pd.DataFrame:
    rows = []
    for t in trials:
        rows.append(
            {
                "stage": t.stage,
                "model": t.model,
                "configuration": t.name,
                "params": json.dumps(t.params, sort_keys=True),
                "objective_slices": "+".join(t.objective),
                "reference": t.reference,
                **t.stats,
                "status": t.status,
            }
        )
    return pd.DataFrame(rows)


def log_to_mlflow(
    trials: list[Trial], outcome: TuningOutcome, data_hash: str, tracking_dir: Path
) -> str:
    """One MLflow run per configuration, in a local file store. Returns the run URI."""
    import os

    # MLflow 3 calls the plain-folder store "maintenance mode" and refuses it unless
    # this is set. It stays local (no server, nothing sent). A SQLite store would need
    # extra packages, which are not approved.
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
    import mlflow

    uri = tracking_dir.resolve().as_uri()
    mlflow.set_tracking_uri(uri)
    mlflow.set_experiment(EXPERIMENT)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    with mlflow.start_run(run_name=f"tuning {stamp}"):
        mlflow.set_tags({"claim": CLAIM, "target": TARGET, "data_hash": data_hash})
        for t in trials:
            with mlflow.start_run(run_name=f"{t.stage}: {t.name}", nested=True):
                mlflow.set_tags(
                    {
                        "stage": t.stage,
                        "model": t.model,
                        "reference": t.reference,
                        "status": t.status,
                        "objective_slices": "+".join(t.objective),
                        "target": TARGET,
                    }
                )
                mlflow.log_param("configuration", t.name)
                mlflow.log_param("params", json.dumps(t.params, sort_keys=True))
                mlflow.log_metrics({k: float(v) for k, v in t.stats.items()})
    return uri


def _fmt(t: Trial) -> str:
    s = t.stats
    return f"{s['ndcg10']:.3f} [{s['ndcg10_low']:.3f}, {s['ndcg10_high']:.3f}]"


def _diff(s: dict[str, float], key: str) -> str:
    return f"{s[key]:+.3f} [{s[key + '_low']:+.3f}, {s[key + '_high']:+.3f}]"


def stage_markdown(trials: list[Trial]) -> str:
    lines = []
    for stage in dict.fromkeys(t.stage for t in trials):
        part = [t for t in trials if t.stage == stage]
        objective = "+".join(part[0].objective)
        lines += [
            f"### {stage}  (objective users: {objective}; "
            f"reference: {part[0].reference})",
            "",
            "| Configuration | NDCG@10 [95% CI] | vs reference (paired) "
            "| vs popularity (paired) | Precision@10 | Recall@10 | MAP@10 "
            "| Coverage@10 | Decision |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        for t in part:
            s = t.stats
            lines.append(
                f"| {t.name} | {_fmt(t)} | {_diff(s, 'diff_vs_reference')} | "
                f"{_diff(s, 'diff_vs_popularity')} | {s['precision10']:.3f} | "
                f"{s['recall10']:.3f} | {s['map10']:.3f} | {s['coverage10']:.3f} | "
                f"{t.status} |"
            )
        lines.append("")
    return "\n".join(lines)


def _ndcg_vector(
    result: EvaluationResult, label: str, method: str
) -> npt.NDArray[np.float64]:
    part = result.per_user
    part = part[
        (part["slice"] == label) & (part["method"] == method) & (part["k"] == PRIMARY_K)
    ].sort_values("user_id")
    return np.asarray(part["ndcg"].to_numpy(dtype=np.float64), dtype=np.float64)


def before_after(
    untuned: EvaluationResult, tuned: EvaluationResult, n_boot: int
) -> pd.DataFrame:
    """NDCG@10 per method and slice before and after tuning, with the paired change."""
    rows = []
    for label in untuned.per_user["slice"].unique():
        for method in ("popularity", "content", "item_knn", "svd", "hybrid"):
            a = _ndcg_vector(untuned, str(label), method)
            b = _ndcg_vector(tuned, str(label), method)
            ma, la, ha = bootstrap_ci(a, n_boot=n_boot)
            mb, lb, hb = bootstrap_ci(b, n_boot=n_boot)
            d, dl, dh = paired_bootstrap_difference(b, a, n_boot=n_boot)
            rows.append(
                {
                    "slice": label,
                    "method": method,
                    "untuned": ma,
                    "untuned_low": la,
                    "untuned_high": ha,
                    "tuned": mb,
                    "tuned_low": lb,
                    "tuned_high": hb,
                    "change": d,
                    "change_low": dl,
                    "change_high": dh,
                }
            )
    return pd.DataFrame(rows)


def run(
    out_dir: Path = OUT_DIR,
    *,
    n_boot: int = DEFAULT_BOOTSTRAPS,
    use_mlflow: bool = True,
    log: Callable[[str], None] = print,
) -> Path:
    data = load_movielens(RAW_DIR)
    split = build_split(data.ratings, data.movies, data.tags)
    data_hash = data_fingerprint(RAW_DIR)
    fit = fit_data(split, data.movies, TARGET)
    ctx = Context(split, fit)
    log(
        f"validation users: warm {len(ctx.cases['warm'])} "
        f"(on the many-ratings rung: {ctx.warm_many}), "
        f"cold-start {len(ctx.cases['cold_start_5'])}"
    )
    start = time.perf_counter()
    outcome = run_stages(ctx, n_boot, log)
    log(
        f"{len(outcome.trials)} configurations tried "
        f"({time.perf_counter() - start:.0f} s)"
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    table = trials_table(outcome.trials)
    table.to_csv(out_dir / "trials.csv", index=False)
    (out_dir / "trials.json").write_text(
        json.dumps(table.to_dict(orient="records"), indent=2)
    )
    payload = config_payload(outcome.settings, outcome.config, data_hash)
    payload["sha256"] = canonical_hash(payload)
    (out_dir / GRID_WINNER_FILE).write_text(
        json.dumps(payload, indent=2, sort_keys=True)
    )

    mlflow_note = "MLflow: not used (--no-mlflow)"
    if use_mlflow:
        try:
            uri = log_to_mlflow(outcome.trials, outcome, data_hash, MLFLOW_DIR)
            mlflow_note = f"MLflow: {len(outcome.trials)} runs logged to {uri}"
        except Exception as error:  # noqa: BLE001 - fall back to the CSV/JSON log
            mlflow_note = f"MLflow FAILED ({error!r}); the CSV/JSON log is the record"
    log(mlflow_note)

    log("full validation comparison, untuned vs tuned settings")
    untuned = evaluate(split, data.movies, TARGET, data_hash=data_hash, n_boot=n_boot)
    tuned = evaluate(
        split,
        data.movies,
        TARGET,
        data_hash=data_hash,
        n_boot=n_boot,
        settings=outcome.settings,
        config=outcome.config,
    )
    changes = before_after(untuned, tuned, n_boot)
    changes.to_csv(out_dir / "before_after_ndcg10.csv", index=False)
    tuned_summary = summarize(tuned.per_user, n_boot=n_boot)
    tuned_summary.to_csv(out_dir / "tuned_summary.csv", index=False)
    tuned_compare = compare(tuned.per_user, n_boot=n_boot)
    tuned_compare.to_csv(out_dir / "tuned_comparisons.csv", index=False)
    (out_dir / "mlflow_note.txt").write_text(mlflow_note + "\n")
    (out_dir / "stage_tables.md").write_text(stage_markdown(outcome.trials))
    log(f"saved to {out_dir}")
    return out_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pmrs.evaluation.tuning")
    parser.add_argument("--out", type=Path, default=OUT_DIR)
    parser.add_argument("--no-mlflow", action="store_true")
    args = parser.parse_args(argv)
    run(args.out, use_mlflow=not args.no_mlflow)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
