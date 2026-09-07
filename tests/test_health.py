"""Health endpoint behavior tests."""

from uuid import UUID

from fastapi import Query
from fastapi.testclient import TestClient

from identitymesh.config import Settings
from identitymesh.main import create_app


def test_liveness_returns_safe_service_metadata() -> None:
    client = TestClient(create_app(Settings(environment="test", _env_file=None)))

    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "identitymesh-api",
        "version": "0.0.1",
    }
    UUID(response.headers["X-Request-ID"])


def test_readiness_succeeds_without_required_external_dependencies() -> None:
    client = TestClient(create_app(Settings(environment="test", _env_file=None)))

    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "dependencies": {}}


def test_readiness_fails_safely_when_dependency_is_unavailable() -> None:
    async def unavailable() -> bool:
        return False

    app = create_app(
        Settings(environment="test", _env_file=None),
        readiness_probes={"graph": unavailable},
    )
    client = TestClient(app)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "dependencies": {"graph": "unavailable"},
    }


def test_readiness_hides_dependency_exception_details() -> None:
    async def raises_with_sensitive_detail() -> bool:
        raise RuntimeError("postgresql://user:secret@example.test/database")

    app = create_app(
        Settings(environment="test", _env_file=None),
        readiness_probes={"database": raises_with_sensitive_detail},
    )
    client = TestClient(app)

    response = client.get("/health/ready")

    assert response.status_code == 503
    assert "secret" not in response.text
    assert response.json()["dependencies"] == {"database": "unavailable"}


def test_validation_error_uses_safe_structured_response() -> None:
    app = create_app(Settings(environment="test", _env_file=None))

    @app.get("/test-only")
    async def test_only(limit: int = Query(ge=1)) -> dict[str, int]:
        return {"limit": limit}

    client = TestClient(app)

    response = client.get("/test-only", params={"limit": 0})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
    assert response.json()["error"]["message"] == ("The request did not match the required schema.")
    UUID(response.json()["error"]["request_id"])
