import asyncio
import os
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest

from identitymesh.aws_evidence_store import (
    AwsIamRoleEvidenceStore,
    CollectionPersistenceConflictError,
    CollectorVersionMismatchError,
    SnapshotNotCollectingError,
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
from identitymesh.snapshots import SnapshotNotFoundError, SnapshotStatus

TEST_DATABASE_DSN = os.getenv("IDENTITYMESH_TEST_POSTGRES_DSN")
NOW = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
ACCOUNT_ID = "123456789012"
CALLER_ARN = f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/IdentityMeshCollector/run"


def _role(
    snapshot_id: UUID,
    name: str = "ApplicationRole",
    role_id: str = "AROAPP",
) -> AwsRoleEvidence:
    arn = f"arn:aws:iam::{ACCOUNT_ID}:role/application/{name}"
    return AwsRoleEvidence(
        snapshot_id=snapshot_id,
        source_id=arn,
        account_id=ACCOUNT_ID,
        collector_principal_arn=CALLER_ARN,
        collected_at=NOW,
        collector_version=COLLECTOR_VERSION,
        role_id=role_id,
        role_name=name,
        arn=arn,
        path="/application/",
        created_at=NOW,
        assume_role_policy_document={"Version": "2012-10-17", "Statement": []},
        description="Synthetic application role",
        max_session_duration=3600,
        tags={"Environment": "test"},
    )


def _gap() -> CollectionGap:
    return CollectionGap(
        operation="iam:ListRoles",
        reason_code=CollectionReasonCode.ACCESS_DENIED,
        retryable=False,
        message="AWS denied the required read-only operation.",
    )


def _collection(
    snapshot_id: UUID,
    *,
    status: CollectionStatus = CollectionStatus.COMPLETE,
    roles: tuple[AwsRoleEvidence, ...] | None = None,
    gaps: tuple[CollectionGap, ...] = (),
    account_id: str | None = ACCOUNT_ID,
    collector_principal_arn: str | None = CALLER_ARN,
) -> AwsRoleCollection:
    return AwsRoleCollection(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        status=status,
        account_id=account_id,
        collector_principal_arn=collector_principal_arn,
        roles=(_role(snapshot_id),) if roles is None else roles,
        gaps=gaps,
    )


@pytest.fixture
async def persistence() -> AsyncIterator[
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
async def test_rejects_unvalidated_collection_input() -> None:
    store = AwsIamRoleEvidenceStore(object())  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="validated AwsRoleCollection"):
        await store.persist({"status": "complete"})  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_complete_collection_persists_evidence_and_principal_atomically(
    persistence: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
) -> None:
    snapshots, evidence_store, pool = persistence
    snapshot = await snapshots.create(COLLECTOR_VERSION)

    result = await evidence_store.persist(_collection(snapshot.snapshot_id))

    assert result.created is True
    assert result.status is CollectionStatus.COMPLETE
    assert result.role_count == result.principal_count == 1
    async with pool.acquire() as connection:
        attempt = await connection.fetchrow(
            "SELECT status, role_count, gap_count FROM aws_iam_role_collection_attempts "
            "WHERE snapshot_id = $1",
            snapshot.snapshot_id,
        )
        evidence = await connection.fetchval(
            "SELECT evidence FROM provider_evidence WHERE snapshot_id = $1",
            snapshot.snapshot_id,
        )
        principal = await connection.fetchval(
            "SELECT principal FROM principals WHERE snapshot_id = $1",
            snapshot.snapshot_id,
        )
        snapshot_status = await connection.fetchval(
            "SELECT status FROM snapshots WHERE snapshot_id = $1",
            snapshot.snapshot_id,
        )
    assert dict(attempt) == {"status": "complete", "role_count": 1, "gap_count": 0}
    assert '"role_id": "AROAPP"' in evidence
    assert '"classification": "observed"' in principal
    assert snapshot_status == SnapshotStatus.COLLECTING.value
    assert await snapshots.get_active() is None


@pytest.mark.anyio
async def test_identical_retry_is_idempotent(
    persistence: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
) -> None:
    snapshots, evidence_store, pool = persistence
    snapshot = await snapshots.create(COLLECTOR_VERSION)
    collection = _collection(snapshot.snapshot_id)

    first = await evidence_store.persist(collection)
    second = await evidence_store.persist(collection)

    assert first.created is True
    assert second.created is False
    async with pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM provider_evidence WHERE snapshot_id = $1",
                snapshot.snapshot_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM principals WHERE snapshot_id = $1",
                snapshot.snapshot_id,
            )
            == 1
        )


@pytest.mark.anyio
async def test_concurrent_identical_retries_create_one_collection(
    persistence: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
) -> None:
    snapshots, evidence_store, pool = persistence
    snapshot = await snapshots.create(COLLECTOR_VERSION)
    collection = _collection(snapshot.snapshot_id)

    results = await asyncio.gather(
        evidence_store.persist(collection),
        evidence_store.persist(collection),
    )

    assert sorted(result.created for result in results) == [False, True]
    async with pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM aws_iam_role_collection_attempts WHERE snapshot_id = $1",
                snapshot.snapshot_id,
            )
            == 1
        )
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM principals WHERE snapshot_id = $1",
                snapshot.snapshot_id,
            )
            == 1
        )


