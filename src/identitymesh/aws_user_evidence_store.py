"""Atomic persistence of independently scoped IAM user observations."""

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]

from identitymesh.aws_evidence_store import (
    CollectionPersistenceConflictError,
    CollectorVersionMismatchError,
    SnapshotNotCollectingError,
    _final_state,
    _finalize_snapshot,
    _locked_snapshot,
)
from identitymesh.collectors.aws_iam import CollectionStatus
from identitymesh.collectors.aws_iam_users import COLLECTOR_VERSION, AwsUserCollection
from identitymesh.normalizers.aws_iam_users import normalize_aws_user
from identitymesh.snapshots import SnapshotStatus


@dataclass(frozen=True, slots=True)
class PersistedAwsUserCollection:
    snapshot_id: UUID
    status: CollectionStatus
    user_count: int
    gap_count: int
    principal_count: int
    created: bool
    snapshot_status: SnapshotStatus
    failure_code: str | None


class AwsIamUserEvidenceStore:
    """Store and finalize user evidence without projecting or activating its snapshot."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def persist_and_finalize(
        self, collection: AwsUserCollection
    ) -> PersistedAwsUserCollection:
        if not isinstance(collection, AwsUserCollection):
            raise TypeError("collection must be validated AwsUserCollection")
        # Revalidate nested objects as well: model_copy/model_construct can bypass validators.
        collection = AwsUserCollection.model_validate_json(collection.model_dump_json())
        normalized = tuple(normalize_aws_user(user).principal for user in collection.users)
        canonical = json.dumps(
            collection.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        digest = hashlib.sha256(canonical.encode()).hexdigest()
        target_status, failure_code = _final_state(collection.status)
        created = False
        try:
            async with self._pool.acquire() as connection, connection.transaction():
                snapshot = await _locked_snapshot(connection, collection.snapshot_id)
                if snapshot["collector_version"] != COLLECTOR_VERSION:
                    raise CollectorVersionMismatchError(collection.snapshot_id)
                current_status = SnapshotStatus(snapshot["status"])
                if current_status is target_status:
                    existing = await connection.fetchval(
                        "SELECT content_sha256 FROM aws_iam_user_collection_attempts "
                        "WHERE snapshot_id = $1",
                        collection.snapshot_id,
                    )
                    if existing != digest or snapshot["failure_code"] != failure_code:
                        raise CollectionPersistenceConflictError(collection.snapshot_id)
                elif current_status is not SnapshotStatus.COLLECTING:
                    raise SnapshotNotCollectingError(collection.snapshot_id, current_status)
                else:
                    await connection.execute(
                        """
                        INSERT INTO aws_iam_user_collection_attempts (
                            snapshot_id, schema_version, collected_at, status, account_id,
                            collector_principal_arn, user_count, gap_count, content_sha256
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                        """,
                        collection.snapshot_id,
                        collection.schema_version,
                        collection.collected_at,
                        collection.status.value,
                        collection.account_id,
                        collection.collector_principal_arn,
                        len(collection.users),
                        len(collection.gaps),
                        digest,
                    )
                    if collection.gaps:
                        await connection.executemany(
                            """
                            INSERT INTO aws_iam_user_collection_gaps (
                                snapshot_id, operation, reason_code, retryable, message
                            ) VALUES ($1, $2, $3, $4, $5)
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
                    for user, principal in zip(collection.users, normalized, strict=True):
                        await connection.execute(
                            """
                            INSERT INTO provider_evidence (
                                snapshot_id, provider, object_type, source_id, schema_version,
                                provider_object_id, collected_at, collector_version,
                                collector_principal_id, evidence
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
                            """,
                            collection.snapshot_id,
                            user.provider,
                            user.object_type,
                            user.source_id,
                            user.schema_version,
                            user.user_id,
                            user.collected_at,
                            user.collector_version,
                            user.collector_principal_arn,
                            user.model_dump_json(),
                        )
                        await connection.execute(
                            """
                            INSERT INTO principals (
                                snapshot_id, principal_id, schema_version, provider,
                                principal_type, external_id, display_name, evidence_source_id,
                                principal
                            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
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
                    await _finalize_snapshot(
                        connection, collection.snapshot_id, target_status, failure_code
                    )
                    created = True
        except asyncpg.IntegrityConstraintViolationError as error:
            raise CollectionPersistenceConflictError(collection.snapshot_id) from error
        return PersistedAwsUserCollection(
            snapshot_id=collection.snapshot_id,
            status=collection.status,
            user_count=len(collection.users),
            gap_count=len(collection.gaps),
            principal_count=len(normalized),
            created=created,
            snapshot_status=target_status,
            failure_code=failure_code,
        )
