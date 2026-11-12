"""Step 14 report: readable tables, saved files, and the claim printed with them."""

import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from pmrs.evaluation.harness import (
    CLAIM,
    KS,
    PRIMARY_K,
    PRIMARY_METRIC,
    EvaluationResult,
)
from pmrs.recommender.recommender import library_versions

DEFAULT_OUT = Path("data/processed/evaluation")

SLICE_TITLES = {
    "warm": "warm users (their own pre-cutoff ratings are the history)",
    "cold_start_0": "cold-start SIMULATION, 0 revealed ratings",
    "cold_start_3": "cold-start SIMULATION, 3 revealed ratings",
    "cold_start_5": "cold-start SIMULATION, 5 revealed ratings",
    "cold_start_10": "cold-start SIMULATION, 10 revealed ratings",
}


def _ci(row: pd.Series, name: str) -> str:
    return f"{row[name]:.3f} [{row[f'{name}_low']:.3f}, {row[f'{name}_high']:.3f}]"


def _slice_table(
    label: str, summary: pd.DataFrame, coverage: pd.DataFrame
) -> list[str]:
    at_k = summary[(summary["slice"] == label) & (summary["k"] == PRIMARY_K)]
    cover = coverage[(coverage["slice"] == label) & (coverage["k"] == PRIMARY_K)]
    lines = [
        f"  {'method':<17} {'NDCG@10 [95% CI]':<24} {'Prec@10':>8} {'Rec@10':>8} "
        f"{'MAP@10':>8} {'diversity':>9} {'coverage':>9}"
    ]
    for _, row in at_k.iterrows():
        covered = cover[cover["method"] == row["method"]]["coverage"].iloc[0]
        lines.append(
            f"  {row['method']:<17} {_ci(row, PRIMARY_METRIC):<24} "
            f"{row['precision']:>8.3f} {row['recall']:>8.3f} {row['map']:>8.3f} "
            f"{row['diversity']:>9.3f} {covered:>9.3f}"
        )
    other = summary[(summary["slice"] == label) & (summary["k"] != PRIMARY_K)]
    for k in (k for k in KS if k != PRIMARY_K):
        part = other[other["k"] == k]
        cells = ", ".join(
            f"{r['method']} {r[PRIMARY_METRIC]:.3f}" for _, r in part.iterrows()
        )
        lines.append(f"  NDCG@{k} means: {cells}")
    return lines


def format_report(
    result: EvaluationResult,
    summary: pd.DataFrame,
    comparisons: pd.DataFrame,
) -> str:
    """The plain-text report for one run."""
    stage = (
        "VALIDATION period (tuning data; the test period was not read)"
        if result.target == "validation"
        else "TEST period (final, read once)"
    )
    lines = [
        f"EVALUATION: {stage}",
        f"Claim limit: {CLAIM}",
        "Evaluated users: "
        + ", ".join(f"{k} {v}" for k, v in result.users_per_slice.items()),
        f"Headline metric (chosen in advance): NDCG@{PRIMARY_K}. All other numbers are "
        "supporting detail; with this many comparisons some intervals will look "
        "decisive by chance.",
        "Intervals: 95% bootstrap over users (sampling noise only).",
    ]
    for label, title in SLICE_TITLES.items():
        if label not in result.users_per_slice:
            continue
        lines += ["", f"== {title}: {result.users_per_slice[label]} users =="]
        lines += _slice_table(label, summary, result.coverage)
        diffs = comparisons[comparisons["slice"] == label]
        if len(diffs):
            lines.append(f"  Paired NDCG@{PRIMARY_K} difference (method - reference):")
            for _, d in diffs.iterrows():
                flag = (
                    "interval excludes 0" if d["interval_excludes_zero"] else "spans 0"
                )
                lines.append(
                    f"    {d['method']:<16} vs {d['reference']:<17} "
                    f"{d['difference']:+.3f} [{d['low']:+.3f}, {d['high']:+.3f}] "
                    f"{flag}"
                )
    errors = result.rating_errors
    lines += ["", "== rating error on warm users' held-out ratings (secondary) =="]
    lines.append(f"  {'predictor':<17} {'RMSE [95% CI]':<24} {'MAE [95% CI]':<24}")
    for _, row in errors.iterrows():
        lines.append(
            f"  {row['method']:<17} {_ci(row, 'rmse'):<24} {_ci(row, 'mae'):<24}"
        )
    lines += [
        "  (lower is better; global_mean and user_mean are references, not models; the "
        "ranking-only methods have no rating prediction)",
    ]
    return "\n".join(lines)


def save_result(
    result: EvaluationResult,
    summary: pd.DataFrame,
    comparisons: pd.DataFrame,
    report: str,
    directory: Path = DEFAULT_OUT,
) -> Path:
    """Write the per-user table, summaries, report and run information."""
    folder = directory / result.target
    folder.mkdir(parents=True, exist_ok=True)
    result.per_user.to_csv(folder / "per_user.csv", index=False)
    summary.to_csv(folder / "summary.csv", index=False)
    comparisons.to_csv(folder / "comparisons.csv", index=False)
    result.coverage.to_csv(folder / "coverage.csv", index=False)
    result.rating_errors.to_csv(folder / "rating_errors.csv", index=False)
    (folder / "report.txt").write_text(report + "\n")
    info = {
        **result.info,
        "created_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "libraries": library_versions(),
    }
    (folder / "run.json").write_text(json.dumps(info, indent=2, sort_keys=True))
    return folder
