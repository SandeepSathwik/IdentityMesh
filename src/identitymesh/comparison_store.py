"""Read comparison inputs consistently from authoritative retained evidence."""

import asyncio
import json
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]
from pydantic import ValidationError

from identitymesh.collectors.aws_iam import COLLECTOR_VERSION, AwsRoleCollection, AwsRoleEvidence
from identitymesh.normalizers.aws_iam import normalize_aws_role
from identitymesh.principal_store import PrincipalSourceError, validate_principal_row
from identitymesh.snapshot_comparison import (
    MAX_COMPARISON_ROLES,
    ComparisonError,
    ComparisonResponse,
    ComparisonSource,
    compare_sources,
)


class SnapshotComparisonService:
    """Reject uncertain absence before exposing an observation difference."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def compare(
        self, base_id: UUID, target_id: UUID, *, limit: int = 50, cursor: UUID | None = None
    ) -> ComparisonResponse:
        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction(isolation="repeatable_read", readonly=True):
                    await connection.execute("SET LOCAL statement_timeout = '5s'")
                    base = await _load_source(connection, base_id)
                    target = (
                        base if base_id == target_id else await _load_source(connection, target_id)
                    )
            return compare_sources(base, target, limit=limit, cursor=cursor)
        except (ValidationError, PrincipalSourceError) as error:
            raise ComparisonError(
                "COMPARISON_SOURCE_INVALID", "Stored comparison evidence is inconsistent.", 503
            ) from error
        except (asyncpg.PostgresError, OSError, asyncio.TimeoutError) as error:
            raise ComparisonError(
                "COMPARISON_UNAVAILABLE", "Snapshot comparison is temporarily unavailable.", 503
            ) from error


async def _load_source(connection: asyncpg.Connection, snapshot_id: UUID) -> ComparisonSource:
    snapshot = await connection.fetchrow(
        "SELECT sequence_id, status, collector_version FROM snapshots WHERE snapshot_id = $1",
        snapshot_id,
    )
    if snapshot is None:
        raise ComparisonError("SNAPSHOT_NOT_FOUND", "A requested snapshot does not exist.", 404)
    if snapshot["status"] != "ready":
        raise ComparisonError("COMPARISON_NOT_READY", "Both snapshots must be ready.")
    if snapshot["collector_version"] != COLLECTOR_VERSION:
        raise ComparisonError(
            "COMPARISON_SCOPE_MISMATCH", "The snapshot collector version is not supported."
        )
    attempt = await connection.fetchrow(
        """
        SELECT schema_version, collected_at, status, account_id, collector_principal_arn,
               role_count, gap_count,
               (SELECT count(*) FROM principals WHERE snapshot_id = $1) AS principal_count,
               (SELECT count(*) FROM provider_evidence WHERE snapshot_id = $1) AS evidence_count,
               (SELECT count(*) FROM aws_iam_role_collection_gaps
                WHERE snapshot_id = $1) AS actual_gap_count
        FROM aws_iam_role_collection_attempts WHERE snapshot_id = $1
        """,
        snapshot_id,
    )
    if attempt is None or (
        attempt["status"] != "complete"
        or attempt["gap_count"] != 0
        or attempt["actual_gap_count"] != 0
        or attempt["role_count"] != attempt["principal_count"]
        or attempt["role_count"] != attempt["evidence_count"]
    ):
        raise ComparisonError(
            "COMPARISON_SOURCE_INVALID", "Complete comparison evidence is missing.", 503
        )
    if attempt["role_count"] > MAX_COMPARISON_ROLES:
        raise ComparisonError(
            "COMPARISON_TOO_LARGE", "A snapshot exceeds the comparison limit.", 413
        )
    rows = await connection.fetch(
        """
        SELECT p.principal_id, p.provider, p.principal_type, p.external_id, p.display_name,
               p.principal, p.schema_version AS principal_schema, e.evidence,
               e.source_id, e.object_type, e.provider_object_id, e.schema_version,
               e.collected_at, e.collector_version, e.collector_principal_id
        FROM principals p JOIN provider_evidence e
          ON p.snapshot_id = e.snapshot_id AND p.provider = e.provider
         AND p.evidence_source_id = e.source_id
        WHERE p.snapshot_id = $1 ORDER BY p.principal_id LIMIT $2
        """,
        snapshot_id,
        MAX_COMPARISON_ROLES + 1,
    )
    if len(rows) != attempt["role_count"]:
        raise ComparisonError("COMPARISON_SOURCE_INVALID", "Role evidence is missing.", 503)
    roles: list[AwsRoleEvidence] = []
    for row in rows:
        role = AwsRoleEvidence.model_validate_json(row["evidence"])
        principal = validate_principal_row(row, snapshot_id)
        if (
            principal != normalize_aws_role(role).principal
            or row["principal_schema"] != principal.schema_version
            or row["source_id"] != role.source_id
            or row["object_type"] != role.object_type
            or row["provider_object_id"] != role.role_id
            or row["schema_version"] != role.schema_version
            or row["collected_at"] != role.collected_at
            or row["collector_version"] != COLLECTOR_VERSION
            or role.collector_version != COLLECTOR_VERSION
            or row["collector_principal_id"] != role.collector_principal_arn
        ):
            raise ComparisonError(
                "COMPARISON_SOURCE_INVALID", "Role evidence and normalization disagree.", 503
            )
        roles.append(role)
    # Validate even complete-empty collections, which still need an account and caller.
    collection = AwsRoleCollection.model_validate_json(
        json.dumps(
            {
                "schema_version": attempt["schema_version"],
                "snapshot_id": str(snapshot_id),
                "collected_at": attempt["collected_at"].isoformat(),
                "status": attempt["status"],
                "account_id": attempt["account_id"],
                "collector_principal_arn": attempt["collector_principal_arn"],
                "roles": [role.model_dump(mode="json") for role in roles],
            }
        )
    )
    if collection.account_id is None:  # pragma: no cover - collection validator enforces this
        raise ComparisonError("COMPARISON_SOURCE_INVALID", "Account evidence is missing.", 503)
    return ComparisonSource(
        snapshot_id=snapshot_id,
        sequence_id=snapshot["sequence_id"],
        account_id=collection.account_id,
        collector_version=snapshot["collector_version"],
        collected_at=collection.collected_at,
        roles=collection.roles,
    )
