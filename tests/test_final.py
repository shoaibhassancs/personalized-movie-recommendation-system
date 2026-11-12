"""Step 16 tests: the final-evaluation script is guarded, hash-checked and writes
files that match what it reports. Mechanics only, on the invented Step 14 dataset.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from pmrs.evaluation import final
from pmrs.evaluation.tuning import canonical_hash
from pmrs.recommender.hybrid import HybridConfig
from pmrs.recommender.settings import ModelSettings
from pmrs.split import Split, build_split
from test_evaluation import toy_movies, toy_ratings, toy_tags

SRC = Path(__file__).resolve().parents[1] / "src"


def write_frozen(path: Path, status: str = "FROZEN - test") -> str:
    config = HybridConfig()
    raw = {
        "settings": ModelSettings().to_dict(),
        "hybrid": {
            "few_max": config.few_max,
            "genre_weight": config.genre_weight,
            "popularity_weight": config.popularity_weight,
            "few_weights": dict(config.few_weights),
            "many_weights": dict(config.many_weights),
        },
        "seed": 42,
    }
    digest = canonical_hash(raw)
    path.write_text(json.dumps({**raw, "status": status, "sha256": digest}))
    return digest


@pytest.fixture(scope="module")
def toy() -> tuple[Split, pd.DataFrame]:
    movies = toy_movies()
    return build_split(toy_ratings(), movies, toy_tags()), movies


def test_only_the_final_script_unlocks_the_test_period() -> None:
    users = [
        p.relative_to(SRC).as_posix()
        for p in SRC.rglob("*.py")
        if "allow_test=" in p.read_text() and "allow_test=False" not in p.read_text()
    ]
    # harness defines the parameter; final.py is the only caller that sets it
    assert sorted(users) == ["pmrs/evaluation/final.py", "pmrs/evaluation/harness.py"]
    assert "allow_test=(target ==" in (SRC / "pmrs/evaluation/final.py").read_text()


def test_unfrozen_or_altered_configurations_are_refused(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    digest = write_frozen(path, status="PROPOSED")
    with pytest.raises(RuntimeError, match="FROZEN"):
        final.check_frozen(path, digest)
    digest = write_frozen(path)
    final.check_frozen(path, digest)
    with pytest.raises(RuntimeError, match="approved hash"):
        final.check_frozen(path, "0" * 64)
    raw = json.loads(path.read_text())
    raw["settings"]["neighbours"] = 7  # a changed setting, hash left as it was
    path.write_text(json.dumps(raw))
    with pytest.raises(RuntimeError, match="approved hash"):
        final.check_frozen(path, digest)


def test_test_read_needs_the_flag_and_happens_only_once(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="read-test-once"):
        final.guard_target("test", False, tmp_path)
    (tmp_path / "test").mkdir()
    with pytest.raises(RuntimeError, match="already exists"):
        final.guard_target("test", True, tmp_path)
    assert final.guard_target("validation", False, tmp_path) == tmp_path / "validation"


def test_run_writes_files_that_match_the_frozen_hash_and_the_metrics(
    tmp_path: Path, toy: tuple[Split, pd.DataFrame]
) -> None:
    split, movies = toy
    frozen = tmp_path / "frozen.json"
    digest = write_frozen(frozen)
    out = tmp_path / "out"
    saved = final.run(
        "validation",
        out_dir=out,
        frozen=frozen,
        expected=digest,
        split=split,
        movies=movies,
        data_hash="toy",
        n_boot=50,
    )
    info = json.loads((saved / "final_run.json").read_text())
    assert info["frozen_config_sha256"] == digest
    copy = json.loads((saved / "frozen_config.json").read_text())
    assert canonical_hash(copy) == digest
    summary = pd.read_csv(saved / "summary.csv")
    per_user = pd.read_csv(saved / "per_user.csv")
    row = summary[
        (summary["slice"] == "warm")
        & (summary["method"] == "popularity")
        & (summary["k"] == 10)
    ].iloc[0]
    mean = per_user[
        (per_user["slice"] == "warm")
        & (per_user["method"] == "popularity")
        & (per_user["k"] == 10)
    ]["ndcg"].mean()
    assert row["ndcg"] == pytest.approx(mean)
    assert f"{mean:.3f}" in (saved / "report.txt").read_text()
    assert len(list((saved / "charts").glob("*.html"))) == 5
    # the second validation run is fine; the test guard is separate
    assert not (out / "test").exists()


def test_a_test_run_refuses_a_second_read(
    tmp_path: Path, toy: tuple[Split, pd.DataFrame]
) -> None:
    split, movies = toy
    frozen = tmp_path / "frozen.json"
    digest = write_frozen(frozen)
    kwargs = dict(
        read_test_once=True,
        out_dir=tmp_path / "out",
        frozen=frozen,
        expected=digest,
        split=split,
        movies=movies,
        data_hash="toy",
        n_boot=50,
    )
    first = final.run("test", **kwargs)  # type: ignore[arg-type]
    assert first.name == "test"
    with pytest.raises(RuntimeError, match="already exists"):
        final.run("test", **kwargs)  # type: ignore[arg-type]
