"""API settings from environment variables (or the git-ignored ``.env``).

``JWT_SECRET`` has no default: the app refuses to start without a secret of at least 32
characters. Generate one with ``secrets.token_urlsafe(48)``; never write it in a file
that is committed, and never print or log it.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ApiSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    jwt_secret: str = Field(repr=False, min_length=32)
    access_token_minutes: int = Field(default=60, ge=1, le=1440)
