"""Tests for the safe-download helpers and the real-data count check."""

import urllib.request
import zipfile
from pathlib import Path

import pytest

from pmrs.data import load_movielens
from pmrs.data.download import (
    README_COUNTS,
    DownloadError,
    _RefuseRedirect,
    download_archive,
    missing_files,
    safe_extract,
    sha256_of,
)

REAL = Path(__file__).parents[1] / "data" / "raw" / "ml-latest-small"


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, payload in members.items():
            bundle.writestr(name, payload)
    return path


def test_extract_strips_top_folder(tmp_path: Path) -> None:
    archive = _zip(
        tmp_path / "a.zip", {"top/ratings.csv": b"x", "top/movies.csv": b"y"}
    )
    names = safe_extract(archive, tmp_path / "out")
    assert names == ["movies.csv", "ratings.csv"]
    assert (tmp_path / "out" / "ratings.csv").read_bytes() == b"x"


@pytest.mark.parametrize("bad", ["../escape.csv", "top/../../escape.csv", "/abs.csv"])
def test_extract_rejects_unsafe_paths(tmp_path: Path, bad: str) -> None:
    archive = _zip(tmp_path / "a.zip", {bad: b"x"})
    with pytest.raises(DownloadError, match="Unsafe"):
        safe_extract(archive, tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert not (tmp_path / "escape.csv").exists()


def test_extract_refuses_existing_target(tmp_path: Path) -> None:
    archive = _zip(tmp_path / "a.zip", {"top/a.csv": b"x"})
    (tmp_path / "out").mkdir()
    with pytest.raises(DownloadError, match="already exists"):
        safe_extract(archive, tmp_path / "out")


def test_download_refuses_other_hosts(tmp_path: Path) -> None:
    with pytest.raises(DownloadError, match="Only"):
        download_archive(tmp_path / "x.zip", url="https://example.com/ml.zip")
    assert not (tmp_path / "x.zip").exists()


def test_sha256_of_known_content(tmp_path: Path) -> None:
    f = tmp_path / "f.bin"
    f.write_bytes(b"abc")
    assert sha256_of(f) == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_missing_files_lists_absent(tmp_path: Path) -> None:
    (tmp_path / "movies.csv").write_text("x")
    assert "ratings.csv" in missing_files(tmp_path)
    assert "movies.csv" not in missing_files(tmp_path)


@pytest.mark.skipif(not REAL.is_dir(), reason="real MovieLens data not downloaded")
def test_real_data_matches_readme_counts_and_drops_nothing() -> None:
    data = load_movielens(REAL)
    assert len(data.ratings) == README_COUNTS["ratings"]
    assert len(data.movies) == README_COUNTS["movies"]
    assert len(data.tags) == README_COUNTS["tags"]
    assert data.report.observations["users_in_ratings"] == README_COUNTS["users"]
    assert data.report.rows_dropped == {"movies": 0, "ratings": 0, "tags": 0}


def test_redirects_are_refused() -> None:
    handler = _RefuseRedirect()
    with pytest.raises(DownloadError, match="redirected"):
        handler.redirect_request(
            urllib.request.Request("https://files.grouplens.org/x"),
            None,
            302,
            "Found",
            {},
            "https://elsewhere.example/x",
        )
