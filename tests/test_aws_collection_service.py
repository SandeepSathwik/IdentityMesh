import os
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest

from identitymesh.aws_collection_service import (
    AwsCollectionRunError,
    AwsIamRoleCollectionService,
)
from identitymesh.aws_evidence_store import (
    AwsIamRoleEvidenceStore,
    CollectorVersionMismatchError,
)
from identitymesh.collectors.aws_iam import (
    COLLECTOR_VERSION,
    AwsRoleCollection,
    AwsRoleEvidence,
    CollectionGap,
    CollectionReasonCode,
    CollectionStatus,
)
from identitymesh.snapshot_store import SnapshotStore
from identitymesh.snapshots import SnapshotStatus

TEST_DATABASE_DSN = os.getenv("IDENTITYMESH_TEST_POSTGRES_DSN")
NOW = datetime(2026, 9, 16, 12, 0, tzinfo=timezone.utc)
ACCOUNT_ID = "123456789012"
CALLER_ARN = f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/IdentityMeshCollector/run"


def _role(snapshot_id: UUID) -> AwsRoleEvidence:
    arn = f"arn:aws:iam::{ACCOUNT_ID}:role/application/ApplicationRole"
    return AwsRoleEvidence(
        snapshot_id=snapshot_id,
        source_id=arn,
        account_id=ACCOUNT_ID,
        collector_principal_arn=CALLER_ARN,
        collected_at=NOW,
        collector_version=COLLECTOR_VERSION,
        role_id="AROAPP",
        role_name="ApplicationRole",
        arn=arn,
        path="/application/",
        created_at=NOW,
        assume_role_policy_document={"Version": "2012-10-17", "Statement": []},
    )


def _gap() -> CollectionGap:
    return CollectionGap(
        operation="iam:ListRoles",
        reason_code=CollectionReasonCode.ACCESS_DENIED,
        retryable=False,
        message="AWS denied the required read-only operation.",
    )


class FakeCollector:
    def __init__(
        self,
        status: CollectionStatus,
        *,
        error: Exception | None = None,
        wrong_snapshot: bool = False,
    ) -> None:
        self.status = status
        self.error = error
        self.wrong_snapshot = wrong_snapshot
        self.thread_id: int | None = None

    def collect(self, snapshot_id: UUID) -> AwsRoleCollection:
        self.thread_id = threading.get_ident()
        if self.error is not None:
            raise self.error
        if self.wrong_snapshot:
            snapshot_id = uuid4()
        incomplete = self.status is not CollectionStatus.COMPLETE
        failed = self.status is CollectionStatus.FAILED
        return AwsRoleCollection(
            snapshot_id=snapshot_id,
            collected_at=NOW,
            status=self.status,
            account_id=None if failed else ACCOUNT_ID,
            collector_principal_arn=None if failed else CALLER_ARN,
            roles=() if failed else (_role(snapshot_id),),
            gaps=(_gap(),) if incomplete else (),
        )


@pytest.mark.anyio
async def test_persistence_failure_is_reason_coded_and_snapshot_is_failed() -> None:
    snapshot_id = uuid4()
    snapshots = MagicMock()
    snapshots.create = AsyncMock(return_value=SimpleNamespace(snapshot_id=snapshot_id))
    snapshots.mark_failed = AsyncMock()
    evidence = MagicMock()
    evidence.persist_and_finalize = AsyncMock(
        side_effect=CollectorVersionMismatchError(snapshot_id)
    )
    service = AwsIamRoleCollectionService(
        snapshots,
        evidence,
        FakeCollector(CollectionStatus.COMPLETE),
    )

    with pytest.raises(AwsCollectionRunError) as captured:
        await service.run()

    assert captured.value.reason_code == "COLLECTOR_VERSION_MISMATCH"
    snapshots.mark_failed.assert_awaited_once_with(
        snapshot_id,
        "COLLECTOR_VERSION_MISMATCH",
    )


@pytest.mark.anyio
async def test_failure_to_record_terminal_state_is_explicit() -> None:
    snapshot_id = uuid4()
    snapshots = MagicMock()
    snapshots.create = AsyncMock(return_value=SimpleNamespace(snapshot_id=snapshot_id))
    snapshots.mark_failed = AsyncMock(side_effect=RuntimeError("database unavailable"))
    evidence = MagicMock()
    evidence.persist_and_finalize = AsyncMock(
        side_effect=CollectorVersionMismatchError(snapshot_id)
    )
    service = AwsIamRoleCollectionService(
        snapshots,
        evidence,
        FakeCollector(CollectionStatus.COMPLETE),
    )

    with pytest.raises(AwsCollectionRunError) as captured:
        await service.run()

    assert captured.value.reason_code == "AWS_COLLECTION_FAILURE_RECORDING_FAILED"
    assert "database unavailable" not in str(captured.value)


