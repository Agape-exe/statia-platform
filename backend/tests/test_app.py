from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import app, create_app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "statia-platform-api"}


def test_origins_and_cors():
    settings = Settings(allowed_origins="http://localhost:5173, https://example.org ")
    assert settings.origins == ["http://localhost:5173", "https://example.org"]
    client = TestClient(create_app(settings))
    assert client.get("/health", headers={"Origin": "https://example.org"}).headers[
        "access-control-allow-origin"
    ] == "https://example.org"
    assert "access-control-allow-origin" not in client.get(
        "/health", headers={"Origin": "https://untrusted.org"}
    ).headers


def test_missing_route():
    assert TestClient(app).get("/missing").status_code == 404
