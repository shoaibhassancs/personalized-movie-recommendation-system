"""Step 19: load MovieLens into the database. Safe to run twice.

    uv run python -m pmrs.db.seed

* The 610 MovieLens users become ``is_historical`` rows with no email or password (the
  schema forbids both), so none of them can log in. Their original MovieLens ids are
  kept in ``movielens_user_id``; the table's own ``id`` is separate.
* Movies keep their MovieLens ids. ``tag_text`` is the movie's distinct tags, sorted.
* Ratings keep the original MovieLens timestamps (``rated_at``), never the import time.
* Every insert is "do nothing on conflict", so a second run adds nothing. Because that
  could hide a row that differs, ``verify`` compares the database with the CSV data
  row by row after every seed.
"""

import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import Engine, create_engine, func, select, text
from sqlalchemy.dialects.postgresql import insert

from pmrs.data import MovieLensData, load_movielens
from pmrs.db.models import Movie, Rating, User
from pmrs.db.settings import load_settings

RAW_DIR = Path("data/raw/ml-latest-small")
CHUNK = 10_000


@dataclass(frozen=True)
class Prepared:
    users: list[dict[str, Any]]
    movies: list[dict[str, Any]]
    ratings: list[dict[str, Any]]  # keyed by MovieLens user id until ids are known


@dataclass(frozen=True)
class SeedReport:
    users_added: int
    movies_added: int
    ratings_added: int


def _moment(seconds: int) -> datetime:
    return datetime.fromtimestamp(int(seconds), tz=UTC)


def tag_text_by_movie(tags: pd.DataFrame) -> dict[int, str]:
    out: dict[int, set[str]] = {}
    for movie_id, tag in zip(tags["movie_id"], tags["tag"], strict=True):
        cleaned = str(tag).strip()
        if cleaned:
            out.setdefault(int(movie_id), set()).add(cleaned)
    return {m: ", ".join(sorted(t)) for m, t in out.items()}


def prepare(data: MovieLensData) -> Prepared:
    """Turn the validated MovieLens tables into plain rows (no database needed)."""
    user_ids = sorted(
        {int(u) for u in data.ratings["user_id"]}
        | {int(u) for u in data.tags["user_id"]}
    )
    users = [
        {
            "movielens_user_id": u,
            "display_name": f"MovieLens user {u}",
            "is_historical": True,
            "email": None,
            "password_hash": None,
        }
        for u in user_ids
    ]
    tag_text = tag_text_by_movie(data.tags)
    movies = [
        {
            "id": int(movie_id),
            "title": str(title),
            "year": None if pd.isna(year) else int(year),
            "genres": list(genres),
            "tag_text": tag_text.get(int(movie_id), ""),
        }
        for movie_id, title, year, genres in zip(
            data.movies["movie_id"],
            data.movies["title"],
            data.movies["year"].astype(object),
            data.movies["genres"],
            strict=True,
        )
    ]
    ratings = [
        {
            "movielens_user_id": int(u),
            "movie_id": int(m),
            "rating": Decimal(str(r)),
            "rated_at": _moment(t),
        }
        for u, m, r, t in zip(
            data.ratings["user_id"],
            data.ratings["movie_id"],
            data.ratings["rating"],
            data.ratings["timestamp"],
            strict=True,
        )
    ]
    return Prepared(users, movies, ratings)


def _count(connection: Any, table: Any) -> int:
    return int(connection.execute(select(func.count()).select_from(table)).scalar_one())


def seed(engine: Engine, data: MovieLensData) -> SeedReport:
    """Insert what is missing, in one transaction; a failure changes nothing."""
    rows = prepare(data)
    with engine.begin() as connection:
        before = (
            _count(connection, User),
            _count(connection, Movie),
            _count(connection, Rating),
        )
        for start in range(0, len(rows.users), CHUNK):
            connection.execute(
                insert(User)
                .values(rows.users[start : start + CHUNK])
                .on_conflict_do_nothing(index_elements=[User.movielens_user_id])
            )
        connection.execute(
            insert(Movie)
            .values(rows.movies)
            .on_conflict_do_nothing(index_elements=[Movie.id])
        )
        db_id = {
            int(ml): int(pk)
            for ml, pk in connection.execute(
                select(User.movielens_user_id, User.id).where(User.is_historical)
            )
            if ml is not None
        }
        batch = [
            {
                "user_id": db_id[r["movielens_user_id"]],
                "movie_id": r["movie_id"],
                "rating": r["rating"],
                "rated_at": r["rated_at"],
            }
            for r in rows.ratings
        ]
        for start in range(0, len(batch), CHUNK):
            connection.execute(
                insert(Rating)
                .values(batch[start : start + CHUNK])
                .on_conflict_do_nothing(
                    index_elements=[Rating.user_id, Rating.movie_id]
                )
            )
        after = (
            _count(connection, User),
            _count(connection, Movie),
            _count(connection, Rating),
        )
    return SeedReport(*(a - b for a, b in zip(after, before, strict=True)))


def verify(engine: Engine, data: MovieLensData) -> list[str]:
    """Compare the database with the CSV data; returns problems (empty = identical)."""
    rows = prepare(data)
    problems: list[str] = []
    with engine.connect() as connection:
        historical = {
            int(r[0])
            for r in connection.execute(
                select(User.movielens_user_id).where(User.is_historical)
            )
            if r[0] is not None
        }
        if historical != {u["movielens_user_id"] for u in rows.users}:
            problems.append("historical users differ from the dataset's users")
        credentials = connection.execute(
            select(func.count())
            .select_from(User)
            .where(
                User.is_historical,
                User.email.is_not(None) | User.password_hash.is_not(None),
            )
        ).scalar_one()
        if credentials:
            problems.append(f"{credentials} historical users hold a credential")
        db_movies = {
            int(m.id): (m.title, m.year, list(m.genres), m.tag_text)
            for m in connection.execute(select(Movie)).all()
        }
        want_movies = {
            m["id"]: (m["title"], m["year"], m["genres"], m["tag_text"])
            for m in rows.movies
        }
        if db_movies != want_movies:
            problems.append("movies differ from the dataset")
        db_ratings = {
            (int(u), int(m), Decimal(r), int(t))
            for u, m, r, t in connection.execute(
                text(
                    "SELECT u.movielens_user_id, r.movie_id, r.rating,"
                    " extract(epoch FROM r.rated_at)::bigint"
                    " FROM ratings r JOIN users u ON u.id = r.user_id"
                )
            )
        }
        want_ratings = {
            (
                r["movielens_user_id"],
                r["movie_id"],
                r["rating"],
                int(r["rated_at"].timestamp()),
            )
            for r in rows.ratings
        }
        if db_ratings != want_ratings:
            problems.append("ratings (values or original timestamps) differ")
    return problems


def main() -> int:
    engine = create_engine(load_settings().database_url)
    data = load_movielens(RAW_DIR)
    report = seed(engine, data)
    print(
        f"added: users {report.users_added}, movies {report.movies_added}, "
        f"ratings {report.ratings_added}"
    )
    problems = verify(engine, data)
    for problem in problems:
        print(f"MISMATCH: {problem}", file=sys.stderr)
    print("verified: database equals the dataset" if not problems else "NOT verified")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
