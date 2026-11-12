"""The FastAPI application.

    uv run uvicorn pmrs.api.app:create_app --factory

Local use only: do not expose it publicly until HTTPS and rate limiting exist (owner
decision, D-037). Interactive docs are at /docs.

Startup verifies and loads the frozen serving artifact (SHA-256 manifest first) and
refuses to start if that fails. CORS allows exactly one origin, ``FRONTEND_ORIGIN``.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, create_engine

from pmrs.api import (
    actions,
    analytics,
    auth,
    dashboard,
    me,
    movies,
    recommendations,
)
from pmrs.api.recommendations import Recommending
from pmrs.api.settings import ApiSettings
from pmrs.db.settings import load_settings
from pmrs.evaluation.serving import load_verified


async def _validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
    """422 without echoing the submitted values: a rejected password must not come back
    in the response (FastAPI's default includes it)."""
    detail = [
        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
        for e in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


DESCRIPTION = """Local development API (no HTTPS, no rate limiting: do not expose it).

**Recommendation strategies** (`GET /me/recommendations?strategy=`): `hybrid` (default),
`popularity`, `content`, `item_knn`, `svd`. `random`, `bayesian_average` and
`content_no_tags` are offline-evaluation methods only and are not served.

The serving model has **no separate quality metric**; the Step 16 results apply only to
the separately fitted evaluated model. "Shown" events mean *served by the API*, not
seen.
"""


def create_app(
    settings: ApiSettings | None = None,
    engine: Engine | None = None,
    recommender: Recommending | None = None,
) -> FastAPI:
    """Build the app. Raises if ``JWT_SECRET`` is missing or under 32 characters, or
    if the serving artifact fails its SHA-256 check (``recommender`` is for tests)."""
    settings = settings or ApiSettings()  # type: ignore[call-arg]
    app = FastAPI(title="PMRS API", version="0.2.0", description=DESCRIPTION)
    app.state.recommender = (
        recommender
        if recommender is not None
        else load_verified(settings.serving_artifact_dir)
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "PUT", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.state.engine = engine or create_engine(
        load_settings().database_url, pool_pre_ping=True
    )
    app.state.jwt_secret = settings.jwt_secret
    app.state.token_minutes = settings.access_token_minutes
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    for module in (
        auth,
        me,
        movies,
        actions,
        recommendations,
        dashboard,
        analytics,
    ):
        app.include_router(module.router)
    return app
