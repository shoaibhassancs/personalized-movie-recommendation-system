"""Feasibility tables for the per-user holdout, and saving the split to disk.

Run ``uv run python -m pmrs.split`` to build the split from ``data/raw/ml-latest-small``
and
write ``data/processed/split/`` (git-ignored). Everything printed is measured on the
data.
"""

from pathlib import Path

import numpy as np
import pandas as pd

from pmrs.data import load_movielens
from pmrs.split.holdout import MIN_TRAIN_RATINGS, PERIOD_ORDER, RELEVANT_THRESHOLD
from pmrs.split.protocol import (
    HISTORY_SIZES,
    Group,
    Split,
    Target,
    build_split,
    candidate_items,
    evaluation_users,
    fit_ratings,
    fit_tags,
    heldout_relevant_items,
)

TARGETS: tuple[Target, Target] = ("validation", "test")
GROUPS: tuple[Group, Group] = ("warm", "cold_start")


def _periods_table(split: Split) -> pd.DataFrame:
    ratings = split.ratings
    months = pd.to_datetime(ratings["timestamp"], unit="s").dt.to_period("M")
    rows = {}
    for name in PERIOD_ORDER:
        in_period = ratings["period"] == name
        shares = months[in_period].value_counts(normalize=True)
        rows[name] = {
            "ratings": int(in_period.sum()),
            "relevant_ratings": int(
                (in_period & (ratings["rating"] >= RELEVANT_THRESHOLD)).sum()
            ),
            "users_with_ratings": int(ratings.loc[in_period, "user_id"].nunique()),
            "distinct_months": int(shares.size),
            "top_month_share_pct": round(100 * float(shares.iloc[0]), 1),
        }
    return pd.DataFrame(rows).T.rename_axis("period")


def _users_table(split: Split) -> pd.DataFrame:
    users = split.users
    cold = users["is_cold_start"]
    reasons = users.loc[~users["eligible"], "exclusion_reason"].value_counts()
    rows: dict[str, int] = {
        "users_total": len(users),
        "users_eligible": int(users["eligible"].sum()),
        "users_excluded_from_scoring": int((~users["eligible"]).sum()),
        **{f"excluded: {reason}": int(n) for reason, n in reasons.items()},
        "cold_start_holdout_users (20%, out of every fit)": int(cold.sum()),
        "users_in_fit (not cold-start)": int((~cold).sum()),
    }
    for group in GROUPS:
        for target in TARGETS:
            rows[f"{group}_evaluated_{target}"] = len(
                evaluation_users(split, target, group)
            )
    return pd.DataFrame({"count": rows}).rename_axis("measure")


def _heldout_table(split: Split) -> pd.DataFrame:
    rows = {}
    for target in TARGETS:
        fit_items = set(fit_ratings(split, target)["movie_id"].unique().tolist())
        for group in GROUPS:
            users = evaluation_users(split, target, group)
            relevant = [heldout_relevant_items(split, int(u), target) for u in users]
            # cold-start candidate counts depend on the revealed history size: they are
            # reported in the cold_start_simulation table instead
            candidates = (
                []
                if group == "cold_start"
                else [len(candidate_items(split, int(u), target)) for u in users]
            )
            counts = np.array([len(r) for r in relevant])
            flat = (
                np.concatenate(relevant) if relevant else np.array([], dtype=np.int64)
            )
            in_fit = (
                np.isin(flat, list(fit_items)).mean() if flat.size else float("nan")
            )
            rows[(target, group)] = {
                "evaluated_users": len(users),
                "relevant_heldout_items": int(counts.sum()),
                "median_relevant_per_user": float(np.median(counts))
                if counts.size
                else 0.0,
                "users_with_1_relevant": int((counts == 1).sum()),
                "users_with_fewer_than_3_relevant": int((counts < 3).sum()),
                "heldout_items_seen_in_fit_pct": round(100 * float(in_fit), 1),
                "mean_candidates_per_user": int(np.mean(candidates))
                if candidates
                else None,
                "min_candidates_per_user": int(min(candidates)) if candidates else None,
            }
    table = pd.DataFrame(rows).T
    table.index.names = ["target", "group"]
    return table


