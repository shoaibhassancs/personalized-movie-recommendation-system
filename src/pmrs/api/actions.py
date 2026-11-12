"""Rate, like, dislike, watchlist, watched, viewed. All need login; the user comes from
the token. Every write is an upsert or a delete, so repeating an action never creates a
duplicate and deleting something absent is not an error. Adding or changing (not
removing) a rating, like, dislike, watchlist or watched on a movie that was served in
a recommendation list also records one ``acted`` event (see ``events``). A view does
not."""

from decimal import Decimal

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert

from pmrs.api.catalogue import states_for
from pmrs.api.deps import CurrentUser, SessionDep
from pmrs.api.events import record_acted
from pmrs.api.schemas import MovieState, RatingIn
from pmrs.db.models import Interaction, Movie, Rating

router = APIRouter(prefix="/movies", tags=["interactions"])

EXCLUSIVE = {"like": "dislike", "dislike": "like"}  # you cannot like AND dislike


def _require_movie(session: SessionDep, movie_id: int) -> None:
    if session.get(Movie, movie_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "movie not found")


def _state(session: SessionDep, user_id: int, movie_id: int) -> MovieState:
    return states_for(session, user_id, [movie_id])[movie_id]


@router.put("/{movie_id}/rating", response_model=MovieState)
def put_rating(
    movie_id: int, body: RatingIn, user: CurrentUser, session: SessionDep
) -> MovieState:
    """Create the rating or replace it; the time becomes now (latest rating event)."""
    _require_movie(session, movie_id)
    value = Decimal(str(body.rating))
    session.execute(
        insert(Rating)
        .values(user_id=user.id, movie_id=movie_id, rating=value, rated_at=func.now())
        .on_conflict_do_update(
            index_elements=[Rating.user_id, Rating.movie_id],
            set_={"rating": value, "rated_at": func.now()},
        )
    )
    record_acted(session, user.id, movie_id)
    session.commit()
    return _state(session, user.id, movie_id)


@router.delete("/{movie_id}/rating", response_model=MovieState)
def delete_rating(movie_id: int, user: CurrentUser, session: SessionDep) -> MovieState:
    _require_movie(session, movie_id)
    session.execute(
        delete(Rating).where(Rating.user_id == user.id, Rating.movie_id == movie_id)
    )
    session.commit()
    return _state(session, user.id, movie_id)


def _set_flag(
    session: SessionDep, user_id: int, movie_id: int, kind: str
) -> MovieState:
    _require_movie(session, movie_id)
    other = EXCLUSIVE.get(kind)
    if other:
        session.execute(
            delete(Interaction).where(
                Interaction.user_id == user_id,
                Interaction.movie_id == movie_id,
                Interaction.kind == other,
            )
        )
    session.execute(
        insert(Interaction)
        .values(user_id=user_id, movie_id=movie_id, kind=kind)
        .on_conflict_do_nothing(
            index_elements=[Interaction.user_id, Interaction.movie_id, Interaction.kind]
        )
    )
    record_acted(session, user_id, movie_id)
    session.commit()
    return _state(session, user_id, movie_id)


def _clear_flag(
    session: SessionDep, user_id: int, movie_id: int, kind: str
) -> MovieState:
    _require_movie(session, movie_id)
    session.execute(
        delete(Interaction).where(
            Interaction.user_id == user_id,
            Interaction.movie_id == movie_id,
            Interaction.kind == kind,
        )
    )
    session.commit()
    return _state(session, user_id, movie_id)


def _register(kind: str) -> None:
    def put(movie_id: int, user: CurrentUser, session: SessionDep) -> MovieState:
        return _set_flag(session, user.id, movie_id, kind)

    def remove(movie_id: int, user: CurrentUser, session: SessionDep) -> MovieState:
        return _clear_flag(session, user.id, movie_id, kind)

    put.__name__ = f"put_{kind}"
    remove.__name__ = f"delete_{kind}"
    router.put(f"/{{movie_id}}/{kind}", response_model=MovieState)(put)
    router.delete(f"/{{movie_id}}/{kind}", response_model=MovieState)(remove)


for _kind in ("like", "dislike", "watchlist", "watched"):
    _register(_kind)


@router.post("/{movie_id}/view", response_model=MovieState)
def post_view(movie_id: int, user: CurrentUser, session: SessionDep) -> MovieState:
    """Record that the caller viewed the movie. One row per user and movie: a repeat
    only refreshes the time (the schema cannot count views). A view is NOT an explicit
    action, so it never writes an ``acted`` recommendation event (D-042)."""
    _require_movie(session, movie_id)
    session.execute(
        insert(Interaction)
        .values(user_id=user.id, movie_id=movie_id, kind="viewed")
        .on_conflict_do_update(
            index_elements=[
                Interaction.user_id,
                Interaction.movie_id,
                Interaction.kind,
            ],
            set_={"created_at": func.now()},
        )
    )
    session.commit()
    return _state(session, user.id, movie_id)
