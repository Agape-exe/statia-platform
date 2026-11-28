import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import app, create_app


def test_health():
    response = TestClient(app).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "statia-platform-api"}
    assert response.headers["X-Statia-Planning-Version"] == "8"


def test_origins_and_cors():
    settings = Settings(allowed_origins="http://localhost:5173, https://example.org ")
    assert settings.origins == ["http://localhost:5173", "https://example.org"]
    client = TestClient(create_app(settings))
    assert (
        client.get("/health", headers={"Origin": "https://example.org"}).headers["access-control-allow-origin"]
        == "https://example.org"
    )
    assert (
        "access-control-allow-origin" not in client.get("/health", headers={"Origin": "https://untrusted.org"}).headers
    )


def test_missing_route():
    assert TestClient(app).get("/missing").status_code == 404


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.vercel.app",
        "https://example.org/",
        "https://example.org/path",
        "https://user:pass@example.org",
        "https://example.org?q=1",
    ],
)
def test_rejects_non_exact_origins(origin):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, allowed_origins=origin)


def test_authorized_cors_preflight_and_diagnostic_headers():
    client = TestClient(create_app(Settings(_env_file=None)))
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    headers = client.get("/health", headers={"Origin": "http://localhost:5173"}).headers
    assert "X-Statia-Error" in headers["access-control-expose-headers"]