def _tags_table(split: Split) -> pd.DataFrame:
    tags = split.tags
    cold_authors = tags["user_id"].isin(split.users.index[split.users["is_cold_start"]])
    rows = {
        "tag_applications_total": len(tags),
        "taggers": int(tags["user_id"].nunique()),
        "tags_by_cold_start_users (never used)": int(cold_authors.sum()),
        "usable_in_validation_fit": len(fit_tags(split, "validation")),
        "usable_in_test_fit": len(fit_tags(split, "test")),
    }
    return pd.DataFrame({"count": rows}).rename_axis("measure")


def _cold_start_table(split: Split) -> pd.DataFrame:
    rows = {}
    for target in TARGETS:
        users = evaluation_users(split, target, "cold_start")
        train_sizes = split.users.loc[users, "n_train"]
        for history in HISTORY_SIZES:
            scorable = [int(u) for u in users if train_sizes[u] >= history]
            sizes, kept, total = [], 0, 0
            for user in scorable:
                candidates = set(candidate_items(split, user, target, history).tolist())
                sizes.append(len(candidates))
                held = heldout_relevant_items(split, user, target).tolist()
                kept += sum(item in candidates for item in held)
                total += len(held)
            rows[(target, history)] = {
                "simulated_users": len(scorable),
                "relevant_heldout_items": total,
                "mean_candidates_per_user": int(np.mean(sizes)) if sizes else None,
                "heldout_relevant_in_candidates_pct": round(100 * kept / total, 1)
                if total
                else None,
            }
    table = pd.DataFrame(rows).T
    table.index.names = ["target", "revealed_ratings"]
    return table


def _leakage_table(split: Split) -> pd.DataFrame:
    """Per scored warm user: share of the fit that is dated at or after their own
    cutoff.
    """
    rows = {}
    for target in TARGETS:
        cutoff_col = "validation_cutoff" if target == "validation" else "test_cutoff"
        fit_stamps = np.sort(fit_ratings(split, target)["timestamp"].to_numpy())
        tag_stamps = np.sort(fit_tags(split, target)["timestamp"].to_numpy())
        users = evaluation_users(split, target, "warm")
        cuts = split.users.loc[users, cutoff_col].to_numpy()
        rating_later = 1 - np.searchsorted(fit_stamps, cuts, side="left") / len(
            fit_stamps
        )
        quantiles = [0.1, 0.5, 0.9]
        row = {
            f"ratings_after_own_cutoff_p{int(q * 100)}_pct": round(
                100 * float(np.quantile(rating_later, q)), 1
            )
            for q in quantiles
        }
        row["ratings_after_own_cutoff_mean_pct"] = round(
            100 * float(rating_later.mean()), 1
        )
        if tag_stamps.size:
            tag_later = 1 - np.searchsorted(tag_stamps, cuts, side="left") / len(
                tag_stamps
            )
            row["usable_tags_after_own_cutoff_median_pct"] = round(
                100 * float(np.median(tag_later)), 1
            )
        rows[target] = row
    return pd.DataFrame(rows).T.rename_axis("target")


def feasibility_tables(split: Split) -> dict[str, pd.DataFrame]:
    """All feasibility tables, keyed by file stem."""
    return {
        "periods": _periods_table(split),
        "users": _users_table(split),
        "heldout": _heldout_table(split),
        "tags": _tags_table(split),
        "cold_start_simulation": _cold_start_table(split),
        "cross_user_leakage": _leakage_table(split),
    }


def save_split(split: Split, tables: dict[str, pd.DataFrame], out_dir: Path) -> None:
    """Write assignments (IDs + period only), user flags and tables as CSV."""
    out_dir.mkdir(parents=True, exist_ok=True)
    assignments = split.ratings[["user_id", "movie_id", "period"]].copy()
    assignments["period"] = assignments["period"].astype(str)
    assignments.to_csv(out_dir / "assignments.csv", index=False)
    split.users.to_csv(out_dir / "users.csv")
    for name, table in tables.items():
        table.to_csv(out_dir / f"feasibility_{name}.csv")


def main(
    raw_dir: Path = Path("data/raw/ml-latest-small"),
    out_dir: Path = Path("data/processed/split"),
) -> None:
    data = load_movielens(raw_dir)
    split = build_split(data.ratings, data.movies, data.tags)
    tables = feasibility_tables(split)
    save_split(split, tables, out_dir)
    for name, table in tables.items():
        print(f"\n== {name} ==")
        print(table.to_string())
    print(f"\nminimum train ratings to be scored: {MIN_TRAIN_RATINGS}")
    print(f"saved to {out_dir}")


if __name__ == "__main__":
    main()
