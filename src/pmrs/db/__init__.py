"""Phase 4A: the PostgreSQL schema (SQLAlchemy models) and the MovieLens seed."""

from pmrs.db.models import (
    Base,
    Interaction,
    Movie,
    Rating,
    RecommendationEvent,
    User,
    UserGenre,
)

__all__ = [
    "Base",
    "Interaction",
    "Movie",
    "Rating",
    "RecommendationEvent",
    "User",
    "UserGenre",
]
