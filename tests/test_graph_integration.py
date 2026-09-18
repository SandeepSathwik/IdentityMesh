import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]
import httpx
import pytest
from neo4j import AsyncDriver, AsyncGraphDatabase

from identitymesh.api import ApplicationServices
from identitymesh.aws_collection_service import AwsIamRoleCollectionService
from identitymesh.aws_evidence_store import AwsIamRoleEvidenceStore
from identitymesh.collectors.aws_iam import (
    COLLECTOR_VERSION,
    AwsRoleCollection,
    AwsRoleEvidence,
    CollectionStatus,
)
from identitymesh.config import Settings
from identitymesh.graph_projection import (
    GraphProjectionVerificationError,
    Neo4jPrincipalProjector,
)
from identitymesh.identity_pipeline import (
    AwsRoleIdentityPipeline,
    AwsRolePipelineCoordinator,
    CollectionAlreadyRunningError,
    IdentityPipeline,
    IdentityPipelineRun,
)
from identitymesh.inventory import InventoryService
from identitymesh.main import create_app
from identitymesh.principal_store import PrincipalStore
from identitymesh.snapshot_store import SnapshotStore
from identitymesh.snapshots import SnapshotStatus

TEST_POSTGRES_DSN = os.getenv("IDENTITYMESH_TEST_POSTGRES_DSN")
TEST_NEO4J_URI = os.getenv("IDENTITYMESH_TEST_NEO4J_URI")
TEST_NEO4J_USERNAME = os.getenv("IDENTITYMESH_TEST_NEO4J_USERNAME", "neo4j")
TEST_NEO4J_PASSWORD = os.getenv("IDENTITYMESH_TEST_NEO4J_PASSWORD")
NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)
ACCOUNT_ID = "123456789012"
CALLER_ARN = f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/IdentityMeshCollector/run"
TOKEN = "graph-integration-token-at-least-32-characters"  # noqa: S105


class SyntheticCollector:
    def __init__(self, *, empty: bool = False, display_name: str = "ApplicationRole") -> None:
        self.empty = empty
        self.display_name = display_name

    def collect(self, snapshot_id: UUID) -> AwsRoleCollection:
        roles: tuple[AwsRoleEvidence, ...] = ()
        if not self.empty:
            arn = f"arn:aws:iam::{ACCOUNT_ID}:role/application/{self.display_name}"
            roles = (
                AwsRoleEvidence(
                    snapshot_id=snapshot_id,
                    source_id=arn,
                    account_id=ACCOUNT_ID,
                    collector_principal_arn=CALLER_ARN,
                    collected_at=NOW,
                    collector_version=COLLECTOR_VERSION,
                    role_id=f"ARO{snapshot_id.hex[:16].upper()}",
                    role_name=self.display_name,
                    arn=arn,
                    path="/application/",
                    created_at=NOW,
                    assume_role_policy_document={"Version": "2012-10-17", "Statement": []},
                    description="Synthetic integration role",
                    max_session_duration=3600,
                    tags={"Environment": "test"},
                ),
            )
        return AwsRoleCollection(
            snapshot_id=snapshot_id,
            collected_at=NOW,
            status=CollectionStatus.COMPLETE,
            account_id=ACCOUNT_ID,
            collector_principal_arn=CALLER_ARN,
            roles=roles,
        )


class VerificationFailureProjector(Neo4jPrincipalProjector):
    async def verify(
        self,
        snapshot_id: UUID,
        expected_count: int,
        expected_digest: str,
    ) -> None:
        del snapshot_id, expected_count, expected_digest
        raise GraphProjectionVerificationError("synthetic verification failure")


