"""Settings, read from the environment (variables start with BLINDSPOT_)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Everything the app can be told from outside. Secrets never have a default here."""

    model_config = SettingsConfigDict(env_prefix="BLINDSPOT_", extra="ignore")

    environment: str = Field(default="production", pattern="^(production|development|test)$")
    release: str = "dev"
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    # PostgreSQL over the unix socket the container creates: no host, no port and no password,
    # because the server trusts the operating system user (peer authentication).
    database_url: str = "postgresql+psycopg://blindspot@/blindspot?host=/run/postgresql"


@lru_cache
def get_settings() -> Settings:
    """The settings, read once."""
    return Settings()
