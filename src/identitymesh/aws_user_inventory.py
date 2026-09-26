"""Collection and validated snapshot-specific reads for IAM user observations."""

import asyncio
import json
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from identitymesh.aws_collection_service import AwsCollectionRunError, _failure_code
from identitymesh.aws_evidence_store import _final_state
from identitymesh.aws_user_evidence_store import AwsIamUserEvidenceStore
from identitymesh.collectors.aws_iam import CollectionGap
from identitymesh.collectors.aws_iam_users import (
    COLLECTOR_VERSION,
    MAX_USERS,
    AwsUserCollection,
    AwsUserEvidence,
)
from identitymesh.identity_pipeline import (
    _AWS_COLLECTION_ADVISORY_LOCK,
    CollectionAlreadyRunningError,
)
from identitymesh.normalizers.aws_iam_users import normalize_aws_user
from identitymesh.principal_store import PrincipalSourceError, validate_principal_row
from identitymesh.principals import Principal
from identitymesh.snapshot_store import SnapshotStore


class UserCollector(Protocol):
    def collect(self, snapshot_id: UUID) -> AwsUserCollection: ...


class UserCollectionRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.user-collection-run/v1"] = (
        "identitymesh.user-collection-run/v1"
    )
    snapshot_id: UUID
    collection_status: str
    snapshot_status: str
    failure_code: str | None
    user_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    principal_count: int = Field(ge=0)
    activated: Literal[False] = False