@pytest.fixture
async def service_dependencies() -> AsyncIterator[
    tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool]
]:
    if TEST_DATABASE_DSN is None:
        pytest.skip("IDENTITYMESH_TEST_POSTGRES_DSN is not configured")
    pool = await asyncpg.create_pool(TEST_DATABASE_DSN, min_size=1, max_size=4)
    try:
        async with pool.acquire() as connection:
            await connection.execute("TRUNCATE snapshots CASCADE")
            await connection.execute(
                "INSERT INTO active_snapshot (singleton) VALUES (TRUE) "
                "ON CONFLICT (singleton) DO UPDATE "
                "SET snapshot_id = NULL, activated_at = NULL"
            )
        yield SnapshotStore(pool), AwsIamRoleEvidenceStore(pool), pool
    finally:
        await pool.close()


@pytest.mark.anyio
async def test_complete_run_collects_off_loop_and_finishes_collected(
    service_dependencies: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
) -> None:
    snapshots, evidence, pool = service_dependencies
    collector = FakeCollector(CollectionStatus.COMPLETE)
    event_loop_thread = threading.get_ident()
    service = AwsIamRoleCollectionService(snapshots, evidence, collector)

    result = await service.run()

    assert result.collection_status is CollectionStatus.COMPLETE
    assert result.snapshot_status is SnapshotStatus.COLLECTED
    assert result.failure_code is None
    assert result.role_count == 1
    assert collector.thread_id is not None
    assert collector.thread_id != event_loop_thread
    async with pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM provider_evidence WHERE snapshot_id = $1",
                result.snapshot_id,
            )
            == 1
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("collection_status", "failure_code", "expected_roles"),
    [
        (CollectionStatus.PARTIAL, "AWS_COLLECTION_PARTIAL", 1),
        (CollectionStatus.FAILED, "AWS_COLLECTION_FAILED", 0),
    ],
)
async def test_incomplete_run_is_terminal_and_never_replaces_active_snapshot(
    service_dependencies: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
    collection_status: CollectionStatus,
    failure_code: str,
    expected_roles: int,
) -> None:
    snapshots, evidence, pool = service_dependencies
    previous = await snapshots.create(COLLECTOR_VERSION)
    await snapshots.mark_collected(previous.snapshot_id)
    await snapshots.start_projection(previous.snapshot_id, "graph-v1")
    previous_result = await snapshots.complete_projection(previous.snapshot_id)
    service = AwsIamRoleCollectionService(
        snapshots,
        evidence,
        FakeCollector(collection_status),
    )

    result = await service.run()

    assert result.snapshot_status is SnapshotStatus.FAILED
    assert result.failure_code == failure_code
    assert result.role_count == expected_roles
    assert await snapshots.get_active() == previous_result.snapshot
    async with pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM aws_iam_role_collection_gaps WHERE snapshot_id = $1",
                result.snapshot_id,
            )
            == 1
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "collector",
    [
        FakeCollector(CollectionStatus.COMPLETE, error=RuntimeError("private provider detail")),
        FakeCollector(CollectionStatus.COMPLETE, wrong_snapshot=True),
    ],
)
async def test_unexpected_collector_failure_is_safe_and_terminal(
    service_dependencies: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
    collector: FakeCollector,
) -> None:
    snapshots, evidence, pool = service_dependencies
    service = AwsIamRoleCollectionService(snapshots, evidence, collector)

    with pytest.raises(AwsCollectionRunError) as captured:
        await service.run()

    assert captured.value.reason_code == "AWS_COLLECTION_INTERNAL_ERROR"
    assert "private provider detail" not in str(captured.value)
    async with pool.acquire() as connection:
        state = await connection.fetchrow(
            "SELECT status, failure_code FROM snapshots WHERE snapshot_id = $1",
            captured.value.snapshot_id,
        )
        attempts = await connection.fetchval(
            "SELECT count(*) FROM aws_iam_role_collection_attempts WHERE snapshot_id = $1",
            captured.value.snapshot_id,
        )
    assert tuple(state) == (SnapshotStatus.FAILED.value, "AWS_COLLECTION_INTERNAL_ERROR")
    assert attempts == 0
