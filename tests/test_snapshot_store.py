import asyncio
import os
from datetime import datetime, timezone
from uuid import uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest

from identitymesh.snapshot_store import (
    SnapshotStore,
    _snapshot_from_record,
    _validate_failure_code,
    _validate_identifier,
)
from identitymesh.snapshots import (
    InvalidSnapshotTransitionError,
    SnapshotNotFoundError,
    SnapshotStatus,
)

TEST_DATABASE_DSN = os.getenv("IDENTITYMESH_TEST_POSTGRES_DSN")


class _FakeAcquire:
    def __init__(self, connection: "_FakeConnection") -> None:
        self.connection = connection

    async def __aenter__(self) -> "_FakeConnection":
        return self.connection

    async def __aexit__(self, *_: object) -> None:
        return None


class _FakeConnection:
    def __init__(self, records: list[dict[str, object] | None]) -> None:
        self.records = records
        self.arguments: tuple[object, ...] | None = None

    async def fetchrow(self, _: str, *arguments: object) -> dict[str, object] | None:
        self.arguments = arguments
        return self.records.pop(0)


class _FakePool:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection

    def acquire(self) -> _FakeAcquire:
        return _FakeAcquire(self.connection)


@pytest.fixture
async def snapshot_store() -> SnapshotStore:
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
        yield SnapshotStore(pool)
    finally:
        await pool.close()


@pytest.mark.parametrize("value", ["", "   ", "x" * 129, "version\nvalue"])
def test_identifier_validation_rejects_empty_or_oversized_values(value: str) -> None:
    with pytest.raises(ValueError, match="collector_version"):
        _validate_identifier(value, "collector_version", 128)


def test_identifier_validation_trims_safe_values() -> None:
    assert _validate_identifier(" collector-v1 ", "collector_version", 128) == "collector-v1"


@pytest.mark.parametrize("value", ["", "collection_failed", "COLLECTION-FAILED", "FAILED\nNOW"])
def test_failure_code_validation_rejects_free_form_values(value: str) -> None:
    with pytest.raises(ValueError, match="machine-readable"):
        _validate_failure_code(value)


def test_failure_code_validation_accepts_stable_reason_code() -> None:
    assert _validate_failure_code(" COLLECTION_INCOMPLETE ") == "COLLECTION_INCOMPLETE"


def test_snapshot_record_is_mapped_to_typed_domain_model() -> None:
    now = datetime.now(timezone.utc)
    snapshot_id = uuid4()

    snapshot = _snapshot_from_record(
        {
            "snapshot_id": snapshot_id,
            "sequence_id": 7,
            "status": "projecting",
            "collector_version": "collector-v1",
            "projection_version": "graph-v1",
            "failure_code": None,
            "created_at": now,
            "collected_at": now,
            "projection_started_at": now,
            "ready_at": None,
            "failed_at": None,
        }
    )

    assert snapshot.snapshot_id == snapshot_id
    assert snapshot.sequence_id == 7
    assert snapshot.status is SnapshotStatus.PROJECTING


@pytest.mark.anyio
async def test_create_persists_a_normalized_collector_version() -> None:
    now = datetime.now(timezone.utc)
    snapshot_id = uuid4()
    connection = _FakeConnection(
        [
            {
                "snapshot_id": snapshot_id,
                "sequence_id": 1,
                "status": "collecting",
                "collector_version": "collector-v1",
                "projection_version": None,
                "failure_code": None,
                "created_at": now,
                "collected_at": None,
                "projection_started_at": None,
                "ready_at": None,
                "failed_at": None,
            }
        ]
    )
    store = SnapshotStore(_FakePool(connection))  # type: ignore[arg-type]

    snapshot = await store.create(" collector-v1 ")

    assert snapshot.snapshot_id == snapshot_id
    assert connection.arguments is not None
    assert connection.arguments[2] == "collector-v1"


