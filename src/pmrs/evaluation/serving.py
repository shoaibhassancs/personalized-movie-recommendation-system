"""Step 17: the two local artifacts, their SHA-256 manifest, and the checks on them.

``evaluated_step16``: the exact Step 16 fit (train + validation ratings of eligible
users, cold-start users left out, tags earlier than the author's test cutoff). The
Step 16 test metrics apply to this fit only.

``serving_all_data``: the same frozen configuration fitted on ALL MovieLens ratings
and tags (610 users, including the test-period ratings and the cold-start users). It
was never evaluated, and no metric describes it.

Both are local and git-ignored. Each folder gets ``MANIFEST.sha256`` (SHA-256 of every
file in it), checked before the model is unpickled. Loading a ``.joblib`` runs code:
load only artifacts this project built. The manifest catches damage and mix-ups; it
cannot make an untrusted file safe, because whoever can replace the model can replace
the manifest.

    uv run python -m pmrs.evaluation.serving build
    uv run python -m pmrs.evaluation.serving verify
"""

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Literal

import pandas as pd

from pmrs.data import load_movielens
from pmrs.evaluation.final import FROZEN_FILE, FROZEN_SHA256, check_frozen
from pmrs.evaluation.harness import CLAIM
from pmrs.evaluation.tuning import load_frozen
from pmrs.recommender.artifact import (
    DEFAULT_ARTIFACTS_DIR,
    ArtifactError,
    data_fingerprint,
    load_recommender,
    save_recommender,
    sha256_of,
)
from pmrs.recommender.base import FitData, fit_data, user_history
from pmrs.recommender.recommender import (
    Recommender,
    UserProfile,
    profile_from_history,
)
from pmrs.split import Split, build_interaction_matrix, build_split, evaluation_users

RAW_DIR = Path("data/raw/ml-latest-small")
Kind = Literal["evaluated", "serving"]
NAMES: dict[str, str] = {"evaluated": "evaluated_step16", "serving": "serving_all_data"}
MANIFEST = "MANIFEST.sha256"
PROVENANCE = "provenance.json"
FROZEN_COPY = "frozen_config.json"
CHECKS_FILE = "step17_checks.json"

DESCRIPTIONS: dict[str, str] = {
    "evaluated": (
        "Exact Step 16 fit: train + validation ratings of eligible users; the 20% "
        "cold-start users left out; tags earlier than their author's own test cutoff; "
        "the test period NOT in the fit. The Step 16 test metrics apply to this fit."
    ),
    "serving": (
        "Fitted on ALL MovieLens ratings and tags (every user, including the "
        "test-period ratings and the cold-start users). Never evaluated: the Step 16 "
        "metrics do NOT apply to this artifact."
    ),
}


def serving_fit_data(split: Split, movies: pd.DataFrame) -> FitData:
    """All ratings and all tags. Only for the serving artifact, after Step 16."""
    ordered = movies.set_index("movie_id").reindex(split.item_map.ids).reset_index()
    if ordered["title"].isna().any():
        raise ValueError("every catalogue movie needs a row in ``movies``")
    return FitData(
        matrix=build_interaction_matrix(split.ratings, split.user_map, split.item_map),
        item_map=split.item_map,
        movies=ordered,
        tags=split.tags,
    )


def manifest_lines(directory: Path) -> list[str]:
    names = sorted(p.name for p in directory.iterdir() if p.name != MANIFEST)
    return [f"{sha256_of(directory / n)}  {n}" for n in names]


def verify_manifest(directory: Path) -> None:
    """Raise ``ArtifactError`` unless every listed file matches and none is extra."""
    path = directory / MANIFEST
    if not path.is_file():
        raise ArtifactError(f"no {MANIFEST} in {directory}")
    listed = {}
    for line in path.read_text().splitlines():
        digest, _, name = line.partition("  ")
        listed[name] = digest
    present = {p.name for p in directory.iterdir() if p.name != MANIFEST}
    if present != set(listed):
        raise ArtifactError(f"files differ from the manifest: {present ^ set(listed)}")
    for name, digest in listed.items():
        if sha256_of(directory / name) != digest:
            raise ArtifactError(f"{name} does not match {MANIFEST} (damaged?)")


