"""Settings and the application factory."""

import pytest
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.main import create_app


def test_settings_come_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLINDSPOT_LOG_LEVEL", "DEBUG")
    assert Settings().log_level == "DEBUG"


def test_settings_reject_an_unknown_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLINDSPOT_ENVIRONMENT", "staging")
    with pytest.raises(ValidationError):
        Settings()


def test_settings_are_read_once() -> None:
    assert get_settings() is get_settings()


def test_docs_are_off_outside_development() -> None:
    assert create_app().docs_url is None


def test_docs_are_on_in_development(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BLINDSPOT_ENVIRONMENT", "development")
    get_settings.cache_clear()
    assert create_app().docs_url == "/api/docs"
