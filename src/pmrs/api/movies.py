"""Public catalogue: GET /movies and GET /movies/{id}. Reading needs no login."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from pmrs.api.catalogue import (
    MAX_PAGE_SIZE,
    Order,
    Sort,
    canonical_genre,
    movies_by_id,
    search_movies,
    states_for,
)
from pmrs.api.deps import OptionalUser, SessionDep
from pmrs.api.schemas import MovieDetail, MoviePage
from pmrs.db.models import Movie

router = APIRouter(prefix="/movies", tags=["catalogue"])


@router.get("", response_model=MoviePage)
def list_movies(
    session: SessionDep,
    q: Annotated[str | None, Query(max_length=100)] = None,
    genre: Annotated[str | None, Query(max_length=50)] = None,
    year_min: Annotated[int | None, Query(ge=1800, le=2100)] = None,
    year_max: Annotated[int | None, Query(ge=1800, le=2100)] = None,
    min_rating: Annotated[float | None, Query(ge=0.5, le=5)] = None,
    sort: Sort = "title",
    order: Order | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> MoviePage:
    chosen = None
    if genre:
        chosen = canonical_genre(session, genre)
        if chosen is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown genre")
    items, total = search_movies(
        session,
        q=q,
        genre=chosen,
        year_min=year_min,
        year_max=year_max,
        min_rating=min_rating,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    return MoviePage(items=items, page=page, page_size=page_size, total=total)


@router.get("/{movie_id}", response_model=MovieDetail)
def movie_detail(movie_id: int, session: SessionDep, user: OptionalUser) -> MovieDetail:
    found = movies_by_id(session, [movie_id]).get(movie_id)
    if found is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "movie not found")
    tag_text = session.execute(
        select(Movie.tag_text).where(Movie.id == movie_id)
    ).scalar_one()
    tags = [t for t in tag_text.split(", ") if t]
    state = states_for(session, user.id, [movie_id])[movie_id] if user else None
    return MovieDetail(**found.model_dump(), tags=tags, me=state)
