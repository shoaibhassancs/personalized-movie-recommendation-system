"""Phase 4A tests: schema, migrations and the MovieLens seed.

The first group needs no database. The second group needs the separate TEST database
(``TEST_DATABASE_URL``, name ending ``_test``). When no server is reachable those
tests are SKIPPED, which this project reports as NOT RUN, never as passed.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from pmrs.data import MovieLensData, ValidationReport
from pmrs.db import Base
from pmrs.db.seed import prepare, seed, tag_text_by_movie, verify
from pmrs.db.settings import DatabaseSettings

ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "users",
    "movies",
    "user_genres",
    "ratings",
    "interactions",
    "recommendation_events",
}
T0 = 1_000_000_000  # 2001-09-09 UTC


def toy_data() -> MovieLensData:
    movies = pd.DataFrame(
        {
            "movie_id": [1, 2, 3],
            "title": ["Alpha (1999)", "Beta", "Gamma (2005)"],
            "genres": [("Action", "Comedy"), (), ("Drama",)],
            "title_clean": ["Alpha", "Beta", "Gamma"],
            "year": pd.array([1999, None, 2005], dtype="Int64"),
        }
    )
    ratings = pd.DataFrame(
        {
            "user_id": [10, 10, 20, 20, 30],
            "movie_id": [1, 2, 1, 3, 3],
            "rating": [5.0, 0.5, 3.5, 4.0, 2.5],
            "timestamp": [T0, T0 + 5, T0 + 10, T0 + 20, T0 + 30],
        }
    )
    tags = pd.DataFrame(
        {
            "user_id": [10, 40, 40, 20],
            "movie_id": [1, 1, 1, 3],
            "tag": ["funny", "funny", " Dark ", "  "],
            "timestamp": [T0, T0, T0, T0],
        }
    )
    return MovieLensData(ratings, movies, tags, ValidationReport())


# ---- no database needed -------------------------------------------------------------


def test_prepare_keeps_original_timestamps_and_marks_users_historical() -> None:
    rows = prepare(toy_data())
    assert [u["movielens_user_id"] for u in rows.users] == [
        10,
        20,
        30,
        40,
    ]  # incl. tagger
    assert all(u["is_historical"] for u in rows.users)
    assert all(u["email"] is None and u["password_hash"] is None for u in rows.users)
    first = rows.ratings[0]
    assert first["rated_at"] == datetime.fromtimestamp(T0, tz=UTC)  # not import time
    assert first["rating"] == Decimal("5.0")
    assert {m["id"]: m["year"] for m in rows.movies} == {1: 1999, 2: None, 3: 2005}
    assert [m["genres"] for m in rows.movies] == [["Action", "Comedy"], [], ["Drama"]]


def test_tag_text_is_distinct_sorted_and_skips_blank_tags() -> None:
    assert tag_text_by_movie(toy_data().tags) == {1: "Dark, funny"}


def test_schema_declares_the_login_safeguard_and_the_rating_rule() -> None:
    users = Base.metadata.tables["users"]
    names = {c.name for c in users.constraints}
    assert "ck_users_historical_users_cannot_log_in" in names
    assert "ck_users_email_lowercase" in names
    assert {"ck_ratings_half_star_between_0_5_and_5"} <= {
        c.name for c in Base.metadata.tables["ratings"].constraints
    }
    assert set(Base.metadata.tables) == TABLES


def test_settings_never_print_the_url_and_no_secret_is_committed() -> None:
    settings = DatabaseSettings(database_url="postgresql://u:topsecret@h/db")
    assert "topsecret" not in repr(settings)
    for name in (".env.example", "compose.yaml"):
        text_ = (ROOT / name).read_text()
        assert "postgresql+psycopg://pmrs:" not in text_
    example = (ROOT / ".env.example").read_text()
    assert "POSTGRES_PASSWORD=\n" in example and "DATABASE_URL=\n" in example


# ---- needs the separate test database -----------------------------------------------


def _config(url: str) -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", url)
    return config


@pytest.fixture()
def engine(test_url: str) -> Iterator[Engine]:
    config = _config(test_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    eng = create_engine(test_url)
    yield eng
    eng.dispose()


def test_migration_goes_up_and_down_on_an_empty_database(test_url: str) -> None:
    config = _config(test_url)
    eng = create_engine(test_url)
    command.downgrade(config, "base")
    assert TABLES.isdisjoint(inspect(eng).get_table_names())
    command.upgrade(config, "head")
    assert TABLES <= set(inspect(eng).get_table_names())
    command.downgrade(config, "base")
    assert TABLES.isdisjoint(inspect(eng).get_table_names())
    command.upgrade(config, "head")  # and up again
    eng.dispose()


def test_migration_matches_the_models(engine: Engine) -> None:
    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        assert compare_metadata(context, Base.metadata) == []


def test_database_refuses_bad_users_ratings_and_interactions(engine: Engine) -> None:
    def refused(sql: str) -> None:
        with pytest.raises(IntegrityError), engine.begin() as connection:
            connection.execute(text(sql))

    with engine.begin() as connection:
        connection.execute(text("INSERT INTO movies (id, title) VALUES (1, 'M')"))
        connection.execute(
            text(
                "INSERT INTO users (email, password_hash, display_name, is_historical)"
                " VALUES ('a@x.org', 'h', 'A', false)"
            )
        )
    user_cols = "(display_name, is_historical, email, password_hash, movielens_user_id)"
    refused(  # a historical user with an email could be signed in as
        f"INSERT INTO users {user_cols} VALUES ('H', true, 'h@x.org', null, 7)"
    )
    refused(f"INSERT INTO users {user_cols} VALUES ('H', true, null, 'hash', 7)")
    refused(f"INSERT INTO users {user_cols} VALUES ('R', false, null, null, null)")
    refused(f"INSERT INTO users {user_cols} VALUES ('R', false, 'B@x.org', 'h', null)")
    refused(f"INSERT INTO users {user_cols} VALUES ('R', false, 'a@x.org', 'h', null)")
    refused(f"INSERT INTO users {user_cols} VALUES ('H', true, null, null, null)")
    uid = "(SELECT id FROM users LIMIT 1)"
    ok = f"INSERT INTO ratings VALUES ({uid}, 1, 4.5, now())"
    with engine.begin() as connection:
        connection.execute(text(ok))
    refused(ok)  # same user and movie twice
    refused(f"INSERT INTO ratings VALUES ({uid}, 1, 3.3, now())")
    refused(f"INSERT INTO ratings VALUES ({uid}, 1, 0, now())")
    refused(f"INSERT INTO ratings VALUES ({uid}, 1, 5.5, now())")
    inter = f"INSERT INTO interactions (user_id, movie_id, kind) VALUES ({uid}, 1, "
    with engine.begin() as connection:
        connection.execute(text(inter + "'like')"))
    refused(inter + "'like')")
    refused(inter + "'adore')")


def test_seed_adds_data_once_keeps_timestamps_and_is_safe_to_repeat(
    engine: Engine,
) -> None:
    data = toy_data()
    first = seed(engine, data)
    assert (first.users_added, first.movies_added, first.ratings_added) == (4, 3, 5)
    assert verify(engine, data) == []
    second = seed(engine, data)
    assert (second.users_added, second.movies_added, second.ratings_added) == (0, 0, 0)
    assert verify(engine, data) == []
    with engine.connect() as connection:
        stamp = connection.execute(
            text("SELECT extract(epoch FROM min(rated_at))::bigint FROM ratings")
        ).scalar_one()
        credentials = connection.execute(
            text(
                "SELECT count(*) FROM users WHERE is_historical"
                " AND (email IS NOT NULL OR password_hash IS NOT NULL)"
            )
        ).scalar_one()
        non_historical = connection.execute(
            text("SELECT count(*) FROM users WHERE NOT is_historical")
        ).scalar_one()
    assert stamp == T0
    assert credentials == 0
    assert non_historical == 0


def test_verify_notices_a_changed_row(engine: Engine) -> None:
    data = toy_data()
    seed(engine, data)
    with engine.begin() as connection:
        connection.execute(text("UPDATE ratings SET rating = 1.0 WHERE movie_id = 2"))
    assert any("ratings" in p for p in verify(engine, data))
    with engine.begin() as connection:
        connection.execute(text("UPDATE movies SET title = 'Changed' WHERE id = 1"))
    assert any("movies" in p for p in verify(engine, data))


def test_seed_does_not_disturb_registered_users(engine: Engine) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (email, password_hash, display_name, is_historical)"
                " VALUES ('me@x.org', 'h', 'Me', false)"
            )
        )
    seed(engine, toy_data())
    seed(engine, toy_data())
    with engine.connect() as connection:
        mine = connection.execute(
            text("SELECT count(*) FROM users WHERE email = 'me@x.org'")
        ).scalar_one()
    assert mine == 1