def load_verified(directory: Path) -> Recommender:
    """Check the manifest and the frozen hash, then load. Trusted artifacts only."""
    verify_manifest(directory)
    provenance = json.loads((directory / PROVENANCE).read_text())
    if provenance.get("frozen_config_sha256") != FROZEN_SHA256:
        raise ArtifactError("artifact was not built from the approved frozen config")
    return load_recommender(directory)


def build(kind: Kind, root: Path = DEFAULT_ARTIFACTS_DIR) -> Path:
    """Build one artifact in a new folder (never overwrites)."""
    check_frozen()
    settings, config = load_frozen(FROZEN_FILE)
    data = load_movielens(RAW_DIR)
    split = build_split(data.ratings, data.movies, data.tags)
    if kind == "evaluated":
        fit = fit_data(split, data.movies, "test")
        target = "test"
    else:
        fit = serving_fit_data(split, data.movies)
        target = "serving_all_data"
    recommender = Recommender.fit(
        fit,
        target=target,
        seed=42,
        config=config,
        settings=settings,
        data_hash=data_fingerprint(RAW_DIR),
    )
    folder = save_recommender(recommender, root / NAMES[kind])
    shutil.copy(FROZEN_FILE, folder / FROZEN_COPY)
    (folder / PROVENANCE).write_text(
        json.dumps(
            {
                "kind": kind,
                "frozen_config_sha256": FROZEN_SHA256,
                "fit_description": DESCRIPTIONS[kind],
                "step16_metrics_apply": kind == "evaluated",
                "contains": (
                    "anonymized MovieLens user IDs and rating histories; no names or "
                    "contact details"
                ),
                "claim": CLAIM,
                "not_evaluated_at": "exactly 11 ratings",
            },
            indent=2,
            sort_keys=True,
        )
    )
    (folder / MANIFEST).write_text("\n".join(manifest_lines(folder)) + "\n")
    return folder


# ---- checks -------------------------------------------------------------------------


def _profile_rows(movie_ids: list[int], rating: float = 4.0) -> UserProfile:
    return UserProfile({m: rating for m in movie_ids})


