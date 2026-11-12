"""Recommendations for the signed-in user, from the frozen serving artifact.

The profile is built from the caller's own ratings and favourite genres only. Likes,
dislikes, watched and watchlist are NOT inputs to any model (owner decision, D-039);
watched and disliked movies are only removed from the displayed list afterwards. The
models, the artifact and the hybrid routing are the frozen ones: no model code here.

Exposed strategies: hybrid, popularity, content, item_knn, svd. ``random``,
``bayesian_average`` and ``content_no_tags`` exist for the offline evaluation only.

The serving artifact was fitted on all MovieLens data and has no separate quality
metric. The Step 16 results describe a differently fitted model (``evaluated_step16``)
and compare methods under one offline holdout protocol; they do not show that these
lists are good for any person.
"""

from collections.abc import Container, Mapping
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from pmrs.api.catalogue import MAX_PAGE_SIZE, movies_by_id, states_for
from pmrs.api.deps import CurrentUser, SessionDep
from pmrs.api.events import record_served
from pmrs.api.schemas import RecommendationItem, RecommendationsOut
from pmrs.db.models import Interaction, Rating, UserGenre
from pmrs.recommender.recommender import RecommendationList, UserProfile

Strategy = Literal["hybrid", "popularity", "content", "item_knn", "svd"]
EXPOSED: tuple[str, ...] = ("hybrid", "popularity", "content", "item_knn", "svd")
NEEDS_RATINGS = ("content", "item_knn", "svd")
MAX_K = MAX_PAGE_SIZE
MODEL_NOTICE = (
    "These lists come from the serving model, fitted on all MovieLens data. It has no "
    "separate quality metric. The Step 16 offline results describe a different, "
    "separately fitted model, compare methods under one holdout protocol only, and do "
    "not show that these lists suit you."
)

router = APIRouter(prefix="/me", tags=["recommendations"])


class _Config(Protocol):
    @property
    def few_max(self) -> int: ...


class Recommending(Protocol):
    """What this module needs from the shared ``Recommender`` (tests can stand in)."""

    @property
    def item_map(self) -> Container[int]: ...

    @property
    def genre_names(self) -> Mapping[str, str]: ...

    @property
    def config(self) -> _Config: ...

    def recommend(
        self, profile: UserProfile, strategy: str = "hybrid", k: int = 10
    ) -> RecommendationList: ...


def _reason(strategy: str, branch: str | None, n: int, few_max: int) -> str:
    if strategy != "hybrid":
        label = {
            "popularity": "ranked by how many people rated each movie",
            "content": "ranked by similarity to movies you rated (genres and tags)",
            "item_knn": "ranked by movies rated similarly to ones you rated",
            "svd": "ranked by a latent-factor model of rating patterns",
        }[strategy]
        return f"A single method, shown so you can compare it with the hybrid: {label}."
    if branch == "no_ratings":
        return (
            "You have no ratings, so this is not personalised from your history: it "
            "uses your favourite genres with overall popularity if you chose genres, "
            "and popularity alone if you did not."
        )
    if branch == "few_ratings":
        return (
            f"You have {n} rating(s). Up to {few_max} ratings the hybrid ranks by "
            "popularity, so this list is not personalised."
        )
    return (
        f"You have {n} ratings, so the full hybrid blend of content, item-neighbour, "
        "SVD and popularity scores is used."
    )


def _profile(
    session: Session, recommender: Recommending, user_id: int
) -> tuple[UserProfile, int, list[str]]:
    notes: list[str] = []
    ratings: dict[int, float] = {}
    skipped = 0
    for row in session.execute(select(Rating).where(Rating.user_id == user_id)):
        rating = row[0]
        if rating.movie_id in recommender.item_map:
            ratings[rating.movie_id] = float(rating.rating)
        else:
            skipped += 1
    if skipped:
        notes.append(f"{skipped} rated movie(s) are not in the model and were ignored.")
    names = session.execute(
        select(UserGenre.genre).where(UserGenre.user_id == user_id)
    ).scalars()
    genres = tuple(g for g in names if g.lower() in recommender.genre_names)
    return UserProfile(ratings, genres), len(ratings), notes


def recommend_for_user(
    session: Session,
    recommender: Recommending,
    user_id: int,
    strategy: str = "hybrid",
    k: int = 10,
) -> RecommendationsOut:
    """Build the profile, call the shared recommender, filter, and log "shown" once.

    The only place recommendations are produced and served events are logged, so a
    caller (the route, the dashboard) that goes through it logs each list exactly once.
    """
    profile, n_ratings, notes = _profile(session, recommender, user_id)
    hidden = set(
        session.execute(
            select(Interaction.movie_id).where(
                Interaction.user_id == user_id,
                Interaction.kind.in_(("watched", "dislike")),
            )
        ).scalars()
    )
    few_max = recommender.config.few_max
    branch: str | None = None
    score_kind = "none"
    ordered: list[RecommendationItem] = []
    if strategy in NEEDS_RATINGS and n_ratings == 0:
        notes.append(
            f"The {strategy} method needs at least one rating, so it returns nothing "
            "for you yet. Rate a movie, or use hybrid or popularity."
        )
    else:
        result = recommender.recommend(profile, strategy, k + len(hidden))
        branch, score_kind = result.branch, result.score_kind
        notes.extend(result.notes)
        if strategy in NEEDS_RATINGS and n_ratings <= few_max:
            notes.append(
                "This method was only evaluated for users with many ratings; with "
                f"{n_ratings} it is shown for comparison and may be unreliable."
            )
        kept = [item for item in result.items if item.movie_id not in hidden][:k]
        details = movies_by_id(session, [item.movie_id for item in kept])
        states = states_for(session, user_id, [item.movie_id for item in kept])
        ordered = [
            RecommendationItem(
                movie=details[item.movie_id],
                score=item.score,
                explanation=item.explanation,
                source=item.source,
                state=states[item.movie_id],
            )
            for item in kept
            if item.movie_id in details
        ]
    logged = record_served(session, user_id, strategy, [i.movie.id for i in ordered])
    session.commit()
    return RecommendationsOut(
        strategy=strategy,
        branch=branch,
        branch_reason=_reason(strategy, branch, n_ratings, few_max),
        score_kind=score_kind,
        rating_count=n_ratings,
        items=ordered,
        notes=notes,
        served_events_logged=logged,
        model_notice=MODEL_NOTICE,
    )


@router.get("/recommendations", response_model=RecommendationsOut)
def recommendations(
    request: Request,
    user: CurrentUser,
    session: SessionDep,
    strategy: Annotated[
        Strategy,
        Query(
            description=(
                "hybrid (default), popularity, content, item_knn or svd. random, "
                "bayesian_average and content_no_tags are offline-evaluation methods "
                "and are not available here."
            )
        ),
    ] = "hybrid",
    k: Annotated[int, Query(ge=1, le=MAX_K)] = 10,
) -> RecommendationsOut:
    """Up to ``k`` movies for the caller, never one they rated, watched or disliked.

    Each call logs one ``shown`` event per returned movie, meaning *served by the API*
    (not seen, and not a measure of effect). The user always comes from the token.
    """
    return recommend_for_user(
        session, request.app.state.recommender, user.id, strategy, k
    )
