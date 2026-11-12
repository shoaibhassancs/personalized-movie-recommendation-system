"""``uv run python -m pmrs.evaluation``: compare every method on the validation period.

Only the validation period is offered here. The test period is read once, by the final
evaluation (Step 16), after the configuration is frozen.
"""

import argparse
import time
from pathlib import Path

from pmrs.data import load_movielens
from pmrs.evaluation.harness import compare, evaluate, summarize
from pmrs.evaluation.report import DEFAULT_OUT, format_report, save_result
from pmrs.recommender.artifact import data_fingerprint
from pmrs.split import build_split

RAW_DIR = Path("data/raw/ml-latest-small")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pmrs.evaluation")
    parser.add_argument("--target", choices=("validation",), default="validation")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    data = load_movielens(RAW_DIR)
    split = build_split(data.ratings, data.movies, data.tags)
    start = time.perf_counter()
    result = evaluate(
        split, data.movies, args.target, data_hash=data_fingerprint(RAW_DIR)
    )
    summary = summarize(result.per_user)
    comparisons = compare(result.per_user)
    report = format_report(result, summary, comparisons)
    folder = save_result(result, summary, comparisons, report, args.out)
    print(report)
    print(f"\nsaved to {folder} ({time.perf_counter() - start:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
