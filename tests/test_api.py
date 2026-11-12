"""Chunk 4B tests: accounts, historical-user protection, account deletion, catalogue
and interactions, run against the separate TEST database with a tiny invented catalogue.

The catalogue is built so every expected answer can be worked out by hand:

    id  title               year  genres          ratings (by historical users)  avg   n
    1   Alpha Run (1990)    1990  Action          5, 5, 4.5, 4.5, 4              4.6   5
    2   Beta Night (1995)   1995  Action, Comedy  3 x 6                          3.0   6
    3   Gamma_Ray (2000)    2000  Comedy          2 x 5                          2.0   5
    4   Delta 100% (2005)   2005  Drama           5, 5                           5.0   2
    5   Epsilon (2010)      2010  Drama, Comedy   none                           -     0
    6   Zeta                none  none            4                              4.0   1

These are mechanics tests on a small fixture. They do not audit security, measure speed
or show how the API behaves under load.
"""

import logging
from collections.abc import Iterator
from pathlib import Path
from types import SimpleNamespace

import jwt
import pandas as pd
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, create_engine, text

from pmrs.api.app import create_app
from pmrs.api.security import create_token
from pmrs.api.settings import ApiSettings
from pmrs.data import MovieLensData, ValidationReport
from pmrs.db.seed import seed
from pmrs.recommender.explain import Evidence
from pmrs.recommender.recommender import (
    Recommendation,
    RecommendationList,
    UserProfile,
)

ROOT = Path(__file__).resolve().parents[1]
SECRET = "test-only-secret-" + "k" * 40  # a fixed test value, not a real secret
PASSWORD = "correct horse battery staple"
T0 = 1_000_000_000


def catalogue_data() -> MovieLensData:
    movies = pd.DataFrame(
        {
            "movie_id": [1, 2, 3, 4, 5, 6],
            "title": [
                "Alpha Run (1990)",
                "Beta Night (1995)",
                "Gamma_Ray (2000)",
                "Delta 100% (2005)",
                "Epsilon (2010)",
                "Zeta",
            ],
            "genres": [
                ("Action",),
                ("Action", "Comedy"),
                ("Comedy",),
                ("Drama",),
                ("Drama", "Comedy"),
                (),
            ],
            "title_clean": [
                "Alpha Run",
                "Beta Night",
                "Gamma_Ray",
                "Delta 100%",
                "Epsilon",
                "Zeta",
            ],
            "year": pd.array([1990, 1995, 2000, 2005, 2010, None], dtype="Int64"),
        }
    )
    given = {
        1: [5, 5, 4.5, 4.5, 4],
        2: [3, 3, 3, 3, 3, 3],
        3: [2, 2, 2, 2, 2],
        4: [5, 5],
        6: [4],
    }
    rows = [
        (user, movie, float(value))
        for movie, values in given.items()
        for user, value in enumerate(values, start=1)
    ]
    ratings = pd.DataFrame(
        {
            "user_id": [r[0] for r in rows],
            "movie_id": [r[1] for r in rows],
            "rating": [r[2] for r in rows],
            "timestamp": [T0 + i for i in range(len(rows))],
        }
    )
    tags = pd.DataFrame(
        {
            "user_id": [1, 1],
            "movie_id": [1, 1],
            "tag": ["retro", "classic"],
            "timestamp": [T0, T0],
        }
    )
    return MovieLensData(ratings, movies, tags, ValidationReport())


@pytest.fixture(scope="module")
def engine(test_url: str) -> Iterator[Engine]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    eng = create_engine(test_url)
    yield eng
    eng.dispose()


