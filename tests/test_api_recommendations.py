"""Chunk 4C tests on the REAL frozen serving artifact and the REAL MovieLens data in the
separate TEST database: the recommendation branches, filtering, user isolation, event
meaning, the exposed strategy list and artifact verification.

What these show: the API wires the profile to the shared Recommender correctly and
follows the frozen routing. What they do NOT show: that any list is good. The serving
artifact has no quality metric, and the Step 16 results describe another model.
Expected values are properties (branch, exclusion, equality with the popularity list),
not memorised movie lists.
"""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text

from pmrs.api.app import create_app
from pmrs.api.settings import ApiSettings
from pmrs.data import load_movielens
from pmrs.db.seed import seed
from pmrs.evaluation.serving import NAMES, load_verified
from pmrs.recommender.artifact import ArtifactError
from pmrs.recommender.recommender import Recommender

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "data/processed/artifacts" / NAMES["serving"]
RAW = ROOT / "data/raw/ml-latest-small"
SECRET = "test-only-secret-" + "k" * 40
PASSWORD = "correct horse battery staple"
# well-known movies (all in ml-latest-small)
ELEVEN = [1, 50, 110, 260, 318, 356, 480, 527, 589, 593, 1196]
TOP_POPULAR = 356  # Forrest Gump: the most-rated movie in the data

pytestmark = pytest.mark.skipif(
    not ARTIFACT.is_dir() or not RAW.is_dir(),
    reason="needs the serving artifact and the MovieLens data (NOT RUN without them)",
)


@pytest.fixture(scope="session")
def recommender() -> Recommender:
    return load_verified(ARTIFACT)


@pytest.fixture(scope="module")
def real_engine(test_url: str) -> Iterator[Engine]:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    eng = create_engine(test_url)
    seed(eng, load_movielens(RAW))  # the real data, in the TEST database only
    yield eng
    eng.dispose()


@pytest.fixture()
def client(real_engine: Engine, recommender: Recommender) -> TestClient:
    with real_engine.begin() as connection:  # historical users stay; app users go
        connection.execute(text("DELETE FROM users WHERE NOT is_historical"))
    app = create_app(ApiSettings(jwt_secret=SECRET), real_engine, recommender)
    return TestClient(app)


def signup(client: TestClient, email: str = "ann@example.org") -> dict[str, str]:
    body = {"email": email, "password": PASSWORD, "display_name": "Ann"}
    assert client.post("/auth/register", json=body).status_code == 201
    token = client.post("/auth/login", json=body).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def rate(client: TestClient, h: dict[str, str], movie_ids: list[int], value: float = 4):
    for movie_id in movie_ids:
        r = client.put(f"/movies/{movie_id}/rating", json={"rating": value}, headers=h)
        assert r.status_code == 200, r.text


def recs(
    client: TestClient, h: dict[str, str], strategy: str = "hybrid", k: int = 10
) -> dict:  # type: ignore[type-arg]
    r = client.get(f"/me/recommendations?strategy={strategy}&k={k}", headers=h)
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def movie_ids(body: dict) -> list[int]:  # type: ignore[type-arg]
    return [i["movie"]["id"] for i in body["items"]]


def count_events(engine: Engine, kind: str) -> int:
    with engine.connect() as c:
        return int(
            c.execute(
                text("SELECT count(*) FROM recommendation_events WHERE kind = :k"),
                {"k": kind},
            ).scalar_one()
        )


# ---- branches ----------------------------------------------------------------


def test_new_user_without_genres_gets_popularity(client: TestClient) -> None:
    h = signup(client)
    body = recs(client, h)
    assert (body["strategy"], body["branch"], body["rating_count"]) == (
        "hybrid",
        "no_ratings",
        0,
    )
    assert movie_ids(body) == movie_ids(recs(client, h, "popularity"))
    assert movie_ids(body)[0] == TOP_POPULAR and len(body["items"]) == 10
    assert "not personalised" in body["branch_reason"]
    assert "no separate quality metric" in body["model_notice"]


def test_new_user_with_genres_gets_matching_genres(client: TestClient) -> None:
    h = signup(client)
    assert client.put(
        "/me/genres", json={"genres": ["documentary"]}, headers=h
    ).is_success
    body = recs(client, h)
    assert body["branch"] == "no_ratings"
    top = body["items"][:3]
    assert all("Documentary" in i["movie"]["genres"] for i in top)
    assert movie_ids(body) != movie_ids(recs(client, h, "popularity"))


