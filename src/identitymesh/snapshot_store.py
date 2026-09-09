"""PostgreSQL persistence for the snapshot lifecycle."""

import re
from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID, uuid4

import asyncpg  # type: ignore[import-untyped]

from identitymesh.snapshots import (
    PromotionResult,
    Snapshot,
    SnapshotNotFoundError,
    SnapshotStatus,
    require_transition,
)

_INSERT_SNAPSHOT = """
    INSERT INTO snapshots (snapshot_id, status, collector_version)
    VALUES ($1, $2, $3)
    RETURNING snapshot_id, sequence_id, status, collector_version, projection_version,
              failure_code, created_at, collected_at, projection_started_at, ready_at, failed_at
"""

_MARK_COLLECTED = """
    UPDATE snapshots
    SET status = $2, collected_at = transaction_timestamp(),
        projection_version = $3, failure_code = $4
    WHERE snapshot_id = $1
    RETURNING snapshot_id, sequence_id, status, collector_version, projection_version,
              failure_code, created_at, collected_at, projection_started_at, ready_at, failed_at
"""

_START_PROJECTION = """
    UPDATE snapshots
    SET status = $2, projection_started_at = transaction_timestamp(),
        projection_version = $3, failure_code = $4
    WHERE snapshot_id = $1
    RETURNING snapshot_id, sequence_id, status, collector_version, projection_version,
              failure_code, created_at, collected_at, projection_started_at, ready_at, failed_at
"""

_MARK_FAILED = """
    UPDATE snapshots
    SET status = $2, failed_at = transaction_timestamp(),
        projection_version = COALESCE($3, projection_version), failure_code = $4
    WHERE snapshot_id = $1
    RETURNING snapshot_id, sequence_id, status, collector_version, projection_version,
              failure_code, created_at, collected_at, projection_started_at, ready_at, failed_at
"""

_MARK_READY = """
    UPDATE snapshots
    SET status = $2, ready_at = transaction_timestamp()
    WHERE snapshot_id = $1
    RETURNING snapshot_id, sequence_id, status, collector_version, projection_version,
              failure_code, created_at, collected_at, projection_started_at, ready_at, failed_at
"""

_GET_ACTIVE = """
    SELECT snapshots.snapshot_id, snapshots.sequence_id, snapshots.status,
           snapshots.collector_version, snapshots.projection_version, snapshots.failure_code,
           snapshots.created_at, snapshots.collected_at, snapshots.projection_started_at,
           snapshots.ready_at, snapshots.failed_at
    FROM snapshots
    JOIN active_snapshot USING (snapshot_id)
    WHERE active_snapshot.singleton = TRUE AND snapshots.status = $1
"""


def _validate_identifier(value: str, field_name: str, max_length: int) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > max_length or not normalized.isprintable():
        raise ValueError(f"{field_name} must contain 1 to {max_length} printable characters")
    return normalized


def _validate_failure_code(value: str) -> str:
    normalized = value.strip()
    if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", normalized) is None:
        raise ValueError("failure_code must be an uppercase machine-readable reason code")
    return normalized


def _snapshot_from_record(record: Mapping[str, Any]) -> Snapshot:
    return Snapshot(
        snapshot_id=record["snapshot_id"],
        sequence_id=record["sequence_id"],
        status=SnapshotStatus(record["status"]),
        collector_version=record["collector_version"],
        projection_version=record["projection_version"],
        failure_code=record["failure_code"],
        created_at=record["created_at"],
        collected_at=record["collected_at"],
        projection_started_at=record["projection_started_at"],
        ready_at=record["ready_at"],
        failed_at=record["failed_at"],
    )