def run_checks(root: Path = DEFAULT_ARTIFACTS_DIR) -> dict[str, Any]:
    """Load-and-recommend checks and the serving-vs-evaluated diagnostic."""
    results: dict[str, Any] = {}
    checks: dict[str, bool] = {}
    data = load_movielens(RAW_DIR)
    split = build_split(data.ratings, data.movies, data.tags)
    run = json.loads(Path("data/processed/final/test/run.json").read_text())
    models: dict[str, Recommender] = {}
    for kind, name in NAMES.items():
        folder = root / name
        models[kind] = load_verified(folder)  # manifest, frozen hash, model checks
        checks[f"{kind}: manifest and frozen hash verified, model loads"] = True
    ev, sv = models["evaluated"].metadata, models["serving"].metadata
    checks["evaluated: fit counts equal the Step 16 run"] = (
        ev.n_fit_ratings == run["n_fit_ratings"]
        and ev.n_items == run["n_items"]
        and ev.data_hash == run["data_hash"]
    )
    checks["serving: all ratings, all users, all tags"] = (
        sv.n_fit_ratings == len(data.ratings)
        and sv.n_fit_users == data.ratings["user_id"].nunique()
        and sv.n_fit_tags == len(data.tags)
    )
    settings, config = load_frozen(FROZEN_FILE)
    for kind, model in models.items():
        params = model.metadata.model_params
        checks[f"{kind}: frozen settings are in the model"] = (
            params["item_knn"]["neighbours"] == settings.neighbours
            and params["item_knn"]["shrinkage"] == settings.shrinkage
            and params["item_knn"]["min_support"] == settings.min_support
            and params["svd"]["factors"] == settings.factors
            and model.config == config
        )
    ids = [int(m) for m in split.item_map.ids[:40]]
    for kind, model in models.items():
        popular = model.recommend(UserProfile(), "popularity", k=10).movie_ids
        for n, rung in (
            (0, "no_ratings"),
            (3, "few_ratings"),
            (5, "few_ratings"),
            (10, "few_ratings"),
            (11, "many_ratings"),
            (20, "many_ratings"),
        ):
            profile = _profile_rows(ids[:n])
            listing = model.recommend(profile, "hybrid", k=10)
            ok = listing.branch == rung and len(listing.items) == 10
            ok = ok and not set(listing.movie_ids) & set(ids[:n])
            ok = ok and set(listing.movie_ids) <= {int(m) for m in split.item_map.ids}
            ok = ok and all(i.explanation for i in listing.items)
            if rung == "few_ratings":  # frozen: popularity fallback
                pop = model.recommend(profile, "popularity", k=10).movie_ids
                ok = ok and listing.movie_ids == pop
            if n == 0:
                ok = ok and listing.movie_ids == popular
            checks[f"{kind}: {n} ratings -> {rung}"] = ok
        genre = model.recommend(UserProfile(genres=("Comedy",)), "hybrid", k=10)
        checks[f"{kind}: 0 ratings with a genre uses the genre mix"] = (
            genre.branch == "no_ratings"
            and any(i.evidence.kind == "genre_popularity" for i in genre.items)
        )
    # evaluated artifact == the same fit rebuilt in memory (save/load fidelity)
    rebuilt = Recommender.fit(
        fit_data(split, data.movies, "test"),
        target="test",
        seed=42,
        config=config,
        settings=settings,
    )
    users = [int(u) for u in evaluation_users(split, "test", "warm")[:40]]
    same = 0
    overlaps: list[float] = []
    differing = 0
    for user in users:
        profile = profile_from_history(
            user_history(split, user, "test"), split.item_map
        )
        a = models["evaluated"].recommend(profile, "hybrid", k=20).movie_ids
        b = rebuilt.recommend(profile, "hybrid", k=20).movie_ids
        same += a == b
        c = models["serving"].recommend(profile, "hybrid", k=10).movie_ids
        overlap = len(set(a[:10]) & set(c)) / 10
        overlaps.append(overlap)
        differing += a[:10] != c
    checks["evaluated: lists equal an in-memory refit (40 warm users)"] = same == len(
        users
    )
    results["diagnostic_only"] = {
        "note": (
            "Same train + validation profile given to both artifacts. Different lists "
            "are expected because the serving model used more data. This is not a "
            "quality measure."
        ),
        "users": len(users),
        "lists_with_any_difference": differing,
        "mean_top10_overlap": round(sum(overlaps) / len(overlaps), 3),
        "min_top10_overlap": min(overlaps),
    }
    results["checks"] = checks
    results["all_pass"] = all(checks.values())
    results["sizes_bytes"] = {
        kind: sum(p.stat().st_size for p in (root / name).iterdir())
        for kind, name in NAMES.items()
    }
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pmrs.evaluation.serving")
    parser.add_argument("command", choices=("build", "verify"))
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            for kind in ("evaluated", "serving"):
                print(f"saved {build(kind)}")
            return 0
        results = run_checks()
        out = DEFAULT_ARTIFACTS_DIR / CHECKS_FILE
        out.write_text(json.dumps(results, indent=2, sort_keys=True))
        for name, ok in results["checks"].items():
            print(f"{'PASS' if ok else 'FAIL'}  {name}")
        print(json.dumps(results["diagnostic_only"], indent=2))
        print("sizes (bytes):", results["sizes_bytes"])
        return 0 if results["all_pass"] else 1
    except (ArtifactError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
