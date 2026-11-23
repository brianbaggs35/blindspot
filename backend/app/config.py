"""Settings, read from the environment (variables start with BLINDSPOT_)."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
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

    model_config = SettingsConfigDict(
        env_prefix="BLINDSPOT_",
        extra="ignore",
        # compose passes variables it was not given as empty text, which means not set.
        env_ignore_empty=True,
    )

    environment: str = Field(default="production", pattern="^(production|development|test)$")
    release: str = "dev"
    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    # Where the app keeps what must survive a restart (the container mounts a volume here).
    data_dir: Path = Path("/data")
    # The app secret key, which seals every credential before it is stored. Give it as a value
    # or as the path of a file (a Docker secret is one); with neither, a key is generated into
    # `<data_dir>/secrets/secret.key` the first time. See docs/how-to/secrets.md.
    secret_key: SecretStr | None = None
    secret_key_file: Path | None = None
    # While rotating, the key the data is sealed with now.
    previous_secret_key: SecretStr | None = None
    database_url: str = Field(default_factory=lambda: SOCKET_DATABASE_URL)
    # Sessions: signed out after this long without a request, and at the latest after the total.
    session_idle_minutes: int = Field(default=60, ge=1, le=1440)
    session_total_hours: int = Field(default=12, ge=1, le=720)
    # The session cookie is only sent over https. Turn this off only for development over http.
    cookie_secure: bool = True
    # An account locks for `lockout_minutes` after this many wrong passwords in a row.
    lockout_attempts: int = Field(default=5, ge=3, le=50)
    lockout_minutes: int = Field(default=15, ge=1, le=1440)
    # An address that fails this many times in `throttle_window_minutes` waits for the window.
    throttle_failures: int = Field(default=10, ge=3, le=1000)
    throttle_window_minutes: int = Field(default=5, ge=1, le=60)


@lru_cache
def get_settings() -> Settings:
    """The settings, read once."""
    return Settings()