class StubRecommender:
    """Stands in for the real Recommender in tests that do not need real models: a
    fixed order over the six fixture movies, minus what the profile already rated."""

    item_map = frozenset({1, 2, 3, 4, 5, 6})
    genre_names = {"action": "Action", "comedy": "Comedy", "drama": "Drama"}
    config = SimpleNamespace(few_max=10)
    order = (2, 1, 3, 4, 6, 5)

    def recommend(
        self, profile: UserProfile, strategy: str = "hybrid", k: int = 10
    ) -> RecommendationList:
        n = len(profile.ratings)
        branch = None
        if strategy == "hybrid":
            branch = "no_ratings" if n == 0 else "few_ratings" if n <= 10 else "many"
        items = tuple(
            Recommendation(
                movie_id=m,
                title=f"stub {m}",
                genres=(),
                score=float(10 - m),
                explanation=f"stub sentence {m}",
                evidence=Evidence("no_evidence"),
                source="popularity",
            )
            for m in self.order
            if m not in profile.ratings
        )[:k]
        return RecommendationList(strategy, branch, "rating count", items)  # type: ignore[arg-type]


@pytest.fixture()
def client(engine: Engine) -> TestClient:
    with engine.begin() as connection:
        connection.execute(
            text(
                "TRUNCATE users, movies, user_genres, ratings, interactions,"
                " recommendation_events RESTART IDENTITY CASCADE"
            )
        )
    seed(engine, catalogue_data())
    app = create_app(ApiSettings(jwt_secret=SECRET), engine, StubRecommender())
    return TestClient(app)


