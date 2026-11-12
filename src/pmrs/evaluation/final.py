"""Step 16: the final evaluation of the frozen configuration.

``uv run python -m pmrs.evaluation.final --target validation`` is a dry run (writes to
``data/processed/final_dryrun/``). ``--target test --read-test-once`` reads the test
period, once: it refuses if a test result folder already exists.

This is the only module that passes ``allow_test=True``. It cannot tune: it loads the
frozen file, checks its hash against the value the owner approved (D-031), and makes one
call to ``evaluate``. Claim limit: methods compared under the same per-user holdout
protocol; not leakage-safe, not a prediction of future behaviour.
"""

import argparse
import json
import time
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.graph_objects as go  # type: ignore[import-untyped]
from plotly.subplots import make_subplots  # type: ignore[import-untyped]

from pmrs.data import load_movielens
from pmrs.evaluation.harness import (
    CLAIM,
    PRIMARY_K,
    PRIMARY_METRIC,
    compare,
    evaluate,
    summarize,
)
from pmrs.evaluation.report import format_report, save_result
from pmrs.evaluation.tuning import canonical_hash, load_frozen
from pmrs.recommender.artifact import data_fingerprint
from pmrs.split import Split, build_split
from pmrs.split.protocol import Target

RAW_DIR = Path("data/raw/ml-latest-small")
FROZEN_FILE = Path("data/processed/tuning/proposed_frozen_config.json")
FROZEN_SHA256 = "e68a7ee613e27719e7369f592ce438cd8fb7b4ff5887a55af4ce39d5eecce2b5"
FINAL_DIR = Path("data/processed/final")
DRYRUN_DIR = Path("data/processed/final_dryrun")

CHART_METHODS = (
    "random",
    "popularity",
    "bayesian_average",
    "content",
    "item_knn",
    "svd",
    "hybrid",
)
COLD_SLICES = ("cold_start_0", "cold_start_3", "cold_start_5", "cold_start_10")


def check_frozen(path: Path = FROZEN_FILE, expected: str = FROZEN_SHA256) -> None:
    """Refuse to run unless the file is the approved, frozen configuration."""
    raw = json.loads(path.read_text())
    if not str(raw.get("status", "")).startswith("FROZEN"):
        raise RuntimeError(f"{path} is not marked FROZEN; the owner must freeze it")
    if raw.get("sha256") != expected or canonical_hash(raw) != expected:
        raise RuntimeError(f"{path} does not match the approved hash {expected}")
    load_frozen(path)  # also checks the hash and that the file parses


def guard_target(target: Target, read_test_once: bool, out_dir: Path) -> Path:
    """Where results go; raises before any data is read if a test read is barred."""
    if target != "test":
        return out_dir / "validation"
    if not read_test_once:
        raise RuntimeError("the test period needs --read-test-once")
    folder = out_dir / "test"
    if folder.exists():
        raise RuntimeError(f"{folder} already exists: the test period is read once")
    return folder


# ---- charts -------------------------------------------------------------------------


def _at(summary: pd.DataFrame, label: str, k: int = PRIMARY_K) -> pd.DataFrame:
    part = summary[(summary["slice"] == label) & (summary["k"] == k)]
    return part.set_index("method").reindex(
        [m for m in CHART_METHODS if m in set(part["method"])]
    )


def _bars(frame: pd.DataFrame, value: str, low: str, high: str) -> dict[str, Any]:
    return {
        "x": list(frame.index),
        "y": frame[value],
        "error_y": {
            "type": "data",
            "symmetric": False,
            "array": frame[high] - frame[value],
            "arrayminus": frame[value] - frame[low],
        },
    }