class UserInventoryPage(BaseModel):
    """Safe principal references with completeness explicit even for empty results."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.user-inventory-page/v1"] = (
        "identitymesh.user-inventory-page/v1"
    )
    snapshot_id: UUID
    collection_status: str
    snapshot_status: str
    account_id: str | None
    collected_at: datetime
    items: tuple[Principal, ...]
    gaps: tuple[CollectionGap, ...]
    next_cursor: UUID | None
    total_count: int = Field(ge=0)
    uncollected_fields: tuple[Literal["tags"], Literal["permissions_boundary"]] = (
        "tags",
        "permissions_boundary",
    )


class UserInventoryError(Exception):
    def __init__(self, reason_code: str, message: str, status_code: int = 503) -> None:
        self.reason_code = reason_code
        self.status_code = status_code
        super().__init__(message)


class AwsUserInventoryService:
    """Retain user observations separately from the role-only active graph."""

    def __init__(self, pool: asyncpg.Pool, collector: UserCollector) -> None:
        self._pool = pool
        self._collector = collector
        self._snapshots = SnapshotStore(pool)
        self._evidence = AwsIamUserEvidenceStore(pool)

    async def run(self) -> UserCollectionRun:
        # Share the role pipeline's lock: IAM collection is serialized across both routes.
        async with self._pool.acquire() as connection:
            acquired = await connection.fetchval(
                "SELECT pg_try_advisory_lock($1)", _AWS_COLLECTION_ADVISORY_LOCK
            )
            if not acquired:
                raise CollectionAlreadyRunningError("an AWS collection is already running")
            try:
                return await self._collect()
            finally:
                await connection.fetchval(
                    "SELECT pg_advisory_unlock($1)", _AWS_COLLECTION_ADVISORY_LOCK
                )

    async def _collect(self) -> UserCollectionRun:
        snapshot = await self._snapshots.create(COLLECTOR_VERSION)
        try:
            collection = await asyncio.to_thread(self._collector.collect, snapshot.snapshot_id)
            if not isinstance(collection, AwsUserCollection):
                raise TypeError("collector returned unvalidated user evidence")
            if collection.snapshot_id != snapshot.snapshot_id:
                raise ValueError("collector returned evidence for a different snapshot")
            persisted = await self._evidence.persist_and_finalize(collection)
        except Exception as error:
            reason_code = _failure_code(error)
            try:
                await self._snapshots.mark_failed(snapshot.snapshot_id, reason_code)
            except Exception as recording_error:
                raise AwsCollectionRunError(
                    snapshot.snapshot_id, "AWS_COLLECTION_FAILURE_RECORDING_FAILED"
                ) from recording_error
            raise AwsCollectionRunError(snapshot.snapshot_id, reason_code) from error
        return UserCollectionRun(
            snapshot_id=snapshot.snapshot_id,
            collection_status=persisted.status.value,
            snapshot_status=persisted.snapshot_status.value,
            failure_code=persisted.failure_code,
            user_count=persisted.user_count,
            gap_count=persisted.gap_count,
            principal_count=persisted.principal_count,
        )

    async def users(
        self, snapshot_id: UUID, *, limit: int = 50, cursor: UUID | None = None
    ) -> UserInventoryPage:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction(isolation="repeatable_read", readonly=True):
                    await connection.execute("SET LOCAL statement_timeout = '5s'")
                    collection, principals, snapshot_status = await _load_users(
                        connection, snapshot_id
                    )
        except (ValidationError, PrincipalSourceError, ValueError, TypeError, KeyError) as error:
            raise UserInventoryError(
                "USER_INVENTORY_SOURCE_INVALID", "Stored user evidence is inconsistent."
            ) from error
        except (asyncpg.PostgresError, OSError, asyncio.TimeoutError) as error:
            raise UserInventoryError(
                "USER_INVENTORY_UNAVAILABLE", "User inventory is temporarily unavailable."
            ) from error
        remaining = tuple(p for p in principals if cursor is None or p.principal_id > cursor)
        items = remaining[:limit]
        return UserInventoryPage(
            snapshot_id=snapshot_id,
            collection_status=collection.status.value,
            snapshot_status=snapshot_status,
            account_id=collection.account_id,
            collected_at=collection.collected_at,
            items=items,
            gaps=collection.gaps,
            total_count=len(principals),
            next_cursor=items[-1].principal_id if len(remaining) > limit else None,
        )


async def _load_users(
    connection: asyncpg.Connection, snapshot_id: UUID
) -> tuple[AwsUserCollection, tuple[Principal, ...], str]:
    snapshot = await connection.fetchrow(
        "SELECT status, collector_version, failure_code FROM snapshots WHERE snapshot_id = $1",
        snapshot_id,
    )
    if snapshot is None:
        raise UserInventoryError(
            "SNAPSHOT_NOT_FOUND", "The requested snapshot does not exist.", 404
        )
    if snapshot["collector_version"] != COLLECTOR_VERSION:
        raise UserInventoryError("USER_INVENTORY_SCOPE_MISMATCH", "Select a user snapshot.", 409)
    if snapshot["status"] not in {"collected", "failed"}:
        raise UserInventoryError(
            "USER_INVENTORY_NOT_COLLECTED", "User collection is unfinished.", 409
        )
    attempt = await connection.fetchrow(
        """
        SELECT schema_version, collected_at, status, account_id, collector_principal_arn,
               user_count, gap_count,
               (SELECT count(*) FROM principals WHERE snapshot_id = $1) AS principal_count,
               (SELECT count(*) FROM provider_evidence WHERE snapshot_id = $1) AS evidence_count
        FROM aws_iam_user_collection_attempts WHERE snapshot_id = $1
        """,
        snapshot_id,
    )
    if attempt is None:
        raise UserInventoryError(
            "USER_INVENTORY_SOURCE_INVALID", "User collection evidence is missing."
        )
    if not 0 <= attempt["user_count"] <= MAX_USERS or (
        attempt["principal_count"] != attempt["user_count"]
        or attempt["evidence_count"] != attempt["user_count"]
    ):
        raise ValueError("user evidence counts disagree")
    gaps = await connection.fetch(
        "SELECT operation, reason_code, retryable, message FROM aws_iam_user_collection_gaps "
        "WHERE snapshot_id = $1 ORDER BY gap_id",
        snapshot_id,
    )
    if len(gaps) != attempt["gap_count"]:
        raise ValueError("user gap count disagrees")
    rows = await connection.fetch(
        """
        SELECT p.principal_id, p.provider, p.principal_type, p.external_id, p.display_name,
               p.principal, p.schema_version AS principal_schema, e.evidence, e.source_id,
               e.object_type, e.provider_object_id, e.schema_version, e.collected_at,
               e.collector_version, e.collector_principal_id
        FROM principals p JOIN provider_evidence e
          ON p.snapshot_id = e.snapshot_id AND p.provider = e.provider
         AND p.evidence_source_id = e.source_id
        WHERE p.snapshot_id = $1 ORDER BY p.principal_id LIMIT $2
        """,
        snapshot_id,
        MAX_USERS + 1,
    )
    if len(rows) != attempt["user_count"]:
        raise ValueError("user evidence rows are missing")
    users: list[AwsUserEvidence] = []
    principals: list[Principal] = []
    for row in rows:
        user = AwsUserEvidence.model_validate_json(row["evidence"])
        principal = validate_principal_row(row, snapshot_id)
        if (
            principal != normalize_aws_user(user).principal
            or row["principal_schema"] != principal.schema_version
            or row["source_id"] != user.source_id
            or row["object_type"] != user.object_type
            or row["provider_object_id"] != user.user_id
            or row["schema_version"] != user.schema_version
            or row["collected_at"] != user.collected_at
            or row["collector_version"] != user.collector_version
            or row["collector_principal_id"] != user.collector_principal_arn
        ):
            raise ValueError("user evidence and principal disagree")
        users.append(user)
        principals.append(principal)
    collection = AwsUserCollection.model_validate_json(
        json.dumps(
            {
                "schema_version": attempt["schema_version"],
                "snapshot_id": str(snapshot_id),
                "collected_at": attempt["collected_at"].isoformat(),
                "status": attempt["status"],
                "account_id": attempt["account_id"],
                "collector_principal_arn": attempt["collector_principal_arn"],
                "users": [user.model_dump(mode="json") for user in users],
                "gaps": [dict(gap) for gap in gaps],
            }
        )
    )
    expected_status, failure_code = _final_state(collection.status)
    if snapshot["status"] != expected_status.value or snapshot["failure_code"] != failure_code:
        raise ValueError("snapshot lifecycle disagrees with user collection")
    return collection, tuple(principals), expected_status.value
