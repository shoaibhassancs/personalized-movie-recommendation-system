"""The database schema (ARCHITECTURE.md section 4), as SQLAlchemy 2 models.

Historical users. The 610 MovieLens users are rows with ``is_historical`` true. A check
constraint makes the database itself refuse a historical user that has an email or a
password hash, and a registered user that lacks them. So no login credential can ever
exist for a historical user, whatever the application code does. Login code must in
addition look users up by email only and ignore historical rows (Step 20).

Ratings keep MovieLens' original timestamps (``rated_at``), never the import time.
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

INTERACTION_KINDS = ("like", "dislike", "watchlist", "watched", "viewed")
EVENT_KINDS = ("shown", "acted")

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "(is_historical AND movielens_user_id IS NOT NULL"
            " AND email IS NULL AND password_hash IS NULL)"
            " OR (NOT is_historical AND movielens_user_id IS NULL"
            " AND email IS NOT NULL AND password_hash IS NOT NULL)",
            name="historical_users_cannot_log_in",
        ),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    display_name: Mapped[str] = mapped_column(String(100))
    is_historical: Mapped[bool] = mapped_column(Boolean, default=False)
    movielens_user_id: Mapped[int | None] = mapped_column(Integer, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Movie(Base):
    __tablename__ = "movies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(Text)  # as in MovieLens, e.g. "Heat (1995)"
    year: Mapped[int | None] = mapped_column(Integer)
    genres: Mapped[list[str]] = mapped_column(ARRAY(Text), server_default=text("'{}'"))
    tag_text: Mapped[str] = mapped_column(Text, server_default="")


class UserGenre(Base):
    __tablename__ = "user_genres"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    genre: Mapped[str] = mapped_column(String(50), primary_key=True)


class Rating(Base):
    __tablename__ = "ratings"
    __table_args__ = (
        CheckConstraint(
            "rating >= 0.5 AND rating <= 5 AND rating * 2 = trunc(rating * 2)",
            name="half_star_between_0_5_and_5",
        ),
        Index("ix_ratings_movie_id", "movie_id"),
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    movie_id: Mapped[int] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), primary_key=True
    )
    rating: Mapped[Decimal] = mapped_column(Numeric(2, 1))
    rated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Interaction(Base):
    __tablename__ = "interactions"
    __table_args__ = (
        UniqueConstraint("user_id", "movie_id", "kind"),
        CheckConstraint(_in_list("kind", INTERACTION_KINDS), name="kind_known"),
        Index("ix_interactions_movie_id", "movie_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"
    __table_args__ = (
        CheckConstraint(_in_list("kind", EVENT_KINDS), name="kind_known"),
        Index("ix_recommendation_events_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    movie_id: Mapped[int] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    strategy: Mapped[str] = mapped_column(String(30))
    kind: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