def test_one_to_ten_ratings_is_popularity_and_eleven_is_the_hybrid(
    client: TestClient,
) -> None:
    h = signup(client)
    rate(client, h, ELEVEN[:3])
    few = recs(client, h)
    assert (few["branch"], few["rating_count"]) == ("few_ratings", 3)
    pop = recs(client, h, "popularity")
    assert movie_ids(few) == movie_ids(pop)  # the frozen rung is pure popularity
    assert not set(movie_ids(few)) & set(ELEVEN[:3])
    rate(client, h, ELEVEN[3:10])  # now exactly 10
    assert recs(client, h)["branch"] == "few_ratings"
    rate(client, h, ELEVEN[10:])  # 11
    many = recs(client, h)
    assert (many["branch"], many["rating_count"]) == ("many_ratings", 11)
    assert movie_ids(many) != movie_ids(recs(client, h, "popularity"))
    assert not set(movie_ids(many)) & set(ELEVEN)
    assert all(i["explanation"] for i in many["items"])
    assert "full hybrid" in many["branch_reason"]


def test_adding_a_rating_changes_the_list(client: TestClient) -> None:
    h = signup(client)
    rate(client, h, ELEVEN)
    before = recs(client, h)
    top = movie_ids(before)[0]
    rate(client, h, [top], 5)
    after = recs(client, h)
    assert top in movie_ids(before) and top not in movie_ids(after)
    assert movie_ids(after) != movie_ids(before)
    assert after["rating_count"] == 12


def test_a_smaller_k_is_a_prefix_of_a_larger_one(client: TestClient) -> None:
    h = signup(client)
    rate(client, h, ELEVEN)
    assert movie_ids(recs(client, h, k=5)) == movie_ids(recs(client, h, k=10))[:5]


# ---- filtering and what feeds the model ---------------------------------------


def test_watched_and_disliked_are_hidden_but_watchlist_and_liked_are_not(
    client: TestClient,
) -> None:
    h = signup(client)
    base = movie_ids(recs(client, h))
    watched, disliked, listed, liked = base[0], base[1], base[2], base[3]
    assert client.put(f"/movies/{watched}/watched", headers=h).is_success
    assert client.put(f"/movies/{disliked}/dislike", headers=h).is_success
    assert client.put(f"/movies/{listed}/watchlist", headers=h).is_success
    assert client.put(f"/movies/{liked}/like", headers=h).is_success
    now = recs(client, h)
    assert watched not in movie_ids(now) and disliked not in movie_ids(now)
    assert len(now["items"]) == 10  # the list is topped up, not shortened
    assert movie_ids(now)[:2] == [listed, liked]  # nothing else moved
    assert now["items"][0]["state"]["watchlist"] is True
    assert now["items"][1]["state"]["liked"] is True


def test_likes_dislikes_watched_and_watchlist_do_not_change_the_model_input(
    client: TestClient,
) -> None:
    h = signup(client)
    rate(client, h, ELEVEN)
    before = recs(client, h)
    # four existing movies outside the list, so hiding cannot be the explanation
    shown = set(movie_ids(before)) | set(ELEVEN)
    others = [m for m in (2, 3, 5, 6, 7, 10, 11, 17, 21, 32) if m not in shown][:4]
    assert len(others) == 4
    client.put(f"/movies/{others[0]}/like", headers=h)
    client.put(f"/movies/{others[1]}/dislike", headers=h)
    client.put(f"/movies/{others[2]}/watchlist", headers=h)
    client.put(f"/movies/{others[3]}/watched", headers=h)
    after = recs(client, h)
    assert movie_ids(after) == movie_ids(before)
    assert [i["score"] for i in after["items"]] == [i["score"] for i in before["items"]]


# ---- isolation ---------------------------------------------------------------


def test_each_user_gets_a_list_from_their_own_data_only(client: TestClient) -> None:
    ann, bob = signup(client), signup(client, "bob@example.org")
    rate(client, ann, ELEVEN)
    rate(client, bob, [2571, 2959, 4993, 5952, 7153, 1, 3, 6, 7, 10, 11], 2)
    a_before, b_before = recs(client, ann), recs(client, bob)
    assert movie_ids(a_before) != movie_ids(b_before)
    # Bob rating more changes nothing for Ann
    rate(client, bob, [32, 47, 150], 5)
    assert movie_ids(recs(client, ann)) == movie_ids(a_before)
    # Ann's flags never show in Bob's list
    client.put(f"/movies/{TOP_POPULAR}/like", headers=ann)
    carol = signup(client, "carol@example.org")
    first = recs(client, carol)["items"][0]
    assert first["movie"]["id"] == TOP_POPULAR and first["state"]["liked"] is False


def test_recommendations_need_login_and_take_no_user_id(client: TestClient) -> None:
    assert client.get("/me/recommendations").status_code == 401
    bad = client.get("/me/recommendations", headers={"Authorization": "Bearer x"})
    assert bad.status_code == 401
    h = signup(client)
    other = client.get("/me/recommendations?user_id=1", headers=h)
    assert other.status_code == 200  # unknown query parameters are ignored...
    assert other.json()["rating_count"] == 0  # ...never used to pick another user
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/me/recommendations", "/me/dashboard"):
        names = {p["name"] for p in paths[path]["get"].get("parameters", [])}
        assert not names & {"user_id", "userId", "id"}


