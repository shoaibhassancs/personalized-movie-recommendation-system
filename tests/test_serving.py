"""Step 17 tests: the manifest, the all-data fit and the artifact statements.
Mechanics on the invented Step 14 dataset; no claim about quality.
"""

import json
from pathlib import Path

import pandas as pd
import pytest

from pmrs.evaluation import serving
from pmrs.recommender.artifact import MODEL_FILE, ArtifactError, save_recommender
from pmrs.recommender.recommender import Recommender
from pmrs.split import Split, build_split
from test_evaluation import toy_movies, toy_ratings, toy_tags


@pytest.fixture(scope="module")
def toy() -> tuple[Split, pd.DataFrame]:
    movies = toy_movies()
    return build_split(toy_ratings(), movies, toy_tags()), movies


def make_folder(tmp_path: Path, toy: tuple[Split, pd.DataFrame]) -> Path:
    split, movies = toy
    rec = Recommender.fit(
        serving.serving_fit_data(split, movies), target="serving_all_data"
    )
    folder = save_recommender(rec, tmp_path / "a")
    (folder / serving.PROVENANCE).write_text(
        json.dumps({"frozen_config_sha256": serving.FROZEN_SHA256})
    )
    (folder / serving.MANIFEST).write_text(
        "\n".join(serving.manifest_lines(folder)) + "\n"
    )
    return folder


def test_serving_fit_uses_every_rating_user_and_tag(
    toy: tuple[Split, pd.DataFrame],
) -> None:
    split, movies = toy
    fit = serving.serving_fit_data(split, movies)
    assert fit.matrix.nnz == len(split.ratings) == len(toy_ratings())
    assert len(fit.tags) == len(toy_tags())  # includes the tag after the cutoff
    cold = split.users.index[split.users["is_cold_start"]]
    rows = split.user_map.to_index(cold.to_numpy())
    assert (fit.matrix[rows].getnnz(axis=1) > 0).all()  # cold-start users are in


def test_manifest_accepts_the_folder_and_catches_changes(
    tmp_path: Path, toy: tuple[Split, pd.DataFrame]
) -> None:
    folder = make_folder(tmp_path, toy)
    serving.verify_manifest(folder)
    serving.load_verified(folder)
    (folder / "extra.txt").write_text("x")
    with pytest.raises(ArtifactError, match="differ from the manifest"):
        serving.verify_manifest(folder)
    (folder / "extra.txt").unlink()
    with (folder / MODEL_FILE).open("ab") as handle:
        handle.write(b"0")
    with pytest.raises(ArtifactError, match="damaged"):
        serving.load_verified(folder)  # refused before anything is unpickled


def test_an_artifact_from_another_config_is_refused(
    tmp_path: Path, toy: tuple[Split, pd.DataFrame]
) -> None:
    folder = make_folder(tmp_path, toy)
    (folder / serving.PROVENANCE).write_text(json.dumps({"frozen_config_sha256": "0"}))
    (folder / serving.MANIFEST).write_text(
        "\n".join(serving.manifest_lines(folder)) + "\n"
    )
    with pytest.raises(ArtifactError, match="frozen config"):
        serving.load_verified(folder)


def test_the_statements_keep_the_two_artifacts_apart() -> None:
    assert "do NOT apply" in serving.DESCRIPTIONS["serving"]
    assert "apply to this fit" in serving.DESCRIPTIONS["evaluated"]
    assert set(serving.NAMES) == {"evaluated", "serving"}
