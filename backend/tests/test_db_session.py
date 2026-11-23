"""Sessions that last one request, and the readiness check."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.migrate import upgrade
from app.db.models import AppSetting
from app.db.session import Database, SessionDep
from app.errors import AppError
from app.main import create_app


@pytest.fixture
def migrated_client(database_url: str) -> Iterator[TestClient]:
    upgrade(database_url)
    app: FastAPI = create_app()

    @app.put("/_test/settings/{key}")
    async def put_setting(key: str, session: SessionDep) -> None:
        session.add(AppSetting(key=key, value=True))

    @app.put("/_test/settings/{key}/then-fail")
    async def put_setting_then_fail(key: str, session: SessionDep) -> None:
        session.add(AppSetting(key=key, value=True))
        await session.flush()
        raise AppError(409, "conflict", "Not this time")

    @app.get("/_test/settings")
    async def list_settings(session: SessionDep) -> list[str]:
        return list((await session.execute(select(AppSetting.key))).scalars())

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_a_request_commits_when_it_succeeds(migrated_client: TestClient) -> None:
    assert migrated_client.put("/_test/settings/kept").status_code == 200
    assert migrated_client.get("/_test/settings").json() == ["kept"]


def test_a_request_rolls_back_when_it_fails(migrated_client: TestClient) -> None:
    assert migrated_client.put("/_test/settings/lost/then-fail").status_code == 409
    assert migrated_client.get("/_test/settings").json() == []


def test_ready_when_the_database_answers(migrated_client: TestClient) -> None:
    response = migrated_client.get("/api/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "release": "1.2.3"}


def test_not_ready_when_the_database_is_down(monkeypatch: pytest.MonkeyPatch) -> None:
    # Nothing listens on port 1, and the server still starts: connecting is lazy.
    monkeypatch.setenv("BLINDSPOT_DATABASE_URL", "postgresql+psycopg://blindspot@127.0.0.1:1/x")
    with TestClient(create_app(), raise_server_exceptions=False) as client:
        assert client.get("/api/health").status_code == 200
        response = client.get("/api/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "database_unavailable"


async def test_the_database_reports_readiness_and_closes(database_url: str) -> None:
    database = Database(database_url)
    assert await database.is_ready()
    await database.close()
