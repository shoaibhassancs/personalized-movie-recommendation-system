"""Step 15, after the grid: the owner's choices, applied on top of the grid winner.

The grid (``tuning.py``) produced a *grid winner*. The owner then made four decisions
from the validation results (D-030). They are recorded here as decisions, not as
tuning results:

1. Users with 1 to 10 ratings get pure popularity. The tuned SVD/popularity blend tied
   popularity on NDCG@10 and showed no clear measured advantage. This is outside the
   approved grid and is the owner's call.
2. The cold-start simulation at 0, 3, 5 and 10 revealed ratings therefore uses
   popularity (at 3 and 5 it tied the hybrid; at 10 the hybrid was worse). Warm users
   keep the 10+ hybrid. In code this is one ladder: ``few_max = 10`` with
   popularity-only weights, so a user with 11 or more ratings gets the hybrid. Every
   warm user has 12 or more ratings, so no warm user is affected by the boundary. 11
   ratings was never evaluated.
3. Warm-user hybrid weights, SVD factors, content weights and item-kNN settings stay as
   the grid winner chose them. Item-kNN minimum support stays at 20; nothing above 20
   was searched.
4. The zero-rating favourite-genre mix (0.6 / 0.4) stays provisional and untuned.
"""

import json
from pathlib import Path
from typing import Any

from pmrs.evaluation.tuning import (
    GRID_WINNER_FILE,
    OUT_DIR,
    canonical_hash,
    load_frozen,
)
from pmrs.recommender.hybrid import HybridConfig
from pmrs.recommender.settings import ModelSettings

SELECTED_FILE = "proposed_frozen_config.json"
POPULARITY_ONLY = {"content": 0.0, "item_knn": 0.0, "svd": 0.0, "popularity": 1.0}
FALLBACK_MAX_RATINGS = 10  # 1..10 ratings: popularity; 11 and up: the hybrid

PROVENANCE = {
    "item_knn neighbours / shrinkage": "tuning-grid winner (validation)",
    "item_knn min_support = 20": (
        "tuning-grid winner (validation); owner: keep 20 for comparison, do not "
        "search above 20"
    ),
    "svd factors = 50": "default kept: no grid value was clearly better (validation)",
    "content weights (all 1.0)": "default kept: inconclusive (validation)",
    "warm 10+ hybrid weights": (
        "default kept: best alternative inconclusive (validation); owner: keep"
    ),
    "1-10 ratings rung = pure popularity": (
        "OWNER DECISION based on validation, not a tuning-grid winner: the tuned "
        "SVD/popularity blend tied popularity on NDCG@10 with no clear advantage"
    ),
    "cold-start 0/3/5/10 revealed": (
        "OWNER DECISION based on validation: popularity (tied the hybrid at 3 and 5; "
        "the hybrid was worse at 10)"
    ),
    "0-rating genre/popularity mix 0.6/0.4": (
        "provisional and untuned (owner decision): MovieLens cannot measure the value "
        "of onboarding genre choices"
    ),
}


def apply_owner_decisions(
    settings: ModelSettings, grid_config: HybridConfig
) -> tuple[ModelSettings, HybridConfig]:
    """Grid winner plus the owner's popularity fallback; nothing else changes."""
    return settings, HybridConfig(
        few_max=FALLBACK_MAX_RATINGS,
        genre_weight=grid_config.genre_weight,
        popularity_weight=grid_config.popularity_weight,
        few_weights=dict(POPULARITY_ONLY),
        many_weights=dict(grid_config.many_weights),
    )


def selected_payload(
    settings: ModelSettings, config: HybridConfig, grid: dict[str, Any]
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": (
            "PROPOSED - not frozen until the owner approves; this is not Step 16 "
            "and the test period has not been read"
        ),
        "chosen_on": "validation period only",
        "claim": grid["claim"],
        "data_hash": grid["data_hash"],
        "seed": grid["seed"],
        "settings": settings.to_dict(),
        "hybrid": {
            "few_max": config.few_max,
            "genre_weight": config.genre_weight,
            "popularity_weight": config.popularity_weight,
            "few_weights": config.few_weights,
            "many_weights": config.many_weights,
        },
        "routing": {
            "0 ratings": "genre/popularity mix if genres are given, else popularity",
            f"1 to {config.few_max} ratings": (
                "popularity (cold-start fallback; includes the cold-start simulation "
                "at 3, 5 and 10 revealed)"
            ),
            f"{config.few_max + 1}+ ratings": "warm-user hybrid (many_weights)",
        },
        "provenance": PROVENANCE,
        "grid_winner_sha256": grid["sha256"],
    }
    payload["sha256"] = canonical_hash(payload)
    return payload