class SnapshotStore:
    """Perform serialized, fail-safe snapshot lifecycle changes."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def create(self, collector_version: str) -> Snapshot:
        collector_version = _validate_identifier(collector_version, "collector_version", 128)
        snapshot_id = uuid4()
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                _INSERT_SNAPSHOT,
                snapshot_id,
                SnapshotStatus.COLLECTING.value,
                collector_version,
            )
        if record is None:  # pragma: no cover - PostgreSQL INSERT RETURNING contract
            raise RuntimeError("PostgreSQL did not return the created snapshot")
        return _snapshot_from_record(record)

    async def mark_collected(self, snapshot_id: UUID) -> Snapshot:
        return await self._transition(snapshot_id, SnapshotStatus.COLLECTED)

    async def start_projection(self, snapshot_id: UUID, projection_version: str) -> Snapshot:
        projection_version = _validate_identifier(projection_version, "projection_version", 128)
        return await self._transition(
            snapshot_id,
            SnapshotStatus.PROJECTING,
            projection_version=projection_version,
        )

    async def mark_failed(self, snapshot_id: UUID, failure_code: str) -> Snapshot:
        failure_code = _validate_failure_code(failure_code)
        return await self._transition(
            snapshot_id,
            SnapshotStatus.FAILED,
            failure_code=failure_code,
        )

    async def complete_projection(self, snapshot_id: UUID) -> PromotionResult:
        """Mark a projection ready and atomically promote it when it is newest."""

        async with self._pool.acquire() as connection, connection.transaction():
            record = await self._locked_snapshot(connection, snapshot_id)
            current = SnapshotStatus(record["status"])
            require_transition(snapshot_id, current, SnapshotStatus.READY)

            active = await connection.fetchrow(
                """
                SELECT active.snapshot_id, snapshots.sequence_id
                FROM active_snapshot AS active
                LEFT JOIN snapshots ON snapshots.snapshot_id = active.snapshot_id
                WHERE active.singleton = TRUE
                FOR UPDATE OF active
                """
            )
            if active is None:  # pragma: no cover - protected by the seeded singleton row
                raise RuntimeError("active snapshot control row is missing")

            ready = await connection.fetchrow(
                _MARK_READY,
                snapshot_id,
                SnapshotStatus.READY.value,
            )
            if ready is None:  # pragma: no cover - row is locked above
                raise RuntimeError("snapshot disappeared during projection completion")

            active_sequence = active["sequence_id"]
            should_activate = active_sequence is None or ready["sequence_id"] > active_sequence
            if should_activate:
                await connection.execute(
                    """
                    UPDATE active_snapshot
                    SET snapshot_id = $1, activated_at = transaction_timestamp()
                    WHERE singleton = TRUE
                    """,
                    snapshot_id,
                )

        return PromotionResult(snapshot=_snapshot_from_record(ready), activated=should_activate)

    async def get_active(self) -> Snapshot | None:
        async with self._pool.acquire() as connection:
            record = await connection.fetchrow(
                _GET_ACTIVE,
                SnapshotStatus.READY.value,
            )
        return None if record is None else _snapshot_from_record(record)

    async def _transition(
        self,
        snapshot_id: UUID,
        target: SnapshotStatus,
        *,
        projection_version: str | None = None,
        failure_code: str | None = None,
    ) -> Snapshot:
        async with self._pool.acquire() as connection, connection.transaction():
            current_record = await self._locked_snapshot(connection, snapshot_id)
            current = SnapshotStatus(current_record["status"])
            require_transition(snapshot_id, current, target)

            query = {
                SnapshotStatus.COLLECTED: _MARK_COLLECTED,
                SnapshotStatus.PROJECTING: _START_PROJECTION,
                SnapshotStatus.FAILED: _MARK_FAILED,
            }[target]
            record = await connection.fetchrow(
                query,
                snapshot_id,
                target.value,
                projection_version,
                failure_code,
            )

        if record is None:  # pragma: no cover - row is locked above
            raise RuntimeError("snapshot disappeared during lifecycle transition")
        return _snapshot_from_record(record)

    @staticmethod
    async def _locked_snapshot(connection: Any, snapshot_id: UUID) -> Mapping[str, Any]:
        record = await connection.fetchrow(
            "SELECT snapshot_id, status FROM snapshots WHERE snapshot_id = $1 FOR UPDATE",
            snapshot_id,
        )
        if record is None:
            raise SnapshotNotFoundError(snapshot_id)
        return cast(Mapping[str, Any], record)
