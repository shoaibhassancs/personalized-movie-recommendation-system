"""Load MovieLens CSV files into typed DataFrames and validate them.

Loaders never drop rows. A problem that makes the data unusable raises
:class:`DataValidationError`; anything else is counted in the :class:`ValidationReport`.
``rows_read`` always equals ``rows_returned`` so nothing disappears silently.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

NO_GENRES_MARKER = "(no genres listed)"
VALID_RATINGS = tuple(np.arange(0.5, 5.01, 0.5))
# MovieLens started in 1995; timestamps are Unix seconds.
MIN_TIMESTAMP = 788_918_400  # 1995-01-01 UTC
MAX_TIMESTAMP = 1_893_456_000  # 2030-01-01 UTC
_YEAR_AT_END = re.compile(r"^(?P<title>.*?)\s*\((?P<year>\d{4})\)\s*$")


class DataValidationError(Exception):
    """Raised when the data is unusable (missing columns, bad values, broken links)."""


@dataclass
class ValidationReport:
    """Counts and observations from loading; one entry per fact worth knowing."""

    rows_read: dict[str, int] = field(default_factory=dict)
    rows_returned: dict[str, int] = field(default_factory=dict)
    observations: dict[str, int] = field(default_factory=dict)

    @property
    def rows_dropped(self) -> dict[str, int]:
        """Rows read minus rows returned for each table (must be zero)."""
        return {k: self.rows_read[k] - self.rows_returned[k] for k in self.rows_read}


@dataclass
class MovieLensData:
    """The three tables used by the project, plus the validation report."""

    ratings: pd.DataFrame
    movies: pd.DataFrame
    tags: pd.DataFrame
    report: ValidationReport


def parse_title_year(title: str) -> tuple[str, int | None]:
    """Split ``"Toy Story (1995)"`` into ``("Toy Story", 1995)``; None if no year."""
    match = _YEAR_AT_END.match(title.strip())
    if match is None:
        return title.strip(), None
    return match.group("title"), int(match.group("year"))


def split_genres(genres: str) -> tuple[str, ...]:
    """Split ``"Action|Comedy"`` into a tuple; ``"(no genres listed)"`` gives ``()``."""
    if genres == NO_GENRES_MARKER or genres == "":
        return ()
    return tuple(genres.split("|"))


def genres_multi_hot(movies: pd.DataFrame) -> pd.DataFrame:
    """Return a movie_id x genre table of 0/1 flags from the ``genres`` column."""
    vocabulary = sorted({g for genres in movies["genres"] for g in genres})
    table = np.zeros((len(movies), len(vocabulary)), dtype=np.uint8)
    index = {genre: i for i, genre in enumerate(vocabulary)}
    for row, genres in enumerate(movies["genres"]):
        for genre in genres:
            table[row, index[genre]] = 1
    return pd.DataFrame(table, index=movies["movie_id"].to_numpy(), columns=vocabulary)


def _read(path: Path, columns: dict[str, str]) -> pd.DataFrame:
    """Read a CSV, check the header, and rename columns to snake_case."""
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise DataValidationError(f"{path.name}: missing columns {missing}")
    frame = frame[list(columns)].rename(columns=columns)
    return frame


def _to_int(frame: pd.DataFrame, name: str, table: str) -> pd.Series:
    try:
        return frame[name].astype("int64")
    except (ValueError, TypeError) as error:
        raise DataValidationError(f"{table}.{name}: non-integer values") from error


def _check_timestamps(values: pd.Series, table: str) -> None:
    bad = int(((values < MIN_TIMESTAMP) | (values > MAX_TIMESTAMP)).sum())
    if bad:
        raise DataValidationError(f"{table}: {bad} timestamps outside 1995-2030")


def load_movielens(directory: Path) -> MovieLensData:
    """Load ratings, movies and tags from an extracted ``ml-latest-small`` folder."""
    report = ValidationReport()

    # --- movies
    movies = _read(
        directory / "movies.csv",
        {"movieId": "movie_id", "title": "title", "genres": "genres"},
    )
    report.rows_read["movies"] = len(movies)
    movies["movie_id"] = _to_int(movies, "movie_id", "movies")
    if movies["movie_id"].duplicated().any():
        raise DataValidationError("movies: duplicate movie_id values")
    if (movies["title"].str.strip() == "").any():
        raise DataValidationError("movies: empty titles")
    parsed = [parse_title_year(t) for t in movies["title"]]
    movies["title_clean"] = [p[0] for p in parsed]
    movies["year"] = pd.array([p[1] for p in parsed], dtype="Int64")
    movies["genres"] = [split_genres(g) for g in movies["genres"]]
    report.observations["movies_without_year"] = int(movies["year"].isna().sum())
    report.observations["movies_without_genres"] = int(
        sum(len(g) == 0 for g in movies["genres"])
    )
    report.rows_returned["movies"] = len(movies)

    # --- ratings
    ratings = _read(
        directory / "ratings.csv",
        {
            "userId": "user_id",
            "movieId": "movie_id",
            "rating": "rating",
            "timestamp": "timestamp",
        },
    )
    report.rows_read["ratings"] = len(ratings)
    for name in ("user_id", "movie_id", "timestamp"):
        ratings[name] = _to_int(ratings, name, "ratings")
    try:
        ratings["rating"] = ratings["rating"].astype("float64")
    except ValueError as error:
        raise DataValidationError("ratings.rating: non-numeric values") from error
    if not ratings["rating"].isin(VALID_RATINGS).all():
        raise DataValidationError("ratings: values outside 0.5-5.0 in steps of 0.5")
    if ratings.duplicated(["user_id", "movie_id"]).any():
        raise DataValidationError("ratings: duplicate (user_id, movie_id) pairs")
    _check_timestamps(ratings["timestamp"], "ratings")
    unknown = int((~ratings["movie_id"].isin(movies["movie_id"])).sum())
    if unknown:
        raise DataValidationError(f"ratings: {unknown} rows refer to unknown movies")
    report.rows_returned["ratings"] = len(ratings)

    # --- tags
    tags = _read(
        directory / "tags.csv",
        {
            "userId": "user_id",
            "movieId": "movie_id",
            "tag": "tag",
            "timestamp": "timestamp",
        },
    )
    report.rows_read["tags"] = len(tags)
    for name in ("user_id", "movie_id", "timestamp"):
        tags[name] = _to_int(tags, name, "tags")
    _check_timestamps(tags["timestamp"], "tags")
    unknown = int((~tags["movie_id"].isin(movies["movie_id"])).sum())
    if unknown:
        raise DataValidationError(f"tags: {unknown} rows refer to unknown movies")
    report.observations["tags_empty_text"] = int((tags["tag"].str.strip() == "").sum())
    report.observations["tags_duplicate_rows"] = int(
        tags.duplicated(["user_id", "movie_id", "tag"]).sum()
    )
    report.observations["tag_authors_without_ratings"] = int(
        (~tags["user_id"].isin(ratings["user_id"])).sum()
    )
    report.rows_returned["tags"] = len(tags)

    report.observations["users_in_ratings"] = int(ratings["user_id"].nunique())
    report.observations["movies_without_ratings"] = int(
        (~movies["movie_id"].isin(ratings["movie_id"])).sum()
    )
    if any(report.rows_dropped.values()):
        raise DataValidationError(f"rows were dropped: {report.rows_dropped}")
    return MovieLensData(ratings=ratings, movies=movies, tags=tags, report=report)
