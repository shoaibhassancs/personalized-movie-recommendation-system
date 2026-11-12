"""Database settings, read from environment variables (or a git-ignored ``.env``).

Nothing secret has a default and nothing secret is written in committed files.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """``DATABASE_URL`` is the dev database; ``TEST_DATABASE_URL`` is a separate one."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(repr=False)  # the URL holds the password: never print it
    test_database_url: str | None = Field(default=None, repr=False)


def load_settings() -> DatabaseSettings:
    return DatabaseSettings()  # type: ignore[call-arg]  # filled from the environment
