"""Chunk 4C tests on the six-movie fixture of ``test_api`` with a stand-in recommender:
dashboard panels, analytics aggregates, event meanings and CORS. Every expected number
is worked out by hand in the comments. Run against the separate TEST database.

These establish mechanics (the right counts, filters and headers for a small invented
catalogue). They say nothing about recommendation quality, speed or load.
"""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import Engine, text

from pmrs.api.app import create_app
from pmrs.api.settings import ApiSettings
from pmrs.db.seed import seed
from test_api import (  # noqa: F401  (engine is a fixture)
    SECRET,
    StubRecommender,
    catalogue_data,
    engine,
    scalar,
    signup,
)

ORIGIN = "http://localhost:5173"


@pytest.fixture()
def client(engine: Engine) -> TestClient:  # noqa: F811
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


def events(engine: Engine, kind: str, user: str = "") -> int:  # noqa: F811
    return int(
        str(
            scalar(
                engine,
                "SELECT count(*) FROM recommendation_events WHERE kind = :k",
                k=kind,
            )
        )
    )


def ann_activity(client: TestClient) -> dict[str, str]:
    """Ann: genres Comedy, Drama; rates m1=4; likes m2; watchlists m3; watched m4;
    views m2."""
    h = signup(client)
    assert (
        client.put("/me/genres", json={"genres": ["drama", "Comedy"]}, headers=h)
    ).status_code == 200
    assert client.put("/movies/1/rating", json={"rating": 4}, headers=h).is_success
    assert client.put("/movies/2/like", headers=h).is_success
    assert client.put("/movies/3/watchlist", headers=h).is_success
    assert client.put("/movies/4/watched", headers=h).is_success
    assert client.post("/movies/2/view", headers=h).is_success
    return h


# ---- dashboard ---------------------------------------------------------------


def test_dashboard_has_all_seven_panels_with_hand_checked_contents(
    client: TestClient,
    engine: Engine,  # noqa: F811
) -> None:
    h = ann_activity(client)
    body = client.get("/me/dashboard", headers=h).json()
    assert set(body) == {
        "recommended",
        "trending",
        "popular",
        "recent_releases",
        "genres",
        "watchlist",
        "activity",
    }
    assert body["genres"] == ["Comedy", "Drama"]
    # ratings per movie now: m1 5+1=6, m2 6, m3 5, m4 2, m6 1, m5 0; ties by id
    assert [m["id"] for m in body["popular"]] == [1, 2, 3, 4, 6, 5]
    # newest release years first; the movie with no year last
    assert [m["id"] for m in body["recent_releases"]] == [5, 4, 3, 2, 1, 6]
    assert [m["id"] for m in body["watchlist"]["items"]] == [3]
    assert body["watchlist"]["total"] == 1
    # newest activity first: m2 (view), m4, m3, m1
    assert [i["movie"]["id"] for i in body["activity"]["items"]] == [2, 4, 3, 1]
    # app activity: m1 1 (rating), m2 2 (like+view), m3 1, m4 1
    trending = body["trending"]
    assert trending["source"] == "app_activity"
    assert [(i["movie"]["id"], i["interactions"]) for i in trending["items"]] == [
        (2, 2),
        (1, 1),
        (3, 1),
        (4, 1),
    ]
    # recommended: stub order 2,1,3,4,6,5 minus rated (1) minus watched (4)
    rec = body["recommended"]
    assert rec["branch"] == "few_ratings" and rec["rating_count"] == 1
    assert [i["movie"]["id"] for i in rec["items"]] == [2, 3, 6, 5]


def test_dashboard_logs_its_recommendations_exactly_once(
    client: TestClient,
    engine: Engine,  # noqa: F811
) -> None:
    h = ann_activity(client)
    assert events(engine, "shown") == 0  # actions alone serve nothing
    body = client.get("/me/dashboard", headers=h).json()
    assert body["recommended"]["served_events_logged"] == 4
    assert events(engine, "shown") == 4  # 4 items served, 4 events, no duplicates
    client.get("/me/dashboard", headers=h)
    assert events(engine, "shown") == 8  # each further call is a further serving


def test_trending_falls_back_to_the_dataset_and_says_so(client: TestClient) -> None:
    h = signup(client)  # no app activity at all
    trending = client.get("/me/dashboard", headers=h).json()["trending"]
    assert trending["source"] == "dataset_latest_period"
    assert trending["window_days"] == 365
    assert "not today" in trending["note"]
    # all 19 historical ratings fall in the last 365 days of the data:
    # m2 6, m1 5, m3 5, m4 2, m6 1 (ties by id)
    assert [(i["movie"]["id"], i["interactions"]) for i in trending["items"]] == [
        (2, 6),
        (1, 5),
        (3, 5),
        (4, 2),
        (6, 1),
    ]


