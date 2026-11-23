"""Shared test setup."""

import os
import uuid
from collections.abc import Iterator
from typing import cast

import psycopg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg import sql

from app.auth.setup_code import SetupGate
from app.config import get_settings
from app.db.events import connection_string
from app.db.migrate import upgrade
from app.main import create_app
from app.vault import set_vault

TEST_SECRET_KEY = "test-key-0123456789abcdef0123456789abcdef"


@pytest.fixture(autouse=True)
def _fresh_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Every test reads the environment afresh."""
    monkeypatch.setenv("BLINDSPOT_ENVIRONMENT", "test")
    monkeypatch.setenv("BLINDSPOT_RELEASE", "1.2.3")
    monkeypatch.setenv("BLINDSPOT_SECRET_KEY", TEST_SECRET_KEY)
    set_vault(None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
    set_vault(None)


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


SAME_SITE = {"Origin": "https://testserver", "Sec-Fetch-Site": "same-origin"}
GOOD_PASSWORD = "correct horse battery staple"


@pytest.fixture
def api(database_url: str) -> Iterator[TestClient]:
    """The app on a migrated database, reached the way a browser reaches it: over https and
    from its own pages (so the cross-site check passes)."""
    upgrade(database_url)
    with TestClient(
        create_app(),
        base_url="https://testserver",
        raise_server_exceptions=False,
        headers=SAME_SITE,
    ) as client:
        yield client


def app_of(client: TestClient) -> FastAPI:
    """The app a test client is talking to."""
    return cast("FastAPI", client.app)


def setup_code(client: TestClient) -> str:
    """The code the app printed for first-run setup."""
    gate = cast("SetupGate", app_of(client).state.setup_gate)
    assert gate.code is not None
    return gate.code


def set_up(client: TestClient, username: str = "admin", password: str = GOOD_PASSWORD) -> None:
    """Do first-run setup, which also signs the client in as the new administrator."""
    answer = client.post(
        "/api/auth/setup",
        json={"setup_code": setup_code(client), "username": username, "password": password},
    )
    assert answer.status_code == 200, answer.text


def add_account(
    client: TestClient, username: str, role: str = "viewer", password: str = GOOD_PASSWORD
) -> str:
    """Add an account as the signed-in administrator; returns its id."""
    answer = client.post(
        "/api/users", json={"username": username, "role": role, "password": password}
    )
    assert answer.status_code == 201, answer.text
    return answer.json()["id"]


def another_browser(client: TestClient, username: str, password: str = GOOD_PASSWORD) -> TestClient:
    """A second browser (its own cookies) on the same app, signed in as an account."""
    browser = TestClient(
        app_of(client),
        base_url="https://testserver",
        raise_server_exceptions=False,
        headers=SAME_SITE,
    )
    answer = browser.post("/api/auth/login", json={"username": username, "password": password})
    assert answer.status_code == 200, answer.text
    return browser


def accept_terms(client: TestClient) -> None:
    """Read and accept the terms of use as the signed-in account."""
    current = client.get("/api/terms")
    assert current.status_code == 200, current.text
    answer = client.post("/api/terms/accept", json={"version": current.json()["version"]})
    assert answer.status_code == 200, answer.text


@pytest.fixture
def admin(api: TestClient) -> TestClient:
    """The app with first-run setup done, signed in as the administrator, who has accepted the
    terms of use."""
    set_up(api)
    accept_terms(api)
    return api
