"""Step 12 command line: build an artifact, then ask it for recommendations.

    uv run python -m pmrs.recommender.cli build --target validation
    uv run python -m pmrs.recommender.cli recommend \
        --artifact data/processed/artifacts/validation \
        --ratings 318:5,296:4.5 --strategy hybrid -k 10

``build`` never overwrites an artifact. ``recommend`` loads a pickle, so it only loads
artifacts this project built (the warning is printed every time).
"""

import argparse
import sys
from pathlib import Path

from pmrs.data import load_movielens
from pmrs.recommender.artifact import (
    DEFAULT_ARTIFACTS_DIR,
    ArtifactError,
    data_fingerprint,
    load_recommender,
    save_recommender,
)
from pmrs.recommender.base import fit_data
from pmrs.recommender.recommender import (
    STRATEGIES,
    TRUSTED_ARTIFACT_WARNING,
    Recommender,
    UserProfile,
)
from pmrs.split import Target, build_split

RAW_DIR = Path("data/raw/ml-latest-small")


def parse_ratings(text: str) -> dict[int, float]:
    """``"318:5,296:4.5"`` to ``{318: 5.0, 296: 4.5}``; empty text gives no ratings."""
    ratings: dict[int, float] = {}
    for part in filter(None, (p.strip() for p in text.split(","))):
        movie, _, value = part.partition(":")
        if not value:
            raise ValueError(f"expected movie_id:rating, got {part!r}")
        movie_id = int(movie)
        if movie_id in ratings:
            raise ValueError(f"movie {movie_id} is rated twice")
        ratings[movie_id] = float(value)
    return ratings


def parse_genres(text: str) -> tuple[str, ...]:
    return tuple(g.strip() for g in text.split(",") if g.strip())


def build(target: Target, name: str) -> Path:
    data = load_movielens(RAW_DIR)
    split = build_split(data.ratings, data.movies, data.tags)
    fit = fit_data(split, data.movies, target)
    recommender = Recommender.fit(
        fit, target=target, data_hash=data_fingerprint(RAW_DIR)
    )
    return save_recommender(recommender, DEFAULT_ARTIFACTS_DIR / name)


def recommend(args: argparse.Namespace) -> None:
    print(f"WARNING: {TRUSTED_ARTIFACT_WARNING}", file=sys.stderr)
    recommender = load_recommender(Path(args.artifact))
    profile = UserProfile(parse_ratings(args.ratings), parse_genres(args.genres))
    result = recommender.recommend(profile, strategy=args.strategy, k=args.k)
    branch = f", ladder rung: {result.branch}" if result.branch else ""
    print(f"strategy: {result.strategy}{branch}; score: {result.score_kind}")
    for note in result.notes:
        print(f"note: {note}")
    for rank, item in enumerate(result.items, start=1):
        score = "n/a" if item.score is None else f"{item.score:.3f}"
        print(f"{rank:>2}. {item.title}  [{'|'.join(item.genres)}]  score {score}")
        print(f"      {item.explanation}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pmrs.recommender.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="fit all models and save them")
    build_parser.add_argument("--target", choices=("validation", "test"), required=True)
    build_parser.add_argument("--name", help="folder name (default: the target)")
    ask = commands.add_parser("recommend", help="recommend from a saved artifact")
    ask.add_argument("--artifact", required=True, help="a trusted artifact folder")
    ask.add_argument("--ratings", default="", help="movie_id:rating,movie_id:rating")
    ask.add_argument("--genres", default="", help="favourite genres, comma separated")
    ask.add_argument("--strategy", choices=STRATEGIES, default="hybrid")
    ask.add_argument("-k", type=int, default=10)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            print(f"saved {build(args.target, args.name or args.target)}")
        else:
            recommend(args)
    except (ArtifactError, ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