def make_charts(
    summary: pd.DataFrame, comparisons: pd.DataFrame, coverage: pd.DataFrame
) -> dict[str, go.Figure]:
    """Five figures; every number plotted is a row of the saved CSV files."""
    note = "95% bootstrap intervals over users (sampling noise only)"
    figures: dict[str, go.Figure] = {}

    warm = _at(summary, "warm")
    fig = go.Figure(go.Bar(**_bars(warm, "ndcg", "ndcg_low", "ndcg_high")))
    fig.update_layout(
        title=f"Warm users: NDCG@{PRIMARY_K} by method<br><sup>{note}</sup>",
        yaxis_title=f"NDCG@{PRIMARY_K}",
    )
    figures["ndcg_warm"] = fig

    fig = go.Figure()
    for method in CHART_METHODS:
        rows = [
            summary[
                (summary["slice"] == s)
                & (summary["k"] == PRIMARY_K)
                & (summary["method"] == method)
            ]
            for s in COLD_SLICES
        ]
        if any(r.empty for r in rows):
            continue
        part = pd.concat(rows)
        fig.add_trace(
            go.Scatter(
                x=[int(s.rsplit("_", 1)[1]) for s in COLD_SLICES],
                y=part["ndcg"],
                mode="lines+markers",
                name=method,
                error_y={
                    "type": "data",
                    "symmetric": False,
                    "array": part["ndcg_high"] - part["ndcg"],
                    "arrayminus": part["ndcg"] - part["ndcg_low"],
                },
            )
        )
    fig.update_layout(
        title=(
            f"Cold-start SIMULATION: NDCG@{PRIMARY_K} by revealed ratings<br>"
            f"<sup>hybrid = popularity fallback for 0-10 ratings (D-030); {note}</sup>"
        ),
        xaxis_title="revealed ratings",
        yaxis_title=f"NDCG@{PRIMARY_K}",
    )
    figures["ndcg_cold_start"] = fig

    diffs = comparisons[
        (comparisons["slice"] == "warm") & (comparisons["reference"] == "popularity")
    ].set_index("method")
    fig = go.Figure(go.Bar(**_bars(diffs, "difference", "low", "high")))
    fig.add_hline(y=0, line_dash="dash")
    fig.update_layout(
        title=(
            f"Warm users: paired NDCG@{PRIMARY_K} difference vs popularity<br>"
            f"<sup>{note}</sup>"
        ),
        yaxis_title="method minus popularity",
    )
    figures["paired_vs_popularity_warm"] = fig

    fig = make_subplots(
        rows=1, cols=4, subplot_titles=("precision", "recall", "map", "ndcg")
    )
    for col, metric in enumerate(("precision", "recall", "map", "ndcg"), start=1):
        for method in CHART_METHODS:
            part = summary[(summary["slice"] == "warm") & (summary["method"] == method)]
            part = part.sort_values("k")
            fig.add_trace(
                go.Scatter(
                    x=part["k"],
                    y=part[metric],
                    mode="lines+markers",
                    name=method,
                    legendgroup=method,
                    showlegend=col == 1,
                ),
                row=1,
                col=col,
            )
        fig.update_xaxes(title_text="K", row=1, col=col)
    fig.update_layout(title="Warm users: ranking metrics across K (means)")
    figures["metrics_across_k_warm"] = fig

    cover = coverage[(coverage["slice"] == "warm") & (coverage["k"] == PRIMARY_K)]
    both = warm.join(cover.set_index("method")["coverage"])
    fig = go.Figure(
        go.Scatter(
            x=both["coverage"],
            y=both["ndcg"],
            mode="markers+text",
            text=list(both.index),
            textposition="top center",
        )
    )
    fig.update_layout(
        title=f"Warm users: catalogue coverage vs NDCG@{PRIMARY_K}",
        xaxis_title=f"catalogue coverage @{PRIMARY_K}",
        yaxis_title=f"NDCG@{PRIMARY_K}",
    )
    figures["coverage_vs_ndcg_warm"] = fig
    return figures


def write_charts(figures: dict[str, go.Figure], folder: Path) -> list[str]:
    charts = folder / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    names = []
    for name, fig in figures.items():
        # plotly.min.js is written once beside the charts; nothing is fetched
        fig.write_html(charts / f"{name}.html", include_plotlyjs="directory")
        names.append(f"charts/{name}.html")
    return names


# ---- run ----------------------------------------------------------------------------


def run(
    target: Target,
    *,
    read_test_once: bool = False,
    out_dir: Path | None = None,
    frozen: Path = FROZEN_FILE,
    expected: str = FROZEN_SHA256,
    split: Split | None = None,
    movies: pd.DataFrame | None = None,
    data_hash: str | None = None,
    n_boot: int | None = None,
) -> Path:
    """Evaluate the frozen configuration on ``target`` and write everything."""
    base = out_dir or (FINAL_DIR if target == "test" else DRYRUN_DIR)
    folder = guard_target(target, read_test_once, base)
    check_frozen(frozen, expected)
    settings, config = load_frozen(frozen)
    if split is None or movies is None:
        data = load_movielens(RAW_DIR)
        movies = data.movies
        split = build_split(data.ratings, data.movies, data.tags)
    fingerprint = data_hash if data_hash is not None else data_fingerprint(RAW_DIR)
    extra: dict[str, Any] = {} if n_boot is None else {"n_boot": n_boot}
    result = evaluate(
        split,
        movies,
        target,
        allow_test=(target == "test"),
        data_hash=fingerprint,
        settings=settings,
        config=config,
        **extra,
    )
    summary = summarize(result.per_user, **extra)
    comparisons = compare(result.per_user, **extra)
    report = format_report(result, summary, comparisons)
    saved = save_result(result, summary, comparisons, report, folder.parent)
    names = write_charts(make_charts(summary, comparisons, result.coverage), saved)
    (saved / "frozen_config.json").write_text(frozen.read_text())
    (saved / "final_run.json").write_text(
        json.dumps(
            {
                "target": target,
                "frozen_config_sha256": expected,
                "claim": CLAIM,
                "charts": names,
                "headline": f"{PRIMARY_METRIC}@{PRIMARY_K}",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pmrs.evaluation.final")
    parser.add_argument("--target", choices=("validation", "test"), required=True)
    parser.add_argument("--read-test-once", action="store_true")
    args = parser.parse_args(argv)
    start = time.perf_counter()
    saved = run(args.target, read_test_once=args.read_test_once)
    print((saved / "report.txt").read_text())
    print(f"saved to {saved} ({time.perf_counter() - start:.0f} s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
