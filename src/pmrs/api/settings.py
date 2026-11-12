"""API settings from environment variables (or the git-ignored ``.env``).

``JWT_SECRET`` has no default: the app refuses to start without a secret of at least 32
characters. Generate one with ``secrets.token_urlsafe(48)``; never write it in a file
that is committed, and never print or log it.

``FRONTEND_ORIGIN`` is the one browser origin allowed to call the API (CORS). It is an
origin only (scheme, host, optional port): no path and no wildcard.
"""

import re
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ORIGIN = re.compile(r"^https?://[A-Za-z0-9.-]+(:\d{1,5})?$")


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(repr=False, min_length=32)
    access_token_minutes: int = Field(default=60, ge=1, le=1440)
    frontend_origin: str = "http://localhost:5173"
    serving_artifact_dir: Path = Path("data/processed/artifacts/serving_all_data")

    @field_validator("frontend_origin")
    @classmethod
    def _origin(cls, value: str) -> str:
        origin = value.strip().rstrip("/")
        if not _ORIGIN.match(origin):
            raise ValueError(
                "FRONTEND_ORIGIN must be one origin such as http://localhost:5173 "
                "(scheme, host, optional port; no path, no wildcard)"
            )
        return origin
