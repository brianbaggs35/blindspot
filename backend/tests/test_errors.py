"""Errors come out as problem details with a code and the request id, and never a stack trace."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import AppError


class Item(BaseModel):
    name: str


def test_unknown_path_is_a_problem(client: TestClient) -> None:
    response = client.get("/api/nothing-here")
    body = response.json()
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert body["code"] == "http_404"
    assert body["title"] == "Not Found"
    assert body["request_id"] == response.headers["X-Request-ID"]


def test_app_error_keeps_its_code_and_detail(app: FastAPI, client: TestClient) -> None:
    @app.get("/api/boom-known")
    async def known() -> None:
        raise AppError(409, "conflict_example", "That already exists", "Pick another name")

    body = client.get("/api/boom-known").json()
    assert (body["status"], body["code"], body["detail"]) == (
        409,
        "conflict_example",
        "Pick another name",
    )


def test_validation_errors_list_the_fields(app: FastAPI, client: TestClient) -> None:
    @app.post("/api/items")
    async def create(item: Item) -> Item:
        return item

    response = client.post("/api/items", json={"nope": 1})
    body = response.json()
    assert response.status_code == 422
    assert body["code"] == "validation_failed"
    assert body["errors"][0]["field"] == "body.name"


def test_unexpected_errors_are_generic(app: FastAPI, client: TestClient) -> None:
    @app.get("/api/boom-unknown")
    async def unknown() -> None:
        raise RuntimeError("secret internal detail")

    response = client.get("/api/boom-unknown")
    assert response.status_code == 500
    assert response.json()["code"] == "internal_error"
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