def test_dashboard_is_private_and_per_user(client: TestClient) -> None:
    assert client.get("/me/dashboard").status_code == 401
    ann = ann_activity(client)
    bob = signup(client, email="bob@example.org")
    mine = client.get("/me/dashboard", headers=ann).json()
    his = client.get("/me/dashboard", headers=bob).json()
    assert his["genres"] == [] and his["watchlist"]["total"] == 0
    assert his["activity"]["total"] == 0 and his["recommended"]["rating_count"] == 0
    assert mine["activity"]["total"] == 4


# ---- analytics ---------------------------------------------------------------


def test_analytics_routes_need_login(client: TestClient) -> None:
    for path in (
        "/analytics/summary",
        "/analytics/popular",
        "/analytics/ratings-distribution",
        "/analytics/engagement",
    ):
        assert client.get(path).status_code == 401, path
        bad = client.get(path, headers={"Authorization": "Bearer nonsense"})
        assert bad.status_code == 401, path
    h = signup(client)
    for path in ("/analytics/summary", "/analytics/popular"):
        assert client.get(path, headers=h).status_code == 200


def test_summary_counts_and_keeps_movielens_and_app_apart(client: TestClient) -> None:
    h = signup(client)
    first = client.get("/analytics/summary", headers=h).json()
    # 6 movies; users 1-6 are historical (the ratings use user ids 1..6) plus Ann
    assert first["movies"] == 6
    assert first["users"] == {"total": 7, "movielens": 6, "app": 1}
    assert first["ratings"] == {"total": 19, "movielens": 19, "app": 0}
    assert first["interactions"] == dict.fromkeys(
        ("like", "dislike", "watchlist", "watched", "viewed"), 0
    )
    assert first["recommendation_events"] == {"shown": 0, "acted": 0}
    ann_activity_for(client, h)
    second = client.get("/analytics/summary", headers=h).json()
    assert second["ratings"] == {"total": 20, "movielens": 19, "app": 1}
    assert second["interactions"] == {
        "like": 1,
        "dislike": 0,
        "watchlist": 1,
        "watched": 1,
        "viewed": 1,
    }
    flat = str(second)
    assert "ann@example.org" not in flat  # aggregates only


def ann_activity_for(client: TestClient, h: dict[str, str]) -> None:
    assert client.put("/movies/1/rating", json={"rating": 4}, headers=h).is_success
    assert client.put("/movies/2/like", headers=h).is_success
    assert client.put("/movies/3/watchlist", headers=h).is_success
    assert client.put("/movies/4/watched", headers=h).is_success
    assert client.post("/movies/2/view", headers=h).is_success


def test_ratings_distribution_matches_the_hand_count(client: TestClient) -> None:
    h = signup(client)
    body = client.get("/analytics/ratings-distribution", headers=h).json()
    got = {b["rating"]: b for b in body["buckets"]}
    assert sorted(got) == [x / 2 for x in range(1, 11)]  # every half star, zeros too
    # historical: 2.0 x5 (m3), 3.0 x6 (m2), 4.0 x2 (m1, m6), 4.5 x2, 5.0 x4 (m1 2, m4 2)
    assert {r: b["movielens"] for r, b in got.items() if b["movielens"]} == {
        2.0: 5,
        3.0: 6,
        4.0: 2,
        4.5: 2,
        5.0: 4,
    }
    assert sum(b["total"] for b in got.values()) == 19
    assert all(b["app"] == 0 for b in got.values())
    client.put("/movies/1/rating", json={"rating": 4}, headers=h)
    again = {
        b["rating"]: b
        for b in client.get("/analytics/ratings-distribution", headers=h).json()[
            "buckets"
        ]
    }
    assert (again[4.0]["total"], again[4.0]["movielens"], again[4.0]["app"]) == (
        3,
        2,
        1,
    )


def test_popular_is_ordered_and_limited(client: TestClient) -> None:
    h = signup(client)
    body = client.get("/analytics/popular?limit=3", headers=h).json()
    assert [m["id"] for m in body] == [2, 1, 3]  # 6, 5, 5 ratings (tie by id)
    assert client.get("/analytics/popular?limit=51", headers=h).status_code == 422


def test_empty_engagement_returns_honest_zeros(client: TestClient) -> None:
    h = signup(client)
    body = client.get("/analytics/engagement", headers=h).json()
    assert (body["served"], body["acted"], body["users"]) == (0, 0, 0)
    assert body["by_strategy"] == []
    assert "not show that recommendations caused" in body["note"]


# ---- event meanings ----------------------------------------------------------


def acted(engine: Engine) -> list[tuple[int, str]]:  # noqa: F811
    with engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT movie_id, strategy FROM recommendation_events"
                " WHERE kind = 'acted' ORDER BY id"
            )
        )
        return [(r[0], r[1]) for r in rows]


