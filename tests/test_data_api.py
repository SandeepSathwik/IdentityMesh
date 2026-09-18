from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from identitymesh.api import ApplicationServices
from identitymesh.collectors.aws_iam import CollectionStatus
from identitymesh.config import Settings
from identitymesh.graph_projection import PROJECTION_VERSION, ProjectedPrincipal
from identitymesh.identity_pipeline import CollectionAlreadyRunningError, IdentityPipelineRun
from identitymesh.inventory import ActiveSnapshotNotFoundError, PrincipalPage
from identitymesh.main import create_app
from identitymesh.snapshots import Snapshot, SnapshotStatus

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
TOKEN = "test-api-token-that-is-at-least-32-characters"  # noqa: S105


def _settings() -> Settings:
    return Settings(
        data_api_enabled=True,
        api_token=TOKEN,
        aws_allowed_account_id="123456789012",
        postgres_dsn="postgresql://unused:unused@localhost/unused",
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="unused-test-password",  # noqa: S106 - synthetic test configuration
        _env_file=None,
    )


def _snapshot(snapshot_id: UUID | None = None) -> Snapshot:
    return Snapshot(
        snapshot_id=snapshot_id or uuid4(),
        sequence_id=7,
        status=SnapshotStatus.READY,
        collector_version="aws-iam-role/0.1",
        projection_version=PROJECTION_VERSION,
        failure_code=None,
        created_at=NOW,
        collected_at=NOW,
        projection_started_at=NOW,
        ready_at=NOW,
        failed_at=None,
    )


def _principal(snapshot_id: UUID) -> ProjectedPrincipal:
    return ProjectedPrincipal(
        snapshot_id=snapshot_id,
        projection_version=PROJECTION_VERSION,
        principal_id=uuid4(),
        external_id="arn:aws:iam::123456789012:role/<script>alert(1)</script>",
        provider="aws",
        principal_type="cloud_role",
        display_name="<script>alert(1)</script>",
        created_at=NOW,
        discovered_at=NOW,
        source_system="aws",
        source_object_type="iam_role",
        source_object_id="arn:aws:iam::123456789012:role/test",
        collected_at=NOW,
        collector_version="aws-iam-role/0.1",
        collector_principal_id="arn:aws:sts::123456789012:assumed-role/collector/run",
        evidence_schema_version="aws.iam.role/v1",
        evidence_classification="observed",
    )


class FakeCoordinator:
    async def run(self) -> IdentityPipelineRun:
        return IdentityPipelineRun(
            snapshot_id=uuid4(),
            collection_status=CollectionStatus.COMPLETE,
            snapshot_status=SnapshotStatus.READY,
            failure_code=None,
            role_count=1,
            gap_count=0,
            principal_count=1,
            projection_version=PROJECTION_VERSION,
            activated=True,
        )


class BusyCoordinator:
    async def run(self) -> IdentityPipelineRun:
        raise CollectionAlreadyRunningError("busy")


class FakeInventory:
    def __init__(self, *, active: bool = True) -> None:
        self.snapshot = _snapshot()
        self.active = active

    async def active_snapshot(self) -> Snapshot:
        if not self.active:
            raise ActiveSnapshotNotFoundError("missing")
        return self.snapshot

    async def recent_snapshots(self, limit: int) -> tuple[Snapshot, ...]:
        return (self.snapshot,)[:limit]

    async def principals(self, *, limit: int, cursor: UUID | None) -> PrincipalPage:
        del cursor
        if not self.active:
            raise ActiveSnapshotNotFoundError("missing")
        items = (_principal(self.snapshot.snapshot_id),)[:limit]
        return PrincipalPage(
            snapshot=self.snapshot,
            items=items,
            next_cursor=None,
            total_count=len(items),
        )


def _client(*, active: bool = True, coordinator: object | None = None) -> TestClient:
    services = ApplicationServices(
        coordinator=coordinator or FakeCoordinator(),  # type: ignore[arg-type]
        inventory=FakeInventory(active=active),  # type: ignore[arg-type]
    )
    return TestClient(create_app(_settings(), readiness_probes={}, services=services))


def _headers(token: str = TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_data_routes_fail_closed_without_valid_bearer_token() -> None:
    with _client() as client:
        missing = client.get("/api/v1/snapshots")
        invalid = client.get("/api/v1/snapshots", headers=_headers("x" * 32))

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert missing.json()["error"]["code"] == "AUTHENTICATION_FAILED"
    assert missing.headers["www-authenticate"] == "Bearer"
    assert "x-request-id" in missing.headers


def test_data_routes_fail_closed_when_not_configured() -> None:
    app = create_app(Settings(_env_file=None), readiness_probes={})
    with TestClient(app) as client:
        response = client.get("/api/v1/snapshots")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATA_API_NOT_CONFIGURED"


def test_concurrent_collection_returns_structured_conflict() -> None:
    with _client(coordinator=BusyCoordinator()) as client:
        response = client.post("/api/v1/collections/aws/iam/roles", headers=_headers())

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "AWS_COLLECTION_ALREADY_RUNNING"


def test_query_validation_uses_safe_error_envelope() -> None:
    with _client() as client:
        response = client.get("/api/v1/snapshots?limit=0", headers=_headers())

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"


def test_collection_and_inventory_contracts_are_versioned() -> None:
    with _client() as client:
        run = client.post("/api/v1/collections/aws/iam/roles", headers=_headers())
        snapshots = client.get("/api/v1/snapshots", headers=_headers())
        principals = client.get("/api/v1/principals", headers=_headers())
        graph = client.get("/api/v1/graph", headers=_headers())

    assert run.status_code == 200
    assert run.json()["schema_version"] == "identitymesh.collection-run/v1"
    assert run.json()["snapshot_status"] == "ready"
    assert snapshots.json()["schema_version"] == "identitymesh.snapshot-list/v1"
    assert principals.json()["schema_version"] == "identitymesh.principal-page/v1"
    assert principals.json()["items"][0]["display_name"] == "<script>alert(1)</script>"
    assert graph.json()["schema_version"] == "identitymesh.graph/v1"
    assert graph.json()["relationships"] == []


def test_active_inventory_absence_is_explicit() -> None:
    with _client(active=False) as client:
        response = client.get("/api/v1/snapshots/active", headers=_headers())

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "ACTIVE_SNAPSHOT_NOT_FOUND"


def test_dashboard_is_data_free_and_has_strict_security_headers() -> None:
    with _client() as client:
        response = client.get("/")
        script = client.get("/assets/dashboard.js")

    assert response.status_code == 200
    assert "Observed identities" in response.text
    assert TOKEN not in response.text
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert "textContent" in script.text
    assert "innerHTML" not in script.text
    assert "localStorage" not in script.text
    assert "sessionStorage" not in script.text
