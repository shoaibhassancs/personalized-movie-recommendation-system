"""The caller's own profile, genres, history, watchlist and account deletion.

Every route takes the user from the token. None accepts a user id.
"""

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import delete, func, select

from pmrs.api.auth import user_out
from pmrs.api.catalogue import (
    MAX_PAGE_SIZE,
    canonical_genre,
    movies_by_id,
    states_for,
)
from pmrs.api.deps import CurrentUser, SessionDep
from pmrs.api.schemas import (
    GenresIn,
    HistoryItem,
    HistoryPage,
    MoviePage,
    ProfileIn,
    UserOut,
)
from pmrs.db.models import Interaction, Rating, User, UserGenre

router = APIRouter(prefix="/me", tags=["me"])


def _genres(session: SessionDep, user_id: int) -> list[str]:
    rows = session.execute(
        select(UserGenre.genre)
        .where(UserGenre.user_id == user_id)
        .order_by(UserGenre.genre)
    )
    return [r[0] for r in rows]


@router.get("", response_model=UserOut)
def read_me(user: CurrentUser, session: SessionDep) -> UserOut:
    return user_out(user, _genres(session, user.id))


@router.put("", response_model=UserOut)
def update_me(body: ProfileIn, user: CurrentUser, session: SessionDep) -> UserOut:
    stored = session.get(User, user.id)
    assert stored is not None
    stored.display_name = body.display_name
    session.commit()
    session.refresh(stored)
    return user_out(stored, _genres(session, user.id))


@router.put("/genres", response_model=UserOut)
def replace_genres(body: GenresIn, user: CurrentUser, session: SessionDep) -> UserOut:
    chosen: set[str] = set()
    for name in body.genres:
        known = canonical_genre(session, name)
        if known is None:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "unknown genre")
        chosen.add(known)
    session.execute(delete(UserGenre).where(UserGenre.user_id == user.id))
    session.add_all(UserGenre(user_id=user.id, genre=g) for g in sorted(chosen))
    session.commit()
    stored = session.get(User, user.id)
    assert stored is not None
    return user_out(stored, sorted(chosen))


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(user: CurrentUser, session: SessionDep) -> Response:
    """Delete the caller's own account and, by database cascade, their ratings,
    interactions, genres and events. A historical user can never reach this route
    (no token authenticates as one) and the condition below repeats the guarantee."""
    result = session.execute(
        delete(User).where(User.id == user.id, User.is_historical.is_(False))
    )
    session.commit()
    if result.rowcount != 1:  # type: ignore[attr-defined]
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/history", response_model=HistoryPage)
def history(
    user: CurrentUser,
    session: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
) -> HistoryPage:
    """Movies the caller rated or acted on, newest activity first."""
    rated = select(
        Rating.movie_id.label("movie_id"), Rating.rated_at.label("ts")
    ).where(Rating.user_id == user.id)
    acted = select(
        Interaction.movie_id.label("movie_id"), Interaction.created_at.label("ts")
    ).where(Interaction.user_id == user.id)
    activity = rated.union_all(acted).subquery()
    last = (
        select(activity.c.movie_id, func.max(activity.c.ts).label("last"))
        .group_by(activity.c.movie_id)
        .subquery()
    )
    total = session.execute(select(func.count()).select_from(last)).scalar_one()
    rows = session.execute(
        select(last.c.movie_id, last.c.last)
        .order_by(last.c.last.desc(), last.c.movie_id)
        .limit(page_size)
        .offset((page - 1) * page_size)
    ).all()
    ids = [r[0] for r in rows]
    movies = movies_by_id(session, ids)
    states = states_for(session, user.id, ids)
    items = [
        HistoryItem(movie=movies[i], state=states[i], last_activity=when)
        for i, when in rows
    ]
    return HistoryPage(items=items, page=page, page_size=page_size, total=int(total))


@router.get("/watchlist", response_model=MoviePage)
def watchlist(
    user: CurrentUser,
    session: SessionDep,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=MAX_PAGE_SIZE),
) -> MoviePage:
    base = (Interaction.user_id == user.id, Interaction.kind == "watchlist")
    total = session.execute(
        select(func.count()).select_from(Interaction).where(*base)
    ).scalar_one()
    ids = [
        r[0]
        for r in session.execute(
            select(Interaction.movie_id)
            .where(*base)
            .order_by(Interaction.created_at.desc(), Interaction.movie_id)
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ]
    movies = movies_by_id(session, ids)
    return MoviePage(
        items=[movies[i] for i in ids], page=page, page_size=page_size, total=int(total)
    )
