"""Shared test setup."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every test reads the environment afresh."""
    monkeypatch.setenv("BLINDSPOT_ENVIRONMENT", "test")
    monkeypatch.setenv("BLINDSPOT_RELEASE", "1.2.3")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def app() -> FastAPI:
    """A new app."""
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    """A client that returns error responses instead of raising server errors."""
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
