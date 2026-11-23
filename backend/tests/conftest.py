"""Shared test setup."""

import os
import uuid
from collections.abc import Iterator

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql

from app.config import get_settings
from app.db.events import connection_string
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


@pytest.fixture
def database_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """An empty database made for one test and dropped after it, so no two tests (and no two
    runs) ever share one. The server is the one named by BLINDSPOT_TEST_DATABASE_URL, and the
    app is pointed at the new database through BLINDSPOT_DATABASE_URL."""
    server = os.environ.get("BLINDSPOT_TEST_DATABASE_URL")
    if not server:
        pytest.fail("Set BLINDSPOT_TEST_DATABASE_URL to a PostgreSQL server the tests may use.")
    name = f"blindspot_test_{uuid.uuid4().hex}"
    with psycopg.connect(connection_string(server), autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    url = server.rsplit("/", 1)[0] + "/" + name
    monkeypatch.setenv("BLINDSPOT_DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        yield url
    finally:
        with psycopg.connect(connection_string(server), autocommit=True) as admin:
            admin.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(name)))
