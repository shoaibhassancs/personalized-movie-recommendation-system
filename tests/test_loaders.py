"""Tests for the MovieLens loaders and validation, using small invented fixtures."""

from pathlib import Path
from shutil import copytree

import pytest

from pmrs.data import (
    DataValidationError,
    genres_multi_hot,
    load_movielens,
    parse_title_year,
)

TINY = Path(__file__).parent / "data" / "tiny"


def _copy(tmp_path: Path) -> Path:
    target = tmp_path / "ml"
    copytree(TINY, target)
    return target


def test_loads_every_row_and_reports_zero_dropped() -> None:
    data = load_movielens(TINY)
    assert (len(data.movies), len(data.ratings), len(data.tags)) == (4, 5, 2)
    assert data.report.rows_read == data.report.rows_returned
    assert data.report.rows_dropped == {"movies": 0, "ratings": 0, "tags": 0}


def test_observations_are_counted() -> None:
    obs = load_movielens(TINY).report.observations
    assert obs["movies_without_year"] == 1
    assert obs["movies_without_genres"] == 1
    assert obs["users_in_ratings"] == 3
    assert obs["movies_without_ratings"] == 1  # movie 3 has no ratings


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Toy Story (1995)", ("Toy Story", 1995)),
        ("Name With (Parens) (2001)", ("Name With (Parens)", 2001)),
        ("No year here", ("No year here", None)),
        ("Series (2006-2007)", ("Series (2006-2007)", None)),
    ],
)
def test_parse_title_year(title: str, expected: tuple[str, int | None]) -> None:
    assert parse_title_year(title) == expected


def test_genres_split_and_multi_hot() -> None:
    movies = load_movielens(TINY).movies
    assert movies.loc[movies["movie_id"] == 3, "genres"].iloc[0] == ()
    hot = genres_multi_hot(movies)
    assert list(hot.columns) == ["Action", "Adventure", "Comedy", "Drama", "Sci-Fi"]
    assert hot.loc[1].sum() == 2 and hot.loc[3].sum() == 0


def _edit(path: Path, old: str, new: str) -> None:
    path.write_text(path.read_text().replace(old, new))


def test_rejects_rating_out_of_range(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    _edit(folder / "ratings.csv", "4.0,", "6.0,")
    with pytest.raises(DataValidationError, match="0.5-5.0"):
        load_movielens(folder)


def test_rejects_duplicate_user_movie_pair(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    _edit(folder / "ratings.csv", "1,2,3.5", "1,1,3.5")
    with pytest.raises(DataValidationError, match="duplicate"):
        load_movielens(folder)


def test_rejects_rating_for_unknown_movie(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    _edit(folder / "ratings.csv", "3,2,4.5", "3,99,4.5")
    with pytest.raises(DataValidationError, match="unknown movies"):
        load_movielens(folder)


def test_rejects_missing_column(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    _edit(folder / "ratings.csv", "rating", "stars")
    with pytest.raises(DataValidationError, match="missing columns"):
        load_movielens(folder)


def test_rejects_bad_timestamp(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    _edit(folder / "tags.csv", "1000000500", "5")
    with pytest.raises(DataValidationError, match="timestamps"):
        load_movielens(folder)


def test_rejects_duplicate_movie_id(tmp_path: Path) -> None:
    folder = _copy(tmp_path)
    _edit(folder / "movies.csv", "4,Delta", "1,Delta")
    with pytest.raises(DataValidationError, match="duplicate movie_id"):
        load_movielens(folder)