@pytest.fixture
async def graph_dependencies() -> AsyncIterator[tuple[asyncpg.Pool, AsyncDriver]]:
    if TEST_POSTGRES_DSN is None or TEST_NEO4J_URI is None or TEST_NEO4J_PASSWORD is None:
        pytest.skip("PostgreSQL and Neo4j integration settings are not configured")
    pool = await asyncpg.create_pool(TEST_POSTGRES_DSN, min_size=1, max_size=6)
    driver = AsyncGraphDatabase.driver(
        TEST_NEO4J_URI,
        auth=(TEST_NEO4J_USERNAME, TEST_NEO4J_PASSWORD),
    )
    try:
        await driver.verify_connectivity()
        async with pool.acquire() as connection:
            await connection.execute("TRUNCATE snapshots CASCADE")
            await connection.execute(
                "INSERT INTO active_snapshot (singleton) VALUES (TRUE) "
                "ON CONFLICT (singleton) DO UPDATE "
                "SET snapshot_id = NULL, activated_at = NULL"
            )
        yield pool, driver
    finally:
        async with pool.acquire() as connection:
            snapshot_ids = [
                str(row["snapshot_id"])
                for row in await connection.fetch(
                    "SELECT snapshot_id FROM snapshots ORDER BY sequence_id"
                )
            ]
        if snapshot_ids:
            await driver.execute_query(
                """
                MATCH (node)
                WHERE (node:Principal OR node:IdentityMeshProjection)
                  AND node.snapshot_id IN $snapshot_ids
                DETACH DELETE node
                """,
                parameters_={"snapshot_ids": snapshot_ids},
                database_="neo4j",
            )
        async with pool.acquire() as connection:
            await connection.execute("TRUNCATE snapshots CASCADE")
            await connection.execute(
                "INSERT INTO active_snapshot (singleton) VALUES (TRUE) "
                "ON CONFLICT (singleton) DO UPDATE "
                "SET snapshot_id = NULL, activated_at = NULL"
            )
        await driver.close()
        await pool.close()


def _pipeline(
    pool: asyncpg.Pool,
    driver: AsyncDriver,
    collector: SyntheticCollector,
    *,
    projector: Neo4jPrincipalProjector | None = None,
) -> tuple[AwsRolePipelineCoordinator, InventoryService]:
    snapshots = SnapshotStore(pool)
    graph = projector or Neo4jPrincipalProjector(driver)
    collection = AwsIamRoleCollectionService(
        snapshots,
        AwsIamRoleEvidenceStore(pool),
        collector,
    )
    pipeline = AwsRoleIdentityPipeline(
        collection,
        snapshots,
        PrincipalStore(pool),
        graph,
    )
    return AwsRolePipelineCoordinator(pool, pipeline), InventoryService(snapshots, graph)


