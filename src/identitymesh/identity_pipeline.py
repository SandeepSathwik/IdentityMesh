"""End-to-end orchestration for AWS role collection and graph promotion."""

from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from identitymesh.aws_collection_service import AwsIamRoleCollectionService
from identitymesh.collectors.aws_iam import CollectionStatus
from identitymesh.graph_projection import (
    PROJECTION_VERSION,
    GraphProjectionError,
    Neo4jPrincipalProjector,
)
from identitymesh.principal_store import PrincipalSourceError, PrincipalStore
from identitymesh.snapshot_store import SnapshotStore
from identitymesh.snapshots import SnapshotStatus

_AWS_COLLECTION_ADVISORY_LOCK = 4_932_144_657_367_141_027


class CollectionAlreadyRunningError(Exception):
    """Raised when the singleton AWS collection lock is already held."""

    reason_code = "AWS_COLLECTION_ALREADY_RUNNING"


class IdentityPipelineRunError(Exception):
    """Raised when a terminal pipeline failure cannot be recorded safely."""

    reason_code = "IDENTITY_PIPELINE_FAILED"

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(f"identity pipeline failed with {reason_code}")


@dataclass(frozen=True, slots=True)
class IdentityPipelineRun:
    """Terminal result of collection, persistence, projection, and promotion."""

    snapshot_id: UUID
    collection_status: CollectionStatus
    snapshot_status: SnapshotStatus
    failure_code: str | None
    role_count: int
    gap_count: int
    principal_count: int
    projection_version: str | None
    activated: bool


class IdentityPipeline(Protocol):
    """Pipeline contract used by the concurrency coordinator."""

    async def run(self) -> IdentityPipelineRun: ...


class AwsRoleIdentityPipeline:
    """Promote only complete and exactly verified AWS role evidence."""

    def __init__(
        self,
        collection: AwsIamRoleCollectionService,
        snapshots: SnapshotStore,
        principals: PrincipalStore,
        projector: Neo4jPrincipalProjector,
    ) -> None:
        self._collection = collection
        self._snapshots = snapshots
        self._principals = principals
        self._projector = projector

    async def run(self) -> IdentityPipelineRun:
        collected = await self._collection.run()
        if collected.snapshot_status is not SnapshotStatus.COLLECTED:
            return IdentityPipelineRun(
                snapshot_id=collected.snapshot_id,
                collection_status=collected.collection_status,
                snapshot_status=collected.snapshot_status,
                failure_code=collected.failure_code,
                role_count=collected.role_count,
                gap_count=collected.gap_count,
                principal_count=0,
                projection_version=None,
                activated=False,
            )

        try:
            principals = await self._principals.load_snapshot(collected.snapshot_id)
            await self._snapshots.start_projection(collected.snapshot_id, PROJECTION_VERSION)
            projection = await self._projector.project_and_verify(
                collected.snapshot_id,
                principals,
            )
            promotion = await self._snapshots.complete_projection(collected.snapshot_id)
        except Exception as error:
            failure_code = _projection_failure_code(error)
            try:
                failed = await self._snapshots.mark_failed(collected.snapshot_id, failure_code)
            except Exception as recording_error:
                raise IdentityPipelineRunError(
                    "GRAPH_PROJECTION_FAILURE_RECORDING_FAILED"
                ) from recording_error
            return IdentityPipelineRun(
                snapshot_id=collected.snapshot_id,
                collection_status=collected.collection_status,
                snapshot_status=failed.status,
                failure_code=failed.failure_code,
                role_count=collected.role_count,
                gap_count=collected.gap_count,
                principal_count=0,
                projection_version=failed.projection_version,
                activated=False,
            )

        return IdentityPipelineRun(
            snapshot_id=collected.snapshot_id,
            collection_status=collected.collection_status,
            snapshot_status=promotion.snapshot.status,
            failure_code=promotion.snapshot.failure_code,
            role_count=collected.role_count,
            gap_count=collected.gap_count,
            principal_count=projection.principal_count,
            projection_version=projection.projection_version,
            activated=promotion.activated,
        )


def _projection_failure_code(error: Exception) -> str:
    if isinstance(error, (GraphProjectionError, PrincipalSourceError)):
        return error.reason_code
    return "GRAPH_PROJECTION_INTERNAL_ERROR"


class AwsRolePipelineCoordinator:
    """Serialize AWS collection runs across application processes."""

    def __init__(self, pool: asyncpg.Pool, pipeline: IdentityPipeline) -> None:
        self._pool = pool
        self._pipeline = pipeline

    async def run(self) -> IdentityPipelineRun:
        async with self._pool.acquire() as connection:
            acquired = cast(
                bool,
                await connection.fetchval(
                    "SELECT pg_try_advisory_lock($1)",
                    _AWS_COLLECTION_ADVISORY_LOCK,
                ),
            )
            if not acquired:
                raise CollectionAlreadyRunningError("an AWS collection is already running")
            try:
                return await self._pipeline.run()
            finally:
                await connection.fetchval(
                    "SELECT pg_advisory_unlock($1)",
                    _AWS_COLLECTION_ADVISORY_LOCK,
                )