@pytest.mark.anyio
async def test_get_active_returns_none_when_no_ready_snapshot_exists() -> None:
    store = SnapshotStore(_FakePool(_FakeConnection([None])))  # type: ignore[arg-type]

    assert await store.get_active() is None


@pytest.mark.anyio
async def test_complete_lifecycle_promotes_ready_snapshot(snapshot_store: SnapshotStore) -> None:
    collecting = await snapshot_store.create("collector-v1")
    collected = await snapshot_store.mark_collected(collecting.snapshot_id)
    projecting = await snapshot_store.start_projection(collected.snapshot_id, "graph-v1")
    result = await snapshot_store.complete_projection(projecting.snapshot_id)

    assert result.activated is True
    assert result.snapshot.status is SnapshotStatus.READY
    assert result.snapshot.ready_at is not None
    assert await snapshot_store.get_active() == result.snapshot


@pytest.mark.anyio
async def test_failure_preserves_previous_active_snapshot(snapshot_store: SnapshotStore) -> None:
    previous = await snapshot_store.create("collector-v1")
    await snapshot_store.mark_collected(previous.snapshot_id)
    await snapshot_store.start_projection(previous.snapshot_id, "graph-v1")
    previous_result = await snapshot_store.complete_projection(previous.snapshot_id)

    candidate = await snapshot_store.create("collector-v1")
    failed = await snapshot_store.mark_failed(candidate.snapshot_id, "COLLECTION_INCOMPLETE")

    assert failed.status is SnapshotStatus.FAILED
    assert failed.failure_code == "COLLECTION_INCOMPLETE"
    assert await snapshot_store.get_active() == previous_result.snapshot


@pytest.mark.anyio
async def test_older_snapshot_finishing_late_cannot_replace_newer_active_snapshot(
    snapshot_store: SnapshotStore,
) -> None:
    older = await snapshot_store.create("collector-v1")
    newer = await snapshot_store.create("collector-v1")
    for snapshot in (older, newer):
        await snapshot_store.mark_collected(snapshot.snapshot_id)
        await snapshot_store.start_projection(snapshot.snapshot_id, "graph-v1")

    newer_result = await snapshot_store.complete_projection(newer.snapshot_id)
    older_result = await snapshot_store.complete_projection(older.snapshot_id)

    assert newer_result.activated is True
    assert older_result.activated is False
    assert await snapshot_store.get_active() == newer_result.snapshot


@pytest.mark.anyio
async def test_concurrent_completion_keeps_newest_snapshot_active(
    snapshot_store: SnapshotStore,
) -> None:
    older = await snapshot_store.create("collector-v1")
    newer = await snapshot_store.create("collector-v1")
    for snapshot in (older, newer):
        await snapshot_store.mark_collected(snapshot.snapshot_id)
        await snapshot_store.start_projection(snapshot.snapshot_id, "graph-v1")

    older_result, newer_result = await asyncio.gather(
        snapshot_store.complete_projection(older.snapshot_id),
        snapshot_store.complete_projection(newer.snapshot_id),
    )

    assert older_result.snapshot.status is SnapshotStatus.READY
    assert newer_result.snapshot.status is SnapshotStatus.READY
    assert newer_result.activated is True
    assert await snapshot_store.get_active() == newer_result.snapshot


@pytest.mark.anyio
async def test_invalid_transition_is_rejected_without_changing_state(
    snapshot_store: SnapshotStore,
) -> None:
    snapshot = await snapshot_store.create("collector-v1")

    with pytest.raises(InvalidSnapshotTransitionError):
        await snapshot_store.start_projection(snapshot.snapshot_id, "graph-v1")

    assert await snapshot_store.get_active() is None


@pytest.mark.anyio
async def test_missing_snapshot_has_safe_reason_code(snapshot_store: SnapshotStore) -> None:
    with pytest.raises(SnapshotNotFoundError) as error:
        await snapshot_store.mark_collected(uuid4())

    assert error.value.reason_code == "SNAPSHOT_NOT_FOUND"
