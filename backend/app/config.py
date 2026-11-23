"""Settings, read from the environment (variables start with BLINDSPOT_)."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL

# PostgreSQL over the unix socket the container creates: no host, no port and no password,
# because the server trusts the operating system user (peer authentication).
SOCKET_DATABASE_URL = URL.create(
    "postgresql+psycopg",
    username="blindspot",
    database="blindspot",
    query={"host": "/run/postgresql"},
).render_as_string()


class Settings(BaseSettings):
    """Everything the app can be told from outside. Secrets never have a default here."""

    model_config = SettingsConfigDict(env_prefix="BLINDSPOT_", extra="ignore")

    environment: str = Field(default="production", pattern="^(production|development|test)$")
    release: str = "dev"
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    database_url: str = Field(default_factory=lambda: SOCKET_DATABASE_URL)


@lru_cache
def get_settings() -> Settings:
    """The settings, read once."""
    return Settings()
