"""The health endpoint and the request id."""

from fastapi.testclient import TestClient


def test_health_reports_ok_and_the_release(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "release": "1.2.3"}


def test_every_response_has_a_request_id(client: TestClient) -> None:
    first = client.get("/api/health").headers["X-Request-ID"]
    second = client.get("/api/health").headers["X-Request-ID"]
    assert len(first) == 32
    assert first != second
