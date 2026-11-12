"""Shared fixture: a throwaway PostgreSQL database for the database-backed tests.

Created and dropped once per test module. It refuses to run unless the name ends in
``_test`` and differs from the dev database, so the seeded dev database is never
touched. If no server is reachable the tests are SKIPPED (reported as NOT RUN).
"""

from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError


@pytest.fixture(scope="module")
def test_url() -> Iterator[str]:
    from pmrs.db.settings import load_settings

    try:
        settings = load_settings()
    except Exception:
        pytest.skip("no database settings (.env) found")
    url = settings.test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set")
    parsed = make_url(url)
    dev = make_url(settings.database_url)
    assert parsed.database and parsed.database.endswith("_test")
    assert parsed.database != dev.database  # never touch the dev database
    admin = create_engine(parsed.set(database="postgres"), isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(
                text(f'DROP DATABASE IF EXISTS "{parsed.database}" WITH (FORCE)')
            )
            connection.execute(text(f'CREATE DATABASE "{parsed.database}"'))
    except OperationalError:
        pytest.skip(
            "no PostgreSQL server reachable (start it: docker compose up -d db)"
        )
    yield parsed.render_as_string(hide_password=False)
    with admin.connect() as connection:
        connection.execute(
            text(f'DROP DATABASE IF EXISTS "{parsed.database}" WITH (FORCE)')
        )
