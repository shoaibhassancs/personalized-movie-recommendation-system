"""Initial schema: users, movies, user_genres, ratings, interactions, events.

Revision ID: 0001
Revises:
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=100), nullable=False),
        sa.Column("is_historical", sa.Boolean(), nullable=False),
        sa.Column("movielens_user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(is_historical AND movielens_user_id IS NOT NULL"
            " AND email IS NULL AND password_hash IS NULL)"
            " OR (NOT is_historical AND movielens_user_id IS NULL"
            " AND email IS NOT NULL AND password_hash IS NOT NULL)",
            name=op.f("ck_users_historical_users_cannot_log_in"),
        ),
        sa.CheckConstraint(
            "email = lower(email)", name=op.f("ck_users_email_lowercase")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint(
            "movielens_user_id", name=op.f("uq_users_movielens_user_id")
        ),
    )
    op.create_table(
        "movies",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column(
            "genres",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("tag_text", sa.Text(), server_default="", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movies")),
    )
    op.create_table(
        "user_genres",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("genre", sa.String(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_genres_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "genre", name=op.f("pk_user_genres")),
    )
    op.create_table(
        "ratings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Numeric(precision=2, scale=1), nullable=False),
        sa.Column("rated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "rating >= 0.5 AND rating <= 5 AND rating * 2 = trunc(rating * 2)",
            name=op.f("ck_ratings_half_star_between_0_5_and_5"),
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movies.id"],
            name=op.f("fk_ratings_movie_id_movies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ratings_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "movie_id", name=op.f("pk_ratings")),
    )
    op.create_index("ix_ratings_movie_id", "ratings", ["movie_id"])
    op.create_table(
        "interactions",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('like', 'dislike', 'watchlist', 'watched', 'viewed')",
            name=op.f("ck_interactions_kind_known"),
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movies.id"],
            name=op.f("fk_interactions_movie_id_movies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_interactions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interactions")),
        sa.UniqueConstraint(
            "user_id", "movie_id", "kind", name=op.f("uq_interactions_user_id")
        ),
    )
    op.create_index("ix_interactions_movie_id", "interactions", ["movie_id"])
    op.create_table(
        "recommendation_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("movie_id", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(length=30), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('shown', 'acted')",
            name=op.f("ck_recommendation_events_kind_known"),
        ),
        sa.ForeignKeyConstraint(
            ["movie_id"],
            ["movies.id"],
            name=op.f("fk_recommendation_events_movie_id_movies"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_recommendation_events_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendation_events")),
    )
    op.create_index(
        "ix_recommendation_events_user_id", "recommendation_events", ["user_id"]
    )


def downgrade() -> None:
    op.drop_table("recommendation_events")
    op.drop_table("interactions")
    op.drop_table("ratings")
    op.drop_table("user_genres")
    op.drop_table("movies")
    op.drop_table("users")