def test_acted_is_recorded_only_for_served_movies_and_only_once(
    client: TestClient,
    engine: Engine,  # noqa: F811
) -> None:
    h = signup(client)
    # acting BEFORE anything was served records nothing
    assert client.put("/movies/5/like", headers=h).is_success
    assert acted(engine) == []
    # serve hybrid k=3: stub order 2, 1, 3 (nothing rated yet)
    served = client.get("/me/recommendations?strategy=hybrid&k=3", headers=h).json()
    assert [i["movie"]["id"] for i in served["items"]] == [2, 1, 3]
    assert events(engine, "shown") == 3
    client.put("/movies/1/rating", json={"rating": 4}, headers=h)
    assert acted(engine) == [(1, "hybrid")]
    client.put("/movies/1/rating", json={"rating": 5}, headers=h)  # repeat: no 2nd
    client.put("/movies/1/like", headers=h)
    assert acted(engine) == [(1, "hybrid")]
    client.put("/movies/6/like", headers=h)  # never served to Ann
    client.delete("/movies/1/rating", headers=h)  # a removal is not an action
    client.delete("/movies/1/like", headers=h)
    assert acted(engine) == [(1, "hybrid")]
    # serve again (popularity, k=2: movies 2 and 1); acting after that is a new,
    # separate acted event, attributed to the latest strategy that served the movie
    client.get("/me/recommendations?strategy=popularity&k=2", headers=h)
    assert client.post("/movies/2/view", headers=h).is_success  # a view is not acted
    assert acted(engine) == [(1, "hybrid")]
    assert client.put("/movies/1/like", headers=h).is_success
    assert client.put("/movies/1/watched", headers=h).is_success  # same serving: once
    assert acted(engine) == [(1, "hybrid"), (1, "popularity")]


def test_engagement_counts_by_strategy_match_the_hand_count(
    client: TestClient,
    engine: Engine,  # noqa: F811
) -> None:
    h = signup(client)
    client.get("/me/recommendations?strategy=hybrid&k=3", headers=h)  # 2, 1, 3
    client.get("/me/recommendations?strategy=popularity&k=2", headers=h)  # 2, 1
    client.put("/movies/3/watchlist", headers=h)  # served only by hybrid
    client.put("/movies/2/like", headers=h)  # latest serving of m2 was popularity
    body = client.get("/analytics/engagement", headers=h).json()
    assert (body["served"], body["acted"], body["users"]) == (5, 2, 1)
    by = {s["strategy"]: s for s in body["by_strategy"]}
    assert by["hybrid"]["served"] == 3 and by["hybrid"]["acted"] == 1
    assert by["popularity"]["served"] == 2 and by["popularity"]["acted"] == 1
    assert by["hybrid"]["acted_per_served"] == 0.3333
    assert by["popularity"]["acted_per_served"] == 0.5


def test_events_are_removed_with_the_account(
    client: TestClient,
    engine: Engine,  # noqa: F811
) -> None:
    h = signup(client)
    client.get("/me/recommendations?k=3", headers=h)
    client.put("/movies/2/like", headers=h)
    assert events(engine, "shown") == 3 and events(engine, "acted") == 1
    assert client.delete("/me", headers=h).status_code == 204
    assert events(engine, "shown") == 0 and events(engine, "acted") == 0


# ---- CORS --------------------------------------------------------------------


def test_cors_allows_only_the_configured_origin(client: TestClient) -> None:
    ok = client.get("/movies", headers={"Origin": ORIGIN})
    assert ok.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-credentials" not in ok.headers
    other = client.get("/movies", headers={"Origin": "http://evil.example"})
    assert "access-control-allow-origin" not in other.headers
    assert other.headers.get("access-control-allow-origin") != "*"


def test_cors_preflight(client: TestClient) -> None:
    ask = {
        "Access-Control-Request-Method": "PUT",
        "Access-Control-Request-Headers": "authorization,content-type",
    }
    ok = client.options("/movies/1/rating", headers={"Origin": ORIGIN, **ask})
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == ORIGIN
    assert "PUT" in ok.headers["access-control-allow-methods"]
    bad = client.options(
        "/movies/1/rating", headers={"Origin": "http://evil.example", **ask}
    )
    assert bad.status_code == 400
    assert "access-control-allow-origin" not in bad.headers
    patch = client.options(
        "/movies/1/rating",
        headers={
            "Origin": ORIGIN,
            "Access-Control-Request-Method": "PATCH",
        },
    )
    assert patch.status_code == 400  # a method that is not allowed


@pytest.mark.parametrize(
    "value", ["*", "http://localhost:5173/app", "localhost:5173", "ftp://x", ""]
)
def test_frontend_origin_setting_rejects_wildcards_and_paths(value: str) -> None:
    with pytest.raises(ValidationError):
        ApiSettings(jwt_secret=SECRET, frontend_origin=value)


def test_a_configured_origin_replaces_the_default(engine: Engine) -> None:  # noqa: F811
    app = create_app(
        ApiSettings(jwt_secret=SECRET, frontend_origin="https://app.example.org/"),
        engine,
        StubRecommender(),
    )
    c = TestClient(app)
    same = c.get("/movies", headers={"Origin": "https://app.example.org"})
    assert same.headers["access-control-allow-origin"] == "https://app.example.org"
    old = c.get("/movies", headers={"Origin": ORIGIN})
    assert "access-control-allow-origin" not in old.headers
