"""Construction and cleanup of data-API runtime dependencies."""

from dataclasses import dataclass
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]
from neo4j import AsyncDriver, AsyncGraphDatabase

from identitymesh.api import ApplicationServices
from identitymesh.aws_collection_service import AwsIamRoleCollectionService
from identitymesh.aws_evidence_store import AwsIamRoleEvidenceStore
from identitymesh.collectors.aws_iam import (
    AwsIamRoleCollector,
    AwsRoleCollection,
    Boto3AwsIamApi,
)
from identitymesh.config import Settings
from identitymesh.graph_projection import Neo4jPrincipalProjector
from identitymesh.identity_pipeline import AwsRoleIdentityPipeline, AwsRolePipelineCoordinator
from identitymesh.inventory import InventoryService
from identitymesh.principal_store import PrincipalStore
from identitymesh.snapshot_store import SnapshotStore


class LazyBoto3AwsRoleCollector:
    """Create provider clients inside the collection worker thread."""

    def __init__(self, allowed_account_id: str) -> None:
        self._allowed_account_id = allowed_account_id

    def collect(self, snapshot_id: UUID) -> AwsRoleCollection:
        collector = AwsIamRoleCollector(
            Boto3AwsIamApi(),
            allowed_account_id=self._allowed_account_id,
        )
        return collector.collect(snapshot_id)


@dataclass(frozen=True, slots=True)
class RuntimeResources:
    """Owned database resources and the services built from them."""

    pool: asyncpg.Pool
    driver: AsyncDriver
    services: ApplicationServices

    async def close(self) -> None:
        await self.driver.close()
        await self.pool.close()


async def create_runtime(settings: Settings) -> RuntimeResources:
    """Create the production service graph from fail-closed settings."""

    if not settings.data_api_enabled:
        raise ValueError("data API runtime cannot be created while disabled")
    if (
        settings.postgres_dsn is None
        or settings.neo4j_uri is None
        or settings.neo4j_username is None
        or settings.neo4j_password is None
        or settings.aws_allowed_account_id is None
    ):
        raise ValueError("data API runtime configuration is incomplete")

    pool = await asyncpg.create_pool(dsn=settings.postgres_dsn.get_secret_value())
    driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_username, settings.neo4j_password.get_secret_value()),
        connection_timeout=settings.dependency_timeout_seconds,
    )
    try:
        snapshots = SnapshotStore(pool)
        evidence = AwsIamRoleEvidenceStore(pool)
        principals = PrincipalStore(pool)
        projector = Neo4jPrincipalProjector(driver, settings.neo4j_database)
        collector = LazyBoto3AwsRoleCollector(settings.aws_allowed_account_id)
        collection = AwsIamRoleCollectionService(snapshots, evidence, collector)
        pipeline = AwsRoleIdentityPipeline(collection, snapshots, principals, projector)
        coordinator = AwsRolePipelineCoordinator(pool, pipeline)
        inventory = InventoryService(snapshots, projector)
        return RuntimeResources(
            pool=pool,
            driver=driver,
            services=ApplicationServices(coordinator=coordinator, inventory=inventory),
        )
    except Exception:
        await driver.close()
        await pool.close()
        raise
