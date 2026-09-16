"""Application service for one fail-safe AWS IAM role collection run."""

import asyncio
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from identitymesh.aws_evidence_store import (
    AwsEvidenceStoreError,
    AwsIamRoleEvidenceStore,
)
from identitymesh.collectors.aws_iam import (
    COLLECTOR_VERSION,
    AwsRoleCollection,
    CollectionStatus,
)
from identitymesh.snapshot_store import SnapshotStore
from identitymesh.snapshots import SnapshotStatus


class AwsRoleCollector(Protocol):
    """Collector contract required by the orchestration service."""

    def collect(self, snapshot_id: UUID) -> AwsRoleCollection: ...


class AwsCollectionRunError(Exception):
    """Safe failure returned when an AWS collection run cannot complete."""

    def __init__(self, snapshot_id: UUID, reason_code: str) -> None:
        self.snapshot_id = snapshot_id
        self.reason_code = reason_code
        super().__init__(f"AWS role collection {snapshot_id} failed with {reason_code}")


@dataclass(frozen=True, slots=True)
class AwsCollectionRun:
    """Terminal outcome of a persisted AWS IAM role collection run."""

    snapshot_id: UUID
    collection_status: CollectionStatus
    snapshot_status: SnapshotStatus
    failure_code: str | None
    role_count: int
    gap_count: int


class AwsIamRoleCollectionService:
    """Create, collect, persist, and finalize one AWS IAM role snapshot."""

    def __init__(
        self,
        snapshots: SnapshotStore,
        evidence: AwsIamRoleEvidenceStore,
        collector: AwsRoleCollector,
    ) -> None:
        self._snapshots = snapshots
        self._evidence = evidence
        self._collector = collector

    async def run(self) -> AwsCollectionRun:
        snapshot = await self._snapshots.create(COLLECTOR_VERSION)
        try:
            collection = await asyncio.to_thread(self._collector.collect, snapshot.snapshot_id)
            if collection.snapshot_id != snapshot.snapshot_id:
                raise ValueError("collector returned evidence for a different snapshot")
            persisted = await self._evidence.persist_and_finalize(collection)
        except Exception as error:
            reason_code = _failure_code(error)
            try:
                await self._snapshots.mark_failed(snapshot.snapshot_id, reason_code)
            except Exception as recording_error:
                raise AwsCollectionRunError(
                    snapshot.snapshot_id,
                    "AWS_COLLECTION_FAILURE_RECORDING_FAILED",
                ) from recording_error
            raise AwsCollectionRunError(snapshot.snapshot_id, reason_code) from error

        return AwsCollectionRun(
            snapshot_id=snapshot.snapshot_id,
            collection_status=collection.status,
            snapshot_status=persisted.snapshot_status,
            failure_code=persisted.failure_code,
            role_count=persisted.role_count,
            gap_count=persisted.gap_count,
        )


def _failure_code(error: Exception) -> str:
    if isinstance(error, AwsEvidenceStoreError):
        return error.reason_code
    return "AWS_COLLECTION_INTERNAL_ERROR"
