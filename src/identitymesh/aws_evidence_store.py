"""Transactional PostgreSQL persistence for AWS IAM role evidence."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from identitymesh.collectors.aws_iam import COLLECTOR_VERSION, AwsRoleCollection, CollectionStatus
from identitymesh.normalizers.aws_iam import normalize_aws_role
from identitymesh.snapshots import SnapshotNotFoundError, SnapshotStatus


class AwsEvidenceStoreError(Exception):
    """Base class for safe, reason-coded evidence persistence errors."""

    reason_code = "AWS_EVIDENCE_STORE_ERROR"


class SnapshotNotCollectingError(AwsEvidenceStoreError):
    """Raised when evidence is written outside the collection phase."""

    reason_code = "SNAPSHOT_NOT_COLLECTING"

    def __init__(self, snapshot_id: UUID, status: SnapshotStatus) -> None:
        self.snapshot_id = snapshot_id
        self.status = status
        super().__init__(f"snapshot {snapshot_id} is {status.value}, not collecting")


class CollectionPersistenceConflictError(AwsEvidenceStoreError):
    """Raised when a snapshot is reused for different or inconsistent evidence."""

    reason_code = "COLLECTION_PERSISTENCE_CONFLICT"

    def __init__(self, snapshot_id: UUID) -> None:
        self.snapshot_id = snapshot_id
        super().__init__(f"snapshot {snapshot_id} already contains different collection data")


class CollectorVersionMismatchError(AwsEvidenceStoreError):
    """Raised when a snapshot belongs to a different collector contract."""

    reason_code = "COLLECTOR_VERSION_MISMATCH"

    def __init__(self, snapshot_id: UUID) -> None:
        self.snapshot_id = snapshot_id
        super().__init__(f"snapshot {snapshot_id} does not match the AWS role collector version")


@dataclass(frozen=True, slots=True)
class PersistedAwsRoleCollection:
    """Outcome of an atomic collection persistence attempt."""

    snapshot_id: UUID
    status: CollectionStatus
    role_count: int
    gap_count: int
    principal_count: int
    created: bool


def _canonical_collection(collection: AwsRoleCollection) -> str:
    return json.dumps(
        collection.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _collection_digest(collection: AwsRoleCollection) -> str:
    return hashlib.sha256(_canonical_collection(collection).encode("utf-8")).hexdigest()


class AwsIamRoleEvidenceStore:
    """Persist one immutable AWS role collection per authoritative snapshot."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def persist(self, collection: AwsRoleCollection) -> PersistedAwsRoleCollection:
        if not isinstance(collection, AwsRoleCollection):
            raise TypeError("collection must be validated AwsRoleCollection")

        normalized = tuple(normalize_aws_role(role).principal for role in collection.roles)
        digest = _collection_digest(collection)

        try:
            async with self._pool.acquire() as connection, connection.transaction():
                snapshot = await connection.fetchrow(
                    "SELECT status, collector_version FROM snapshots "
                    "WHERE snapshot_id = $1 FOR UPDATE",
                    collection.snapshot_id,
                )
                if snapshot is None:
                    raise SnapshotNotFoundError(collection.snapshot_id)

                snapshot_status = SnapshotStatus(snapshot["status"])
                if snapshot_status is not SnapshotStatus.COLLECTING:
                    raise SnapshotNotCollectingError(collection.snapshot_id, snapshot_status)
                if snapshot["collector_version"] != COLLECTOR_VERSION:
                    raise CollectorVersionMismatchError(collection.snapshot_id)

                inserted = await connection.fetchval(
                    """
                    INSERT INTO aws_iam_role_collection_attempts (
                        snapshot_id, schema_version, collected_at, status, account_id,
                        collector_principal_arn, role_count, gap_count, content_sha256
                    )
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    ON CONFLICT (snapshot_id) DO NOTHING
                    RETURNING TRUE
                    """,
                    collection.snapshot_id,
                    collection.schema_version,
                    collection.collected_at,
                    collection.status.value,
                    collection.account_id,
                    collection.collector_principal_arn,
                    len(collection.roles),
                    len(collection.gaps),
                    digest,
                )
                if inserted is None:
                    existing_digest = await connection.fetchval(
                        """
                        SELECT content_sha256
                        FROM aws_iam_role_collection_attempts
                        WHERE snapshot_id = $1
                        """,
                        collection.snapshot_id,
                    )
                    if existing_digest != digest:
                        raise CollectionPersistenceConflictError(collection.snapshot_id)
                    return _result(collection, created=False)

                if collection.gaps:
                    await connection.executemany(
                        """
                        INSERT INTO aws_iam_role_collection_gaps (
                            snapshot_id, operation, reason_code, retryable, message
                        )
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        [
                            (
                                collection.snapshot_id,
                                gap.operation,
                                gap.reason_code.value,
                                gap.retryable,
                                gap.message,
                            )
                            for gap in collection.gaps
                        ],
                    )

                for role, principal in zip(collection.roles, normalized, strict=True):
                    await connection.execute(
                        """
                        INSERT INTO provider_evidence (
                            snapshot_id, provider, object_type, source_id, schema_version,
                            provider_object_id, collected_at, collector_version,
                            collector_principal_id, evidence
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                        """,
                        collection.snapshot_id,
                        role.provider,
                        role.object_type,
                        role.source_id,
                        role.schema_version,
                        role.role_id,
                        role.collected_at,
                        role.collector_version,
                        role.collector_principal_arn,
                        role.model_dump_json(),
                    )
                    await connection.execute(
                        """
                        INSERT INTO principals (
                            snapshot_id, principal_id, schema_version, provider,
                            principal_type, external_id, display_name,
                            evidence_source_id, principal
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                        """,
                        collection.snapshot_id,
                        principal.principal_id,
                        principal.schema_version,
                        principal.provider,
                        principal.principal_type.value,
                        principal.external_id,
                        principal.display_name,
                        principal.provenance.source_object_id,
                        principal.model_dump_json(),
                    )
        except asyncpg.IntegrityConstraintViolationError as error:
            raise CollectionPersistenceConflictError(collection.snapshot_id) from error

        return _result(collection, created=True)


def _result(collection: AwsRoleCollection, *, created: bool) -> PersistedAwsRoleCollection:
    return PersistedAwsRoleCollection(
        snapshot_id=collection.snapshot_id,
        status=collection.status,
        role_count=len(collection.roles),
        gap_count=len(collection.gaps),
        principal_count=len(collection.roles),
        created=created,
    )
