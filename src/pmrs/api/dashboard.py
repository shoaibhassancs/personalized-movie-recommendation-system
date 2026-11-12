"""The signed-in user's dashboard: seven panels, each a read-only query, except
"recommended", which goes through the one recommendation service (so its "shown"
events are logged once, by that service, and nowhere else)."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import func, select, union_all
from sqlalchemy.orm import Session

from pmrs.api.catalogue import movies_by_id, search_movies
from pmrs.api.deps import CurrentUser, SessionDep
from pmrs.api.me import genres_of, history_page, watchlist_page
from pmrs.api.recommendations import recommend_for_user
from pmrs.api.schemas import DashboardOut, TrendingItem, TrendingOut
from pmrs.db.models import Interaction, Rating, User

router = APIRouter(prefix="/me", tags=["dashboard"])

PANEL_SIZE = 10
TRENDING_APP_DAYS = 30  # window over activity made in this app
TRENDING_DATASET_DAYS = 365  # fallback window, ending at the dataset's last rating


def trending(session: Session, now: datetime | None = None) -> TrendingOut:
    """Most interactions in a recent window of the app's own data; if the app has
    none in that window, the dataset's latest period, and the response says so.
    An interaction here is a rating or any flag/view by a registered (non-historical)
    user."""
    end = now or session.execute(select(func.now())).scalar_one()
    start = end - timedelta(days=TRENDING_APP_DAYS)
    registered = select(User.id).where(User.is_historical.is_(False))
    app_events = union_all(
        select(Rating.movie_id).where(
            Rating.user_id.in_(registered), Rating.rated_at >= start
        ),
        select(Interaction.movie_id).where(
            Interaction.user_id.in_(registered), Interaction.created_at >= start
        ),
    ).subquery()
    rows = _top(session, app_events)
    if rows:
        return _trending_out(
            session,
            rows,
            "app_activity",
            start,
            end,
            TRENDING_APP_DAYS,
            "Ratings and actions by registered users of this app in the window.",
        )
    last = session.execute(select(func.max(Rating.rated_at))).scalar_one()
    if last is None:
        return TrendingOut(
            source="dataset_latest_period",
            window_start=end,
            window_end=end,
            window_days=TRENDING_DATASET_DAYS,
            note="There are no ratings yet.",
            items=[],
        )
    first = last - timedelta(days=TRENDING_DATASET_DAYS)
    historical = _top(
        session,
        select(Rating.movie_id).where(Rating.rated_at >= first).subquery(),
    )
    return _trending_out(
        session,
        historical,
        "dataset_latest_period",
        first,
        last,
        TRENDING_DATASET_DAYS,
        "No app activity in the last "
        f"{TRENDING_APP_DAYS} days, so this shows the most-rated movies in the final "
        f"{TRENDING_DATASET_DAYS} days of the MovieLens data (ending at its last "
        "rating, not today).",
    )


def _top(session: Session, events: object) -> list[tuple[int, int]]:
    column = events.c.movie_id  # type: ignore[attr-defined]
    rows = session.execute(
        select(column, func.count().label("n"))
        .group_by(column)
        .order_by(func.count().desc(), column)
        .limit(PANEL_SIZE)
    ).all()
    return [(int(m), int(n)) for m, n in rows]


def _trending_out(
    session: Session,
    rows: list[tuple[int, int]],
    source: str,
    start: datetime,
    end: datetime,
    days: int,
    note: str,
) -> TrendingOut:
    movies = movies_by_id(session, [m for m, _ in rows])
    return TrendingOut(
        source=source,
        window_start=start,
        window_end=end,
        window_days=days,
        note=note,
        items=[TrendingItem(movie=movies[m], interactions=n) for m, n in rows],
    )


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(request: Request, user: CurrentUser, session: SessionDep) -> DashboardOut:
    """Recommended (hybrid), trending, popular, newest releases, the caller's genres,
    watchlist and recent activity. "Newest releases" is by release year: it says
    nothing about when a movie was added."""
    recommended = recommend_for_user(
        session, request.app.state.recommender, user.id, "hybrid", PANEL_SIZE
    )
    common = {
        "q": None,
        "genre": None,
        "year_min": None,
        "year_max": None,
        "min_rating": None,
        "page": 1,
        "page_size": PANEL_SIZE,
    }
    popular, _ = search_movies(session, sort="popularity", order="desc", **common)  # type: ignore[arg-type]
    recent, _ = search_movies(session, sort="year", order="desc", **common)  # type: ignore[arg-type]
    return DashboardOut(
        recommended=recommended,
        trending=trending(session),
        popular=popular,
        recent_releases=recent,
        genres=genres_of(session, user.id),
        watchlist=watchlist_page(session, user.id, 1, PANEL_SIZE),
        activity=history_page(session, user.id, 1, PANEL_SIZE),
    )