def write_selected(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    grid_path = out_dir / GRID_WINNER_FILE
    settings, grid_config = load_frozen(grid_path)  # checks the grid file's hash
    existing = out_dir / SELECTED_FILE
    if existing.exists() and json.loads(existing.read_text())["status"].startswith(
        "FROZEN"
    ):
        raise RuntimeError(f"{existing} is frozen (D-031); it is never rewritten")
    grid = json.loads(grid_path.read_text())
    settings, config = apply_owner_decisions(settings, grid_config)
    payload = selected_payload(settings, config, grid)
    (out_dir / SELECTED_FILE).write_text(json.dumps(payload, indent=2, sort_keys=True))
    return payload


# ---- validation checks of the selected configuration --------------------------------


def verify(out_dir: Path = OUT_DIR) -> list[tuple[str, bool, str]]:
    """Validation-only checks that the selected configuration routes users as decided.

    Returns (check, passed, detail). Uses the validation period only; the saved
    grid-winner run (``tuned_summary.csv``) is the reference for "unchanged".
    """
    import numpy as np
    import pandas as pd

    from pmrs.data import load_movielens
    from pmrs.evaluation.harness import all_slices, compare, evaluate, summarize
    from pmrs.evaluation.tuning import RAW_DIR, TARGET
    from pmrs.recommender.artifact import data_fingerprint
    from pmrs.recommender.base import fit_data, user_history
    from pmrs.recommender.recommender import Recommender, UserProfile
    from pmrs.split import build_split, evaluation_users

    results: list[tuple[str, bool, str]] = []

    def check(name: str, passed: bool, detail: str) -> None:
        results.append((name, bool(passed), detail))

    settings, config = load_frozen(out_dir / SELECTED_FILE)
    grid_settings, grid_config = load_frozen(out_dir / GRID_WINNER_FILE)
    check(
        "selected file loads and its SHA-256 matches",
        True,
        "load_frozen verified the hash",
    )
    check(
        "settings equal the grid winner (min_support stays 20)",
        settings == grid_settings and settings.min_support == 20,
        f"neighbours {settings.neighbours}, shrinkage {settings.shrinkage:g}, "
        f"min_support {settings.min_support}, factors {settings.factors}",
    )
    check(
        "warm 10+ weights equal the grid winner; 1-10 rung is pure popularity",
        config.many_weights == grid_config.many_weights
        and config.few_weights == POPULARITY_ONLY
        and config.few_max == FALLBACK_MAX_RATINGS
        and (config.genre_weight, config.popularity_weight) == (0.6, 0.4),
        f"few_max {config.few_max}, few {config.few_weights}, "
        f"many {config.many_weights}",
    )

    data = load_movielens(RAW_DIR)
    split = build_split(data.ratings, data.movies, data.tags)
    data_hash = data_fingerprint(RAW_DIR)

    # routing, by the rung each evaluated user lands on
    branches: dict[str, set[str]] = {}
    sizes: dict[str, list[int]] = {}
    for part in all_slices():
        users = evaluation_users(split, TARGET, part.group)
        found = [
            len(user_history(split, int(u), TARGET, part.history_size)) for u in users
        ]
        sizes[part.label] = found
        branches[part.label] = {config.branch(n) for n in found}
    expected = {
        "warm": {"many_ratings"},
        "cold_start_0": {"no_ratings"},
        "cold_start_3": {"few_ratings"},
        "cold_start_5": {"few_ratings"},
        "cold_start_10": {"few_ratings"},
    }
    check(
        "every evaluated user lands on the intended rung",
        branches == expected,
        f"{ {k: sorted(v) for k, v in branches.items()} }; warm histories "
        f"{min(sizes['warm'])} to {max(sizes['warm'])} ratings "
        f"(n={len(sizes['warm'])})",
    )

    result = evaluate(
        split,
        data.movies,
        TARGET,
        data_hash=data_hash,
        settings=settings,
        config=config,
    )
    for label in ("cold_start_0", "cold_start_3", "cold_start_5", "cold_start_10"):
        same = all(
            np.array_equal(h, p)
            for h, p in zip(
                result.lists[(label, "hybrid")],
                result.lists[(label, "popularity")],
                strict=True,
            )
        )
        check(
            f"{label}: every hybrid list equals the popularity list",
            same,
            f"{len(result.lists[(label, 'hybrid')])} users, top-20 compared",
        )
    summary = summarize(result.per_user)
    comparisons = compare(result.per_user)
    diffs = comparisons[
        (comparisons["method"] == "hybrid")
        & (comparisons["reference"] == "popularity")
        & comparisons["slice"].str.startswith("cold")
    ]
    check(
        "cold-start NDCG@10 difference, hybrid minus popularity, is exactly 0",
        bool((diffs[["difference", "low", "high"]].abs() < 1e-12).all().all()),
        "; ".join(
            f"{r.slice} {r.difference:+.4f} [{r.low:+.4f}, {r.high:+.4f}]"
            for r in diffs.itertuples()
        ),
    )

    saved = pd.read_csv(out_dir / "tuned_summary.csv")
    keys = ["slice", "method", "k"]
    metrics = ["precision", "recall", "map", "ndcg"]
    merged = summary.merge(saved, on=keys, suffixes=("", "_saved"))
    for method in ("popularity", "content", "item_knn", "svd", "bayesian_average"):
        rows = merged[merged["method"] == method]
        gap = max(float((rows[m] - rows[f"{m}_saved"]).abs().max()) for m in metrics)
        check(
            f"{method}: unchanged from the saved grid-winner run",
            gap < 1e-12,
            f"max gap {gap:.1e}",
        )
    warm = merged[(merged["method"] == "hybrid") & (merged["slice"] == "warm")]
    gap = max(float((warm[m] - warm[f"{m}_saved"]).abs().max()) for m in metrics)
    check(
        "warm hybrid: identical to the saved grid-winner run",
        gap < 1e-12,
        f"max gap {gap:.1e}; NDCG@10 "
        f"{float(warm[warm['k'] == 10]['ndcg'].iloc[0]):.4f}",
    )

    # the zero-rating genre path is untouched
    rec = Recommender.fit(
        fit_data(split, data.movies, TARGET),
        target=TARGET,
        settings=settings,
        config=config,
    )
    with_genres = rec.recommend(UserProfile(genres=("sci-fi",)), "hybrid", k=5)
    plain = rec.recommend(UserProfile(), "hybrid", k=5)
    check(
        "0 ratings: favourite genres still use the genre/popularity mix",
        with_genres.branch == "no_ratings"
        and all(i.evidence.kind == "genre_popularity" for i in with_genres.items),
        f"branch {with_genres.branch}; kinds "
        f"{sorted({i.evidence.kind for i in with_genres.items})}",
    )
    check(
        "0 ratings, no genres: popularity",
        plain.branch == "no_ratings"
        and all(i.evidence.kind == "popularity" for i in plain.items),
        f"kinds {sorted({i.evidence.kind for i in plain.items})}",
    )
    top3 = rec.recommend(UserProfile(), "popularity", k=3).movie_ids
    three = {int(m): 4.0 for m in top3}
    short = rec.recommend(UserProfile(three), "hybrid", k=5)
    check(
        "3 ratings: popularity rung, popularity explanations",
        short.branch == "few_ratings"
        and all(i.evidence.kind == "popularity" for i in short.items),
        f"branch {short.branch}; "
        f"kinds {sorted({i.evidence.kind for i in short.items})}",
    )

    summary.to_csv(out_dir / "selected_summary.csv", index=False)
    comparisons.to_csv(out_dir / "selected_comparisons.csv", index=False)
    (out_dir / "selected_checks.json").write_text(
        json.dumps(
            [{"check": c, "passed": p, "detail": d} for c, p, d in results], indent=2
        )
    )
    return results


def main() -> int:
    payload = write_selected()
    print(f"wrote {OUT_DIR / SELECTED_FILE} (sha256 {payload['sha256']})")
    failed = 0
    for name, passed, detail in verify():
        failed += not passed
        print(f"{'PASS' if passed else 'FAIL'}  {name}\n      {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