@pytest.mark.anyio
async def test_synthetic_post_runs_full_verified_pipeline(
    graph_dependencies: tuple[asyncpg.Pool, AsyncDriver],
) -> None:
    pool, driver = graph_dependencies
    coordinator, inventory = _pipeline(
        pool,
        driver,
        SyntheticCollector(display_name="<script>alert(1)</script>"),
    )
    settings = Settings(
        data_api_enabled=True,
        api_token=TOKEN,
        aws_allowed_account_id=ACCOUNT_ID,
        postgres_dsn=TEST_POSTGRES_DSN,
        neo4j_uri=TEST_NEO4J_URI,
        neo4j_username=TEST_NEO4J_USERNAME,
        neo4j_password=TEST_NEO4J_PASSWORD,
        _env_file=None,
    )
    app = create_app(
        settings,
        readiness_probes={},
        services=ApplicationServices(coordinator=coordinator, inventory=inventory),
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        run = await client.post(
            "/api/v1/collections/aws/iam/roles",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        principals = await client.get(
            "/api/v1/principals",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        graph = await client.get(
            "/api/v1/graph",
            headers={"Authorization": f"Bearer {TOKEN}"},
        )

    assert run.status_code == 200
    assert run.json()["snapshot_status"] == "ready"
    assert run.json()["activated"] is True
    assert principals.json()["items"][0]["display_name"] == "<script>alert(1)</script>"
    assert graph.json()["relationships"] == []
    active = await SnapshotStore(pool).get_active()
    assert active is not None
    assert active.snapshot_id == UUID(run.json()["snapshot_id"])


@pytest.mark.anyio
async def test_empty_collection_projects_and_promotes_valid_absence(
    graph_dependencies: tuple[asyncpg.Pool, AsyncDriver],
) -> None:
    pool, driver = graph_dependencies
    coordinator, inventory = _pipeline(pool, driver, SyntheticCollector(empty=True))

    run = await coordinator.run()
    page = await inventory.principals(limit=10, cursor=None)

    assert run.snapshot_status is SnapshotStatus.READY
    assert run.principal_count == 0
    assert page.items == ()


@pytest.mark.anyio
async def test_verification_failure_preserves_previous_active_snapshot(
    graph_dependencies: tuple[asyncpg.Pool, AsyncDriver],
) -> None:
    pool, driver = graph_dependencies
    first, _ = _pipeline(pool, driver, SyntheticCollector(display_name="StableRole"))
    ready = await first.run()
    failing_projector = VerificationFailureProjector(driver)
    second, _ = _pipeline(
        pool,
        driver,
        SyntheticCollector(display_name="UnverifiedRole"),
        projector=failing_projector,
    )

    failed = await second.run()
    active = await SnapshotStore(pool).get_active()

    assert failed.snapshot_status is SnapshotStatus.FAILED
    assert failed.failure_code == "GRAPH_PROJECTION_VERIFICATION_FAILED"
    assert active is not None
    assert active.snapshot_id == ready.snapshot_id


@pytest.mark.anyio
async def test_projection_rebuild_is_idempotent_and_detects_later_corruption(
    graph_dependencies: tuple[asyncpg.Pool, AsyncDriver],
) -> None:
    pool, driver = graph_dependencies
    coordinator, _ = _pipeline(pool, driver, SyntheticCollector(display_name="StableRole"))
    run = await coordinator.run()
    principals = await PrincipalStore(pool).load_snapshot(run.snapshot_id)
    projector = Neo4jPrincipalProjector(driver)

    first = await projector.project_and_verify(run.snapshot_id, principals)
    second = await projector.project_and_verify(run.snapshot_id, principals)
    records, _, _ = await driver.execute_query(
        """
        MATCH (node:Principal {snapshot_id: $snapshot_id, projection_version: $version})
        RETURN count(node) AS count
        """,
        parameters_={"snapshot_id": str(run.snapshot_id), "version": second.projection_version},
        database_="neo4j",
    )

    assert first.content_sha256 == second.content_sha256
    assert records[0]["count"] == 1

    await driver.execute_query(
        """
        MATCH (node:Principal {snapshot_id: $snapshot_id, projection_version: $version})
        REMOVE node:AwsRole
        """,
        parameters_={"snapshot_id": str(run.snapshot_id), "version": second.projection_version},
        database_="neo4j",
    )
    with pytest.raises(GraphProjectionVerificationError):
        await projector.verify(run.snapshot_id, second.principal_count, second.content_sha256)


class BlockingPipeline(IdentityPipeline):
    def __init__(self, entered: asyncio.Event, release: asyncio.Event) -> None:
        self.entered = entered
        self.release = release

    async def run(self) -> IdentityPipelineRun:
        self.entered.set()
        await self.release.wait()
        raise AssertionError("blocking pipeline should be cancelled")


@pytest.mark.anyio
async def test_postgres_advisory_lock_rejects_concurrent_collection(
    graph_dependencies: tuple[asyncpg.Pool, AsyncDriver],
) -> None:
    pool, _ = graph_dependencies
    entered = asyncio.Event()
    release = asyncio.Event()
    coordinator = AwsRolePipelineCoordinator(pool, BlockingPipeline(entered, release))
    first = asyncio.create_task(coordinator.run())
    await entered.wait()

    with pytest.raises(CollectionAlreadyRunningError):
        await coordinator.run()

    first.cancel()
    with pytest.raises(asyncio.CancelledError):
        await first
