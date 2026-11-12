"""Recommendation events, with deliberately modest meanings.

``shown`` means the API *served* a movie in a recommendation list. It does not mean
the person saw it. ``acted`` means the person later added or changed a rating, like,
dislike, watchlist or watched on a movie that had been served to them; it is
recorded once per serving. It does not mean the recommendation caused the action: the
person may well have acted anyway. A view is not an action and never records one
(D-042). Removals (deleting a rating or flag) are not actions.
"""

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from pmrs.db.models import RecommendationEvent


def record_served(
    session: Session, user_id: int, strategy: str, movie_ids: Iterable[int]
) -> int:
    """Log one ``shown`` event per served movie. The caller commits."""
    events = [
        RecommendationEvent(
            user_id=user_id, movie_id=movie_id, strategy=strategy, kind="shown"
        )
        for movie_id in movie_ids
    ]
    session.add_all(events)
    return len(events)


def record_acted(session: Session, user_id: int, movie_id: int) -> None:
    """Log ``acted`` if this movie was served to this user and no ``acted`` event
    follows the latest serving. Same transaction as the action. The strategy is the
    latest one that served the movie."""
    served = session.execute(
        select(RecommendationEvent)
        .where(
            RecommendationEvent.user_id == user_id,
            RecommendationEvent.movie_id == movie_id,
            RecommendationEvent.kind == "shown",
        )
        .order_by(RecommendationEvent.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if served is None:
        return
    later = session.execute(
        select(RecommendationEvent.id)
        .where(
            RecommendationEvent.user_id == user_id,
            RecommendationEvent.movie_id == movie_id,
            RecommendationEvent.kind == "acted",
            RecommendationEvent.id > served.id,
        )
        .limit(1)
    ).first()
    if later is None:
        session.add(
            RecommendationEvent(
                user_id=user_id,
                movie_id=movie_id,
                strategy=served.strategy,
                kind="acted",
            )
        )
