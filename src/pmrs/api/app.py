"""The FastAPI application.

    uv run uvicorn pmrs.api.app:create_app --factory

Local use only: do not expose it publicly until HTTPS and rate limiting exist (owner
decision, D-037). Interactive docs are at /docs.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, create_engine

from pmrs.api import actions, auth, me, movies
from pmrs.api.settings import ApiSettings
from pmrs.db.settings import load_settings


async def _validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
    """422 without echoing the submitted values: a rejected password must not come back
    in the response (FastAPI's default includes it)."""
    detail = [
        {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]}
        for e in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


def create_app(
    settings: ApiSettings | None = None, engine: Engine | None = None
) -> FastAPI:
    """Build the app. Raises if ``JWT_SECRET`` is missing or under 32 characters."""
    settings = settings or ApiSettings()  # type: ignore[call-arg]
    app = FastAPI(title="PMRS API", version="0.1.0")
    app.state.engine = engine or create_engine(
        load_settings().database_url, pool_pre_ping=True
    )
    app.state.jwt_secret = settings.jwt_secret
    app.state.token_minutes = settings.access_token_minutes
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]
    for module in (auth, me, movies, actions):
        app.include_router(module.router)
    return app