def scalar(engine: Engine, sql: str, **params: object) -> object:
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def signup(
    client: TestClient, email: str = "ann@example.org", password: str = PASSWORD
) -> dict[str, str]:
    created = client.post(
        "/auth/register",
        json={"email": email, "password": password, "display_name": "Ann"},
    )
    assert created.status_code == 201, created.text
    login = client.post("/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200, login.text
    return {"Authorization": f"Bearer {login.json()['access_token']}"}


def ids(response: object) -> list[int]:
    body = response.json()  # type: ignore[attr-defined]
    return [item["id"] for item in body["items"]]


# ---- registration and login --------------------------------------------------


def test_register_returns_no_secrets_and_stores_an_argon2id_hash(
    client: TestClient, engine: Engine
) -> None:
    response = client.post(
        "/auth/register",
        json={
            "email": "  Ann@Example.ORG ",
            "password": PASSWORD,
            "display_name": "Ann",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"id", "email", "display_name", "genres", "created_at"}
    assert body["email"] == "ann@example.org"
    stored = str(
        scalar(engine, "SELECT password_hash FROM users WHERE id = :i", i=body["id"])
    )
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored and "password" not in response.text.lower()
    assert (
        scalar(engine, "SELECT is_historical FROM users WHERE id = :i", i=body["id"])
        is False
    )


def test_duplicate_email_is_refused_whatever_its_case(client: TestClient) -> None:
    signup(client)
    again = client.post(
        "/auth/register",
        json={
            "email": "ANN@example.org",
            "password": PASSWORD,
            "display_name": "Other",
        },
    )
    assert again.status_code == 409


def test_password_length_rules_and_no_silent_truncation(client: TestClient) -> None:
    def register(n: int, password: str) -> int:
        return client.post(
            "/auth/register",
            json={
                "email": f"u{n}@example.org",
                "password": password,
                "display_name": "U",
            },
        ).status_code

    assert register(1, "x" * 14) == 422
    assert register(2, "x" * 15) == 201
    assert register(3, "y" * 128) == 201
    assert register(4, "z" * 129) == 422
    assert register(5, " " * 15) == 422
    # passphrases with spaces and non-ASCII letters are fine, exactly as typed
    phrase = "Zażółć gęślą jaźń 🙂 ok!"
    assert register(6, phrase) == 201
    ok = client.post(
        "/auth/login", json={"email": "u6@example.org", "password": phrase}
    )
    assert ok.status_code == 200
    # a trailing space is part of the password, and nothing is cut off at 72 bytes
    long = "y" * 128
    full = client.post(
        "/auth/login", json={"email": "u3@example.org", "password": long}
    )
    cut = client.post(
        "/auth/login", json={"email": "u3@example.org", "password": long[:72]}
    )
    assert full.status_code == 200 and cut.status_code == 401
    spaced = client.post(
        "/auth/login", json={"email": "u2@example.org", "password": "x" * 15 + " "}
    )
    assert spaced.status_code == 401


def test_validation_errors_do_not_echo_the_submitted_password(
    client: TestClient,
) -> None:
    response = client.post(
        "/auth/register",
        json={"email": "a@example.org", "password": "short-pw-1", "display_name": "A"},
    )
    assert response.status_code == 422
    assert "short-pw-1" not in response.text
    bad_email = client.post(
        "/auth/register",
        json={"email": "not-an-email", "password": PASSWORD, "display_name": "A"},
    )
    assert bad_email.status_code == 422


def test_wrong_password_and_unknown_email_look_the_same(client: TestClient) -> None:
    signup(client)
    wrong = client.post(
        "/auth/login",
        json={"email": "ann@example.org", "password": "not the password!"},
    )
    unknown = client.post(
        "/auth/login", json={"email": "nobody@example.org", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_returns_a_sixty_minute_token(client: TestClient) -> None:
    signup(client)
    body = client.post(
        "/auth/login", json={"email": "ann@example.org", "password": PASSWORD}
    ).json()
    assert body["token_type"] == "bearer" and body["expires_in"] == 3600
    claims = jwt.decode(body["access_token"], SECRET, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == 3600


def test_missing_expired_forged_and_tampered_tokens_are_refused(
    client: TestClient,
) -> None:
    headers = signup(client)
    assert client.get("/me", headers=headers).status_code == 200
    assert client.get("/me").status_code == 401
    user_id = client.get("/me", headers=headers).json()["id"]
    good = headers["Authorization"].split()[1]
    claims = jwt.decode(good, SECRET, algorithms=["HS256"])
    bad = {
        "garbage": "not-a-token",
        "expired": create_token(user_id, SECRET, -1),
        "wrong secret": create_token(user_id, "another-secret-" + "z" * 40, 60),
        "tampered": good[:-3] + ("AAA" if not good.endswith("AAA") else "BBB"),
        "alg none": jwt.encode(claims, None, algorithm="none"),
        "no expiry": jwt.encode({"sub": str(user_id)}, SECRET, algorithm="HS256"),
        "non-numeric sub": jwt.encode(
            {**claims, "sub": "abc"}, SECRET, algorithm="HS256"
        ),
    }
    for name, token in bad.items():
        response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 401, name
    wrong_scheme = client.get("/me", headers={"Authorization": f"Basic {good}"})
    assert wrong_scheme.status_code == 401


def test_the_app_will_not_start_without_a_strong_secret(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)  # so no .env is read
    monkeypatch.delenv("JWT_SECRET", raising=False)
    with pytest.raises(ValidationError):
        ApiSettings()  # type: ignore[call-arg]
    with pytest.raises(ValidationError):
        ApiSettings(jwt_secret="too-short")
    assert SECRET not in repr(ApiSettings(jwt_secret=SECRET))


def test_logs_do_not_contain_passwords_or_secrets(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        headers = signup(client)
        client.get("/me", headers=headers)
        client.post(
            "/auth/login",
            json={"email": "ann@example.org", "password": "wrong password!!"},
        )
    assert PASSWORD not in caplog.text and "wrong password!!" not in caplog.text
    assert SECRET not in caplog.text
    assert headers["Authorization"].split()[1] not in caplog.text


# ---- historical users stay out -----------------------------------------------


def test_historical_users_cannot_log_in_or_act_even_with_a_forged_token(
    client: TestClient, engine: Engine
) -> None:
    historical = int(scalar(engine, "SELECT min(id) FROM users WHERE is_historical"))  # type: ignore[call-overload]
    users_before = scalar(engine, "SELECT count(*) FROM users WHERE is_historical")
    ratings_before = scalar(engine, "SELECT count(*) FROM ratings")
    assert (
        scalar(
            engine,
            "SELECT count(*) FROM users WHERE is_historical AND (email IS NOT NULL"
            " OR password_hash IS NOT NULL)",
        )
        == 0
    )
    for email in ("", "none", "null", "MovieLens user 1", "None"):
        attempt = client.post(
            "/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert attempt.status_code in (401, 422)
    forged = {"Authorization": "Bearer " + create_token(historical, SECRET, 60)}
    assert client.get("/me", headers=forged).status_code == 401
    assert (
        client.put("/me", json={"display_name": "x"}, headers=forged).status_code == 401
    )
    assert client.delete("/me", headers=forged).status_code == 401
    assert (
        client.put("/movies/1/rating", json={"rating": 1}, headers=forged).status_code
        == 401
    )
    assert client.get("/me/history", headers=forged).status_code == 401
    assert (
        scalar(engine, "SELECT count(*) FROM users WHERE is_historical") == users_before
    )
    assert scalar(engine, "SELECT count(*) FROM ratings") == ratings_before


def test_no_route_takes_a_user_id_and_no_response_names_a_historical_user(
    client: TestClient,
) -> None:
    assert not [r for r in client.app.routes if "user_id" in getattr(r, "path", "")]  # type: ignore[attr-defined]
    headers = signup(client)
    client.put("/movies/1/rating", json={"rating": 4}, headers=headers)
    for url in ("/me", "/me/history", "/me/watchlist", "/movies", "/movies/1"):
        text_ = client.get(url, headers=headers).text.lower()
        assert "movielens_user_id" not in text_ and "password" not in text_


# ---- profile, isolation and deletion -----------------------------------------


def test_profile_and_favourite_genres(client: TestClient) -> None:
    headers = signup(client)
    renamed = client.put("/me", json={"display_name": "  Ann B "}, headers=headers)
    assert renamed.json()["display_name"] == "Ann B"
    assert (
        client.put("/me", json={"display_name": "  "}, headers=headers).status_code
        == 422
    )
    chosen = client.put(
        "/me/genres", json={"genres": ["comedy", "ACTION", "action"]}, headers=headers
    )
    assert chosen.json()["genres"] == ["Action", "Comedy"]
    assert client.get("/me", headers=headers).json()["genres"] == ["Action", "Comedy"]
    replaced = client.put("/me/genres", json={"genres": ["Drama"]}, headers=headers)
    assert replaced.json()["genres"] == ["Drama"]
    bad = client.put(
        "/me/genres", json={"genres": ["Drama", "Nonsense"]}, headers=headers
    )
    assert bad.status_code == 422
    assert client.get("/me", headers=headers).json()["genres"] == ["Drama"]


def test_users_cannot_see_each_others_data(client: TestClient) -> None:
    ann = signup(client, "ann@example.org")
    bob = signup(client, "bob@example.org")
    client.put("/movies/1/rating", json={"rating": 4}, headers=ann)
    client.put("/movies/1/like", headers=ann)
    client.put("/movies/2/watchlist", headers=ann)
    assert client.get("/me/history", headers=ann).json()["total"] == 2
    assert client.get("/me/history", headers=bob).json()["total"] == 0
    assert client.get("/me/watchlist", headers=bob).json()["total"] == 0
    seen_by_bob = client.get("/movies/1", headers=bob).json()["me"]
    assert seen_by_bob == {
        "rating": None,
        "liked": False,
        "disliked": False,
        "watchlist": False,
        "watched": False,
        "viewed_at": None,
    }
    assert client.get("/movies/1", headers=ann).json()["me"]["rating"] == 4.0


def test_delete_me_removes_only_the_callers_account_and_data(
    client: TestClient, engine: Engine
) -> None:
    ann = signup(client, "ann@example.org")
    bob = signup(client, "bob@example.org")
    for headers in (ann, bob):
        client.put("/movies/1/rating", json={"rating": 3}, headers=headers)
        client.put("/movies/2/like", headers=headers)
        client.put("/me/genres", json={"genres": ["Drama"]}, headers=headers)
    ann_id = client.get("/me", headers=ann).json()["id"]
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO recommendation_events (user_id, movie_id, strategy, kind)"
                " VALUES (:u, 1, 'hybrid', 'shown')"
            ),
            {"u": ann_id},
        )
    historical_users = scalar(engine, "SELECT count(*) FROM users WHERE is_historical")
    historical_ratings = scalar(
        engine,
        "SELECT count(*) FROM ratings r JOIN users u ON u.id = r.user_id"
        " WHERE u.is_historical",
    )
    assert client.delete("/me", headers=ann).status_code == 204
    for table in (
        "users",
        "ratings",
        "interactions",
        "user_genres",
        "recommendation_events",
    ):
        column = "id" if table == "users" else "user_id"
        assert (
            scalar(
                engine, f"SELECT count(*) FROM {table} WHERE {column} = :i", i=ann_id
            )
            == 0
        )
    assert client.get("/me", headers=ann).status_code == 401  # the old token is dead
    assert client.delete("/me", headers=ann).status_code == 401
    assert client.get("/me", headers=bob).status_code == 200
    assert client.get("/me/history", headers=bob).json()["total"] == 2
    assert (
        scalar(engine, "SELECT count(*) FROM users WHERE is_historical")
        == historical_users
    )
    assert (
        scalar(
            engine,
            "SELECT count(*) FROM ratings r JOIN users u ON u.id = r.user_id"
            " WHERE u.is_historical",
        )
        == historical_ratings
    )
    assert scalar(engine, "SELECT count(*) FROM movies") == 6
    # the email can be registered again afterwards
    assert (
        client.post(
            "/auth/register",
            json={
                "email": "ann@example.org",
                "password": PASSWORD,
                "display_name": "Ann",
            },
        ).status_code
        == 201
    )


# ---- catalogue ---------------------------------------------------------------


def test_catalogue_is_public_and_shows_hand_checked_numbers(client: TestClient) -> None:
    response = client.get("/movies")  # no login
    body = response.json()
    assert response.status_code == 200 and body["total"] == 6
    by_id = {m["id"]: m for m in body["items"]}
    assert by_id[1]["average_rating"] == 4.6 and by_id[1]["rating_count"] == 5
    assert by_id[2]["average_rating"] == 3.0 and by_id[2]["rating_count"] == 6
    assert by_id[5]["average_rating"] is None and by_id[5]["rating_count"] == 0
    assert by_id[6]["year"] is None and by_id[6]["genres"] == []
    assert (
        by_id[1]["poster"]["initials"] == "AR" and by_id[6]["poster"]["initials"] == "Z"
    )
    assert by_id[1]["poster"] == client.get("/movies").json()["items"][0]["poster"]
    assert 0 <= by_id[1]["poster"]["hue"] < 360


def test_sorting(client: TestClient) -> None:
    def order(query: str) -> list[int]:
        return ids(client.get(f"/movies?{query}"))

    assert order("") == [1, 2, 4, 5, 3, 6]  # title, A to Z
    assert order("sort=title&order=desc") == [6, 3, 5, 4, 2, 1]
    assert order("sort=year") == [5, 4, 3, 2, 1, 6]  # newest first, no year last
    assert order("sort=year&order=asc") == [1, 2, 3, 4, 5, 6]
    # rating: movies with >= 5 ratings first (4.6, 3.0, 2.0), then the rest by count
    assert order("sort=rating") == [1, 2, 3, 4, 6, 5]
    assert order("sort=rating&order=asc") == [3, 2, 1, 4, 6, 5]
    assert order("sort=popularity") == [2, 1, 3, 4, 6, 5]  # 6, 5, 5, 2, 1, 0 ratings
    assert order("sort=popularity&order=asc") == [5, 6, 4, 1, 3, 2]
    assert client.get("/movies?sort=nonsense").status_code == 422


def test_filters_and_search(client: TestClient) -> None:
    def found(query: str) -> list[int]:
        return ids(client.get(f"/movies?{query}"))

    assert found("genre=Comedy") == [2, 5, 3]
    assert found("genre=comedy") == found("genre=COMEDY") == [2, 5, 3]
    assert client.get("/movies?genre=Nonsense").status_code == 422
    assert found("genre=Action&year_min=1995") == [2]
    assert found("year_min=1995&year_max=2005") == [2, 4, 3]
    assert found("year_min=1800") == [1, 2, 4, 5, 3]  # the movie with no year drops out
    assert found("min_rating=3") == [1, 2]
    assert found("min_rating=4.5") == [1]
    # movie 4 averages 5.0 but has only 2 ratings: below the 5-rating minimum
    assert found("min_rating=5") == []
    assert found("q=alpha") == found("q=ALPHA") == [1]
    assert found("q=_") == [3]  # a literal underscore, not "any character"
    assert found("q=%25") == [4]  # a literal percent sign (URL-encoded)
    assert found("q=%5C") == []  # a backslash matches nothing and is not an error
    assert found("genre=Drama&q=eps") == [5]
    assert found("q=zzz") == []


def test_pagination_and_limits(client: TestClient) -> None:
    pages = [client.get(f"/movies?page_size=2&page={n}").json() for n in (1, 2, 3)]
    assert [[m["id"] for m in p["items"]] for p in pages] == [[1, 2], [4, 5], [3, 6]]
    assert all(p["total"] == 6 and p["page_size"] == 2 for p in pages)
    beyond = client.get("/movies?page_size=2&page=4").json()
    assert beyond["items"] == [] and beyond["total"] == 6
    assert client.get("/movies?page_size=50").status_code == 200
    for bad in (
        "page_size=51",
        "page_size=0",
        "page=0",
        "page=-1",
        "min_rating=0",
        "min_rating=5.5",
        "year_min=1700",
        "q=" + "x" * 101,
    ):
        assert client.get(f"/movies?{bad}").status_code == 422, bad


def test_movie_detail(client: TestClient) -> None:
    anonymous = client.get("/movies/1")
    body = anonymous.json()
    assert anonymous.status_code == 200 and body["me"] is None
    assert body["tags"] == ["classic", "retro"] and body["title"] == "Alpha Run (1990)"
    assert client.get("/movies/999").status_code == 404
    assert (
        client.get("/movies/1", headers={"Authorization": "Bearer junk"}).status_code
        == 401
    )
    headers = signup(client)
    client.put("/movies/1/rating", json={"rating": 2}, headers=headers)
    mine = client.get("/movies/1", headers=headers).json()
    assert mine["me"]["rating"] == 2.0
    assert mine["rating_count"] == 6  # the new rating is counted
    assert mine["average_rating"] == round((23 + 2) / 6, 2)


# ---- interactions ------------------------------------------------------------


def test_rating_rules_and_updates(client: TestClient, engine: Engine) -> None:
    headers = signup(client)
    for good in (0.5, 5, 3.5):
        assert (
            client.put(
                "/movies/1/rating", json={"rating": good}, headers=headers
            ).status_code
            == 200
        )
    for bad in (0, 5.5, 3.3, -1, 4.25, "abc", None):
        assert (
            client.put(
                "/movies/1/rating", json={"rating": bad}, headers=headers
            ).status_code
            == 422
        )
    assert (
        client.put(
            "/movies/999/rating", json={"rating": 3}, headers=headers
        ).status_code
        == 404
    )
    assert client.put("/movies/1/rating", json={"rating": 3}).status_code == 401
    client.put("/movies/5/rating", json={"rating": 4}, headers=headers)
    user_id = client.get("/me", headers=headers).json()["id"]
    first = scalar(
        engine,
        "SELECT rated_at FROM ratings WHERE user_id=:u AND movie_id=5",
        u=user_id,
    )
    client.put("/movies/5/rating", json={"rating": 2.5}, headers=headers)  # replace
    rows = scalar(
        engine,
        "SELECT count(*) FROM ratings WHERE user_id=:u AND movie_id=5",
        u=user_id,
    )
    value = scalar(
        engine, "SELECT rating FROM ratings WHERE user_id=:u AND movie_id=5", u=user_id
    )
    later = scalar(
        engine,
        "SELECT rated_at FROM ratings WHERE user_id=:u AND movie_id=5",
        u=user_id,
    )
    assert rows == 1 and float(value) == 2.5  # type: ignore[arg-type]
    assert later >= first  # type: ignore[operator]
    assert client.get("/movies/5", headers=headers).json()["rating_count"] == 1
    removed = client.delete("/movies/5/rating", headers=headers)
    assert removed.status_code == 200 and removed.json()["rating"] is None
    assert (
        client.delete("/movies/5/rating", headers=headers).status_code == 200
    )  # again
    assert client.get("/movies/5").json()["rating_count"] == 0


def test_flags_are_idempotent_and_independent(
    client: TestClient, engine: Engine
) -> None:
    headers = signup(client)
    user_id = client.get("/me", headers=headers).json()["id"]

    def count(kind: str) -> object:
        return scalar(
            engine,
            "SELECT count(*) FROM interactions"
            " WHERE user_id=:u AND movie_id=1 AND kind=:k",
            u=user_id,
            k=kind,
        )

    first = client.put("/movies/1/watchlist", headers=headers)
    stamp = scalar(
        engine,
        "SELECT created_at FROM interactions WHERE user_id=:u AND kind='watchlist'",
        u=user_id,
    )
    again = client.put("/movies/1/watchlist", headers=headers)
    assert first.json() == again.json() and count("watchlist") == 1
    assert stamp == scalar(
        engine,
        "SELECT created_at FROM interactions WHERE user_id=:u AND kind='watchlist'",
        u=user_id,
    )
    state = client.put("/movies/1/watched", headers=headers).json()
    assert state["watchlist"] is True and state["watched"] is True  # independent
    client.put("/movies/1/rating", json={"rating": 4}, headers=headers)
    after = client.get("/movies/1", headers=headers).json()["me"]
    assert after["rating"] == 4.0 and after["watchlist"] and after["watched"]
    assert count("viewed") == 0 and not after["liked"]  # rating alone sets no flag
    assert (
        client.delete("/movies/1/watchlist", headers=headers).json()["watchlist"]
        is False
    )
    assert client.delete("/movies/1/watchlist", headers=headers).status_code == 200
    assert client.get("/movies/1", headers=headers).json()["me"]["watched"] is True
    assert client.put("/movies/999/like", headers=headers).status_code == 404
    assert client.put("/movies/1/like").status_code == 401


def test_like_and_dislike_replace_each_other(
    client: TestClient, engine: Engine
) -> None:
    headers = signup(client)
    user_id = client.get("/me", headers=headers).json()["id"]
    liked = client.put("/movies/2/like", headers=headers).json()
    assert liked["liked"] and not liked["disliked"]
    flipped = client.put("/movies/2/dislike", headers=headers).json()
    assert flipped["disliked"] and not flipped["liked"]
    rows = scalar(
        engine,
        "SELECT count(*) FROM interactions WHERE user_id=:u AND movie_id=2",
        u=user_id,
    )
    assert rows == 1
    back = client.put("/movies/2/like", headers=headers).json()
    assert back["liked"] and not back["disliked"]
    cleared = client.delete("/movies/2/like", headers=headers).json()
    assert not cleared["liked"] and not cleared["disliked"]


def test_viewing_records_one_row_and_refreshes_its_time(
    client: TestClient, engine: Engine
) -> None:
    headers = signup(client)
    user_id = client.get("/me", headers=headers).json()["id"]
    first = client.post("/movies/3/view", headers=headers).json()["viewed_at"]
    second = client.post("/movies/3/view", headers=headers).json()["viewed_at"]
    assert first is not None and second >= first
    rows = scalar(
        engine,
        "SELECT count(*) FROM interactions WHERE user_id=:u AND kind='viewed'",
        u=user_id,
    )
    assert rows == 1
    assert client.post("/movies/3/view").status_code == 401


def test_history_and_watchlist_are_newest_first_and_paged(client: TestClient) -> None:
    headers = signup(client)
    client.put("/movies/1/rating", json={"rating": 4}, headers=headers)
    client.put("/movies/2/like", headers=headers)
    client.put("/movies/3/watchlist", headers=headers)
    history = client.get("/me/history", headers=headers).json()
    assert [i["movie"]["id"] for i in history["items"]] == [3, 2, 1]
    assert history["total"] == 3
    assert history["items"][2]["state"]["rating"] == 4.0
    paged = client.get("/me/history?page_size=2&page=2", headers=headers).json()
    assert [i["movie"]["id"] for i in paged["items"]] == [1] and paged["total"] == 3
    client.put("/movies/1/watchlist", headers=headers)
    watch = client.get("/me/watchlist", headers=headers).json()
    assert [m["id"] for m in watch["items"]] == [1, 3] and watch["total"] == 2
    assert client.get("/me/history?page_size=51", headers=headers).status_code == 422