# ---- strategies --------------------------------------------------------------


def test_only_the_five_documented_strategies_are_served(client: TestClient) -> None:
    h = signup(client)
    for name in ("random", "bayesian_average", "content_no_tags", "nonsense"):
        r = client.get(f"/me/recommendations?strategy={name}", headers=h)
        assert r.status_code == 422, name
    spec = client.get("/openapi.json").json()
    params = spec["paths"]["/me/recommendations"]["get"]["parameters"]
    strategy = next(p for p in params if p["name"] == "strategy")
    assert set(strategy["schema"]["enum"]) == {
        "hybrid",
        "popularity",
        "content",
        "item_knn",
        "svd",
    }
    assert "offline-evaluation" in strategy["description"]
    assert "no separate quality metric" in spec["info"]["description"]


def test_k_is_validated(client: TestClient) -> None:
    h = signup(client)
    for k in (0, 51, -1):
        assert client.get(f"/me/recommendations?k={k}", headers=h).status_code == 422


def test_single_methods_with_ratings_and_without(client: TestClient) -> None:
    h = signup(client)
    for name in ("content", "item_knn", "svd"):
        empty = recs(client, h, name)
        assert empty["items"] == [] and "needs at least one rating" in empty["notes"][0]
    rate(client, h, ELEVEN)
    for name in ("popularity", "content", "item_knn", "svd"):
        body = recs(client, h, name)
        assert body["strategy"] == name and body["branch"] is None
        assert len(body["items"]) == 10, name
        assert not set(movie_ids(body)) & set(ELEVEN), name
        assert all(i["explanation"] for i in body["items"]), name


# ---- events ------------------------------------------------------------------


def test_serving_logs_one_shown_event_per_item_and_acting_logs_one_acted(
    client: TestClient, real_engine: Engine
) -> None:
    h = signup(client)
    before = count_events(real_engine, "shown")
    body = recs(client, h)
    assert body["served_events_logged"] == 10
    assert count_events(real_engine, "shown") - before == 10
    first = movie_ids(body)[0]
    acted0 = count_events(real_engine, "acted")
    client.put(f"/movies/{first}/rating", json={"rating": 3}, headers=h)
    assert count_events(real_engine, "acted") - acted0 == 1
    client.put(f"/movies/{first}/rating", json={"rating": 4}, headers=h)
    assert count_events(real_engine, "acted") - acted0 == 1
    client.put("/movies/2/like", headers=h)  # not in the served list
    assert count_events(real_engine, "acted") - acted0 == 1


def test_viewing_a_served_movie_records_viewed_but_no_acted_event(
    client: TestClient, real_engine: Engine
) -> None:
    h = signup(client)
    served = movie_ids(recs(client, h))[0]
    acted0 = count_events(real_engine, "acted")
    state = client.post(f"/movies/{served}/view", headers=h).json()
    assert state["viewed_at"] is not None  # the viewed interaction was stored
    assert count_events(real_engine, "acted") == acted0  # and nothing was "acted"
    client.post(f"/movies/{served}/view", headers=h)
    assert count_events(real_engine, "acted") == acted0
    # an explicit action afterwards still records exactly one acted event
    client.put(f"/movies/{served}/watchlist", headers=h)
    assert count_events(real_engine, "acted") - acted0 == 1


# ---- the artifact ------------------------------------------------------------


def settings_for(directory: Path) -> ApiSettings:
    return ApiSettings(jwt_secret=SECRET, serving_artifact_dir=directory)


def test_startup_verifies_the_artifact_before_loading_it(tmp_path: Path) -> None:
    engine = create_engine("sqlite://")  # never used: startup must fail first
    copy = tmp_path / "copy"
    shutil.copytree(ARTIFACT, copy)
    app = create_app(settings_for(copy), engine)  # an intact copy loads
    assert isinstance(app.state.recommender, Recommender)

    model = next(copy.glob("*.joblib"))
    original = model.read_bytes()
    model.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))  # flip one bit
    with pytest.raises(ArtifactError, match="does not match"):
        create_app(settings_for(copy), engine)
    model.write_bytes(original)
    (copy / "extra.txt").write_text("not in the manifest")
    with pytest.raises(ArtifactError, match="differ from the manifest"):
        create_app(settings_for(copy), engine)
    with pytest.raises(ArtifactError):
        create_app(settings_for(tmp_path / "missing"), engine)


def test_the_real_artifact_is_untouched_by_these_tests() -> None:
    load_verified(ARTIFACT)  # still matches its own SHA-256 manifest
