"""System-level aggregates. Every route needs login (owner decision, D-039) and returns
counts only: no user ids, emails or per-person rows.

MovieLens (historical) and app numbers are kept in separate fields, because they
measure different things: the historical ratings were collected years ago by another
service, the app numbers come from people using this app. Engagement comes only from
``recommendation_events``.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select

from pmrs.api.catalogue import search_movies
from pmrs.api.deps import SessionDep, current_user
from pmrs.api.schemas import (
    CountSplit,
    EngagementOut,
    MovieOut,
    RatingBucket,
    RatingDistributionOut,
    StrategyEngagement,
    SummaryOut,
)
from pmrs.db.models import (
    INTERACTION_KINDS,
    Interaction,
    Movie,
    Rating,
    RecommendationEvent,
    User,
)

router = APIRouter(
    prefix="/analytics", tags=["analytics"], dependencies=[Depends(current_user)]
)

HALF_STARS = [x / 2 for x in range(1, 11)]


@router.get("/summary", response_model=SummaryOut)
def summary(session: SessionDep) -> SummaryOut:
    movies = session.execute(select(func.count()).select_from(Movie)).scalar_one()
    users = session.execute(
        select(
            func.count(),
            func.count().filter(User.is_historical.is_(True)),
        ).select_from(User)
    ).one()
    ratings = session.execute(
        select(
            func.count(),
            func.count().filter(User.is_historical.is_(True)),
        )
        .select_from(Rating)
        .join(User, User.id == Rating.user_id)
    ).one()
    by_kind = dict(
        session.execute(
            select(Interaction.kind, func.count()).group_by(Interaction.kind)
        ).all()
    )
    events = dict(
        session.execute(
            select(RecommendationEvent.kind, func.count()).group_by(
                RecommendationEvent.kind
            )
        ).all()
    )
    return SummaryOut(
        movies=int(movies),
        users=CountSplit(
            total=int(users[0]), movielens=int(users[1]), app=int(users[0] - users[1])
        ),
        ratings=CountSplit(
            total=int(ratings[0]),
            movielens=int(ratings[1]),
            app=int(ratings[0] - ratings[1]),
        ),
        interactions={k: int(by_kind.get(k, 0)) for k in INTERACTION_KINDS},
        recommendation_events={
            "shown": int(events.get("shown", 0)),
            "acted": int(events.get("acted", 0)),
        },
        note=(
            "MovieLens figures are historical data imported from the public dataset; "
            "app figures come from registered users of this app. Interactions and "
            "events exist only for the app."
        ),
    )


@router.get("/popular", response_model=list[MovieOut])
def popular(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=50)] = 10
) -> list[MovieOut]:
    """Most-rated movies, over every rating in the database (MovieLens and app)."""
    items, _ = search_movies(
        session,
        q=None,
        genre=None,
        year_min=None,
        year_max=None,
        min_rating=None,
        sort="popularity",
        order="desc",
        page=1,
        page_size=limit,
    )
    return items


@router.get("/ratings-distribution", response_model=RatingDistributionOut)
def ratings_distribution(session: SessionDep) -> RatingDistributionOut:
    historical = User.is_historical.is_(True)
    rows = session.execute(
        select(
            Rating.rating,
            func.count(),
            func.sum(case((historical, 1), else_=0)),
        )
        .join(User, User.id == Rating.user_id)
        .group_by(Rating.rating)
    ).all()
    found = {float(r): (int(t), int(h or 0)) for r, t, h in rows}
    buckets = []
    for value in HALF_STARS:
        total, hist = found.get(value, (0, 0))
        buckets.append(
            RatingBucket(rating=value, total=total, movielens=hist, app=total - hist)
        )
    return RatingDistributionOut(
        buckets=buckets,
        note="Counts of ratings at each half-star value; MovieLens and app separate.",
    )


@router.get("/engagement", response_model=EngagementOut)
def engagement(session: SessionDep) -> EngagementOut:
    """Served and acted-on counts by strategy, from recommendation events only.

    "Served" is a movie returned in a recommendation list by the API, not proof it was
    seen. "Acted" is a later rating, like, dislike, watchlist, watched or view on a
    served movie, once per serving. Neither shows that a recommendation caused the
    action, and there is no comparison group."""
    rows = session.execute(
        select(
            RecommendationEvent.strategy,
            func.count().filter(RecommendationEvent.kind == "shown"),
            func.count().filter(RecommendationEvent.kind == "acted"),
            func.count(func.distinct(RecommendationEvent.user_id)),
        ).group_by(RecommendationEvent.strategy)
    ).all()
    by_strategy = [
        StrategyEngagement(
            strategy=s,
            served=int(a),
            acted=int(b),
            acted_per_served=(round(b / a, 4) if a else None),
            users=int(u),
        )
        for s, a, b, u in sorted(rows)
    ]
    totals = session.execute(
        select(
            func.count().filter(RecommendationEvent.kind == "shown"),
            func.count().filter(RecommendationEvent.kind == "acted"),
            func.count(func.distinct(RecommendationEvent.user_id)),
        )
    ).one()
    return EngagementOut(
        served=int(totals[0]),
        acted=int(totals[1]),
        users=int(totals[2]),
        by_strategy=by_strategy,
        note=(
            "Served = returned by the API in a list (not necessarily seen). Acted = "
            "a later rating, like, dislike, watchlist, watched or view on a served "
            "movie, counted once per serving. These counts do not show that "
            "recommendations caused the actions."
        ),
    )