@pytest.mark.anyio
async def test_conflicting_retry_preserves_original_collection(
    persistence: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
) -> None:
    snapshots, evidence_store, pool = persistence
    snapshot = await snapshots.create(COLLECTOR_VERSION)
    original = _collection(snapshot.snapshot_id)
    changed_role = _role(snapshot.snapshot_id).model_copy(update={"description": "Changed"})
    conflicting = _collection(snapshot.snapshot_id, roles=(changed_role,))
    await evidence_store.persist(original)

    with pytest.raises(CollectionPersistenceConflictError) as error:
        await evidence_store.persist(conflicting)

    assert error.value.reason_code == "COLLECTION_PERSISTENCE_CONFLICT"
    async with pool.acquire() as connection:
        stored = await connection.fetchval(
            "SELECT evidence FROM provider_evidence WHERE snapshot_id = $1",
            snapshot.snapshot_id,
        )
    assert '"description": "Synthetic application role"' in stored


@pytest.mark.anyio
async def test_partial_collection_is_persisted_without_activation(
    persistence: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
) -> None:
    snapshots, evidence_store, pool = persistence
    previous = await snapshots.create(COLLECTOR_VERSION)
    await snapshots.mark_collected(previous.snapshot_id)
    await snapshots.start_projection(previous.snapshot_id, "graph-v1")
    await snapshots.complete_projection(previous.snapshot_id)
    candidate = await snapshots.create(COLLECTOR_VERSION)
    collection = _collection(
        candidate.snapshot_id,
        status=CollectionStatus.PARTIAL,
        gaps=(_gap(),),
    )

    result = await evidence_store.persist(collection)

    assert result.status is CollectionStatus.PARTIAL
    assert result.gap_count == 1
    assert (await snapshots.get_active()).snapshot_id == previous.snapshot_id  # type: ignore[union-attr]
    async with pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM aws_iam_role_collection_gaps WHERE snapshot_id = $1",
                candidate.snapshot_id,
            )
            == 1
        )


@pytest.mark.anyio
@pytest.mark.parametrize("status", [CollectionStatus.COMPLETE, CollectionStatus.FAILED])
async def test_zero_role_collection_preserves_absence_semantics(
    persistence: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
    status: CollectionStatus,
) -> None:
    snapshots, evidence_store, pool = persistence
    snapshot = await snapshots.create(COLLECTOR_VERSION)
    failed = status is CollectionStatus.FAILED
    collection = _collection(
        snapshot.snapshot_id,
        status=status,
        roles=(),
        gaps=(_gap(),) if failed else (),
        account_id=None if failed else ACCOUNT_ID,
        collector_principal_arn=None if failed else CALLER_ARN,
    )

    result = await evidence_store.persist(collection)

    assert result.role_count == 0
    assert result.gap_count == (1 if failed else 0)
    async with pool.acquire() as connection:
        counts = await connection.fetchrow(
            "SELECT role_count, gap_count FROM aws_iam_role_collection_attempts "
            "WHERE snapshot_id = $1",
            snapshot.snapshot_id,
        )
    assert tuple(counts) == (0, 1 if failed else 0)


@pytest.mark.anyio
async def test_duplicate_provider_identity_rolls_back_every_write(
    persistence: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
) -> None:
    snapshots, evidence_store, pool = persistence
    snapshot = await snapshots.create(COLLECTOR_VERSION)
    roles = (
        _role(snapshot.snapshot_id, "First", role_id="ARODUPLICATE"),
        _role(snapshot.snapshot_id, "Second", role_id="ARODUPLICATE"),
    )

    with pytest.raises(CollectionPersistenceConflictError):
        await evidence_store.persist(_collection(snapshot.snapshot_id, roles=roles))

    async with pool.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM aws_iam_role_collection_attempts WHERE snapshot_id = $1",
                snapshot.snapshot_id,
            )
            == 0
        )
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM provider_evidence WHERE snapshot_id = $1",
                snapshot.snapshot_id,
            )
            == 0
        )
        assert (
            await connection.fetchval(
                "SELECT count(*) FROM principals WHERE snapshot_id = $1",
                snapshot.snapshot_id,
            )
            == 0
        )


@pytest.mark.anyio
async def test_rejects_missing_or_noncollecting_snapshot(
    persistence: tuple[SnapshotStore, AwsIamRoleEvidenceStore, asyncpg.Pool],
) -> None:
    snapshots, evidence_store, _ = persistence
    missing_id = uuid4()
    with pytest.raises(SnapshotNotFoundError):
        await evidence_store.persist(_collection(missing_id))

    snapshot = await snapshots.create(COLLECTOR_VERSION)
    await snapshots.mark_collected(snapshot.snapshot_id)
    with pytest.raises(SnapshotNotCollectingError) as error:
        await evidence_store.persist(_collection(snapshot.snapshot_id))
    assert error.value.reason_code == "SNAPSHOT_NOT_COLLECTING"

    wrong_collector = await snapshots.create("different-collector/1.0")
    with pytest.raises(CollectorVersionMismatchError) as version_error:
        await evidence_store.persist(_collection(wrong_collector.snapshot_id))
    assert version_error.value.reason_code == "COLLECTOR_VERSION_MISMATCH"
