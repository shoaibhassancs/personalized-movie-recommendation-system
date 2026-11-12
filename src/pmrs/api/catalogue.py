"""Catalogue and per-user state queries (plain SQL through SQLAlchemy).

Average rating and rating count are computed over every rating in the ``ratings`` table:
the 100,836 MovieLens ratings plus any made in the app. Rating-based sorting and
filtering only count movies with at least ``MIN_RATINGS_FOR_RATING`` ratings, so one 5.0
cannot top the list; movies below that sort after the eligible ones, by title.
"""

import re
import zlib
from collections.abc import Iterable, Sequence
from typing import Any, Literal

from sqlalchemy import (
    ColumnElement,
    Select,
    and_,
    case,
    func,
    select,
)
from sqlalchemy.orm import Session

from pmrs.api.schemas import MovieOut, MovieState, Poster
from pmrs.db.models import Interaction, Movie, Rating

MIN_RATINGS_FOR_RATING = 5
MAX_PAGE_SIZE = 50
Sort = Literal["title", "year", "rating", "popularity"]
Order = Literal["asc", "desc"]
_TRAILING_YEAR = re.compile(r"\s*\(\d{4}\)\s*$")


def poster_for(title: str) -> Poster:
    name = _TRAILING_YEAR.sub("", title)
    words = [w for w in re.split(r"\W+", name) if w]
    initials = "".join(w[0] for w in words[:2]).upper() or "?"
    return Poster(initials=initials, hue=zlib.crc32(name.encode()) % 360)


def genre_vocabulary(session: Session) -> list[str]:
    rows = session.execute(select(func.unnest(Movie.genres)).distinct()).all()
    return sorted(str(r[0]) for r in rows)


def canonical_genre(session: Session, genre: str) -> str | None:
    wanted = genre.strip().lower()
    for known in genre_vocabulary(session):
        if known.lower() == wanted:
            return known
    return None


def _escape_like(text_: str) -> str:
    return text_.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _stats() -> Any:
    return (
        select(
            Rating.movie_id.label("movie_id"),
            func.avg(Rating.rating).label("avg"),
            func.count().label("n"),
        )
        .group_by(Rating.movie_id)
        .subquery()
    )


def _to_movie(movie: Movie, average: Any, count: int | None) -> MovieOut:
    return MovieOut(
        id=movie.id,
        title=movie.title,
        year=movie.year,
        genres=list(movie.genres),
        average_rating=None if average is None else round(float(average), 2),
        rating_count=int(count or 0),
        poster=poster_for(movie.title),
    )


def search_movies(
    session: Session,
    *,
    q: str | None,
    genre: str | None,
    year_min: int | None,
    year_max: int | None,
    min_rating: float | None,
    sort: Sort,
    order: Order | None,
    page: int,
    page_size: int,
) -> tuple[list[MovieOut], int]:
    """One page of movies and the total number matching the filters."""
    stats = _stats()
    count = func.coalesce(stats.c.n, 0)
    eligible = count >= MIN_RATINGS_FOR_RATING
    query: Select[Any] = select(Movie, stats.c.avg, count.label("n")).outerjoin(
        stats, stats.c.movie_id == Movie.id
    )
    where: list[ColumnElement[bool]] = []
    if q:
        where.append(Movie.title.ilike(f"%{_escape_like(q.strip())}%", escape="\\"))
    if genre:
        where.append(Movie.genres.contains([genre]))
    if year_min is not None:
        where.append(Movie.year >= year_min)
    if year_max is not None:
        where.append(Movie.year <= year_max)
    if min_rating is not None:
        where.append(and_(eligible, stats.c.avg >= min_rating))
    query = query.where(*where)
    total = session.execute(
        select(func.count()).select_from(query.with_only_columns(Movie.id).subquery())
    ).scalar_one()

    descending = (order or ("asc" if sort == "title" else "desc")) == "desc"
    title_key = func.lower(Movie.title)
    ordering: list[Any]
    if sort == "title":
        ordering = [title_key.desc() if descending else title_key.asc()]
    elif sort == "year":
        year = Movie.year.desc() if descending else Movie.year.asc()
        ordering = [year.nulls_last(), title_key]
    elif sort == "rating":
        average = case((eligible, stats.c.avg), else_=None)
        ordered = average.desc() if descending else average.asc()
        ordering = [eligible.desc(), ordered.nulls_last(), count.desc(), title_key]
    else:
        ordering = [count.desc() if descending else count.asc()]
    query = (
        query.order_by(*ordering, Movie.id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    )
    rows = session.execute(query).all()
    return [_to_movie(m, avg, n) for m, avg, n in rows], int(total)


def movies_by_id(session: Session, ids: Sequence[int]) -> dict[int, MovieOut]:
    stats = _stats()
    rows = session.execute(
        select(Movie, stats.c.avg, func.coalesce(stats.c.n, 0))
        .outerjoin(stats, stats.c.movie_id == Movie.id)
        .where(Movie.id.in_(list(ids)))
    ).all()
    return {m.id: _to_movie(m, avg, n) for m, avg, n in rows}


def states_for(
    session: Session, user_id: int, movie_ids: Iterable[int]
) -> dict[int, MovieState]:
    """The user's own rating and flags for each movie (empty state when none)."""
    ids = list(movie_ids)
    ratings = {
        r.movie_id: float(r.rating)
        for r in session.execute(
            select(Rating).where(Rating.user_id == user_id, Rating.movie_id.in_(ids))
        ).scalars()
    }
    flags: dict[int, dict[str, Any]] = {i: {} for i in ids}
    for row in session.execute(
        select(Interaction).where(
            Interaction.user_id == user_id, Interaction.movie_id.in_(ids)
        )
    ).scalars():
        flags[row.movie_id][row.kind] = row.created_at
    return {
        i: MovieState(
            rating=ratings.get(i),
            liked="like" in flags[i],
            disliked="dislike" in flags[i],
            watchlist="watchlist" in flags[i],
            watched="watched" in flags[i],
            viewed_at=flags[i].get("viewed"),
        )
        for i in ids
    }
