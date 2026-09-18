"""Versioned Neo4j projection for normalized principal snapshots."""

import hashlib
import json
from datetime import datetime
from typing import Any, Literal, cast
from uuid import UUID

from neo4j import AsyncDriver, AsyncManagedTransaction
from neo4j.exceptions import DriverError, Neo4jError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from identitymesh.principals import Principal, PrincipalType

PROJECTION_VERSION = "principal-graph/0.1"

_PRINCIPAL_CONSTRAINT = """
CREATE CONSTRAINT identitymesh_principal_projection_key IF NOT EXISTS
FOR (node:Principal) REQUIRE node.projection_key IS UNIQUE
"""

_MARKER_CONSTRAINT = """
CREATE CONSTRAINT identitymesh_projection_marker_key IF NOT EXISTS
FOR (marker:IdentityMeshProjection) REQUIRE marker.projection_key IS UNIQUE
"""


class GraphProjectionError(Exception):
    """Base class for safe, reason-coded projection failures."""

    reason_code = "GRAPH_PROJECTION_FAILED"


class GraphProjectionVerificationError(GraphProjectionError):
    """Raised when Neo4j does not exactly match the expected projection."""

    reason_code = "GRAPH_PROJECTION_VERIFICATION_FAILED"


class ProjectedPrincipal(BaseModel):
    """Safe graph/API representation of one observed normalized principal."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.graph-principal/v1"] = "identitymesh.graph-principal/v1"
    snapshot_id: UUID
    projection_version: str = Field(min_length=1, max_length=128)
    principal_id: UUID
    external_id: str = Field(min_length=1, max_length=2048)
    provider: str = Field(min_length=1, max_length=64)
    principal_type: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=256)
    status: str | None = Field(default=None, min_length=1, max_length=64)
    created_at: datetime | None = None
    discovered_at: datetime
    source_system: str = Field(min_length=1, max_length=64)
    source_object_type: str = Field(min_length=1, max_length=64)
    source_object_id: str = Field(min_length=1, max_length=2048)
    collected_at: datetime
    collector_version: str = Field(min_length=1, max_length=128)
    collector_principal_id: str = Field(min_length=1, max_length=2048)
    evidence_schema_version: str = Field(min_length=1, max_length=128)
    evidence_classification: str = Field(min_length=1, max_length=64)


class ProjectionResult(BaseModel):
    """Verified output of one Neo4j projection write."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot_id: UUID
    projection_version: str
    principal_count: int = Field(ge=0)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def project_principal(principal: Principal) -> ProjectedPrincipal:
    """Flatten observed principal data into safe graph properties."""

    if principal.principal_type is not PrincipalType.CLOUD_ROLE:
        raise GraphProjectionError("the current projection supports only AWS role principals")
    provenance = principal.provenance
    return ProjectedPrincipal(
        snapshot_id=provenance.snapshot_id,
        projection_version=PROJECTION_VERSION,
        principal_id=principal.principal_id,
        external_id=principal.external_id,
        provider=principal.provider,
        principal_type=principal.principal_type.value,
        display_name=principal.display_name,
        status=principal.status,
        created_at=principal.created_at,
        discovered_at=principal.discovered_at,
        source_system=provenance.source_system,
        source_object_type=provenance.source_object_type,
        source_object_id=provenance.source_object_id,
        collected_at=provenance.collected_at,
        collector_version=provenance.collector_version,
        collector_principal_id=provenance.collector_principal_id,
        evidence_schema_version=provenance.evidence_schema_version,
        evidence_classification=provenance.classification.value,
    )


def _node_properties(principal: ProjectedPrincipal) -> dict[str, Any]:
    properties = principal.model_dump(mode="json", exclude_none=True)
    properties["projection_key"] = (
        f"{principal.snapshot_id}:{principal.projection_version}:{principal.principal_id}"
    )
    return properties


def _canonical_digest(nodes: list[dict[str, Any]]) -> str:
    canonical = json.dumps(
        sorted(nodes, key=lambda node: cast(str, node["principal_id"])),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def _replace_projection(
    transaction: AsyncManagedTransaction,
    snapshot_id: str,
    projection_version: str,
    nodes: list[dict[str, Any]],
    content_sha256: str,
) -> None:
    result = await transaction.run(
        """
        MATCH (node:Principal {snapshot_id: $snapshot_id, projection_version: $version})
        DETACH DELETE node
        """,
        snapshot_id=snapshot_id,
        version=projection_version,
    )
    await result.consume()
    result = await transaction.run(
        """
        MATCH (marker:IdentityMeshProjection {
            snapshot_id: $snapshot_id, projection_version: $version
        })
        DELETE marker
        """,
        snapshot_id=snapshot_id,
        version=projection_version,
    )
    await result.consume()
    result = await transaction.run(
        """
        UNWIND $nodes AS properties
        CREATE (node:Principal:AwsRole)
        SET node = properties
        """,
        nodes=nodes,
    )
    await result.consume()
    marker_key = f"{snapshot_id}:{projection_version}"
    result = await transaction.run(
        """
        CREATE (marker:IdentityMeshProjection {
            schema_version: 'identitymesh.graph-projection/v1',
            projection_key: $projection_key,
            snapshot_id: $snapshot_id,
            projection_version: $version,
            principal_count: $principal_count,
            content_sha256: $content_sha256
        })
        """,
        projection_key=marker_key,
        snapshot_id=snapshot_id,
        version=projection_version,
        principal_count=len(nodes),
        content_sha256=content_sha256,
    )
    await result.consume()


class Neo4jPrincipalProjector:
    """Write, verify, and query rebuildable principal projections."""

    def __init__(self, driver: AsyncDriver, database: str = "neo4j") -> None:
        self._driver = driver
        self._database = database

    async def ensure_schema(self) -> None:
        try:
            await self._driver.execute_query(_PRINCIPAL_CONSTRAINT, database_=self._database)
            await self._driver.execute_query(_MARKER_CONSTRAINT, database_=self._database)
        except (DriverError, Neo4jError) as error:
            raise GraphProjectionError("Neo4j projection schema could not be prepared") from error

    async def project_and_verify(
        self,
        snapshot_id: UUID,
        principals: tuple[Principal, ...],
    ) -> ProjectionResult:
        projected = tuple(project_principal(principal) for principal in principals)
        if any(principal.snapshot_id != snapshot_id for principal in projected):
            raise GraphProjectionError("principal snapshot did not match the projection snapshot")
        nodes = [_node_properties(principal) for principal in projected]
        content_sha256 = _canonical_digest(nodes)

        await self.ensure_schema()
        try:
            async with self._driver.session(database=self._database) as session:
                await session.execute_write(
                    _replace_projection,
                    str(snapshot_id),
                    PROJECTION_VERSION,
                    nodes,
                    content_sha256,
                )
        except (DriverError, Neo4jError) as error:
            raise GraphProjectionError("Neo4j projection write failed") from error

        await self.verify(snapshot_id, len(nodes), content_sha256)
        return ProjectionResult(
            snapshot_id=snapshot_id,
            projection_version=PROJECTION_VERSION,
            principal_count=len(nodes),
            content_sha256=content_sha256,
        )

    async def verify(
        self,
        snapshot_id: UUID,
        expected_count: int,
        expected_digest: str,
    ) -> None:
        try:
            async with self._driver.session(database=self._database) as session:
                marker_result = await session.run(
                    """
                    MATCH (marker:IdentityMeshProjection {
                        snapshot_id: $snapshot_id, projection_version: $version
                    })
                    RETURN marker.principal_count AS principal_count,
                           marker.content_sha256 AS content_sha256
                    """,
                    snapshot_id=str(snapshot_id),
                    version=PROJECTION_VERSION,
                )
                marker = await marker_result.single(strict=True)
                node_result = await session.run(
                    """
                    MATCH (node:Principal {
                        snapshot_id: $snapshot_id, projection_version: $version
                    })
                    RETURN labels(node) AS labels, properties(node) AS properties
                    ORDER BY node.principal_id
                    """,
                    snapshot_id=str(snapshot_id),
                    version=PROJECTION_VERSION,
                )
                nodes: list[dict[str, Any]] = []
                invalid_labels = False
                async for record in node_result:
                    invalid_labels = invalid_labels or set(record["labels"]) != {
                        "Principal",
                        "AwsRole",
                    }
                    nodes.append(cast(dict[str, Any], record["properties"]))
        except (DriverError, Neo4jError, ValueError) as error:
            raise GraphProjectionVerificationError(
                "Neo4j projection could not be verified"
            ) from error

        try:
            actual_digest = _canonical_digest(nodes)
        except (KeyError, TypeError) as error:
            raise GraphProjectionVerificationError(
                "Neo4j projection contained malformed node properties"
            ) from error
        valid = (
            marker is not None
            and marker["principal_count"] == expected_count
            and marker["content_sha256"] == expected_digest
            and len(nodes) == expected_count
            and actual_digest == expected_digest
            and not invalid_labels
        )
        if not valid:
            raise GraphProjectionVerificationError("Neo4j projection did not match source data")

    async def list_principals(
        self,
        snapshot_id: UUID,
        projection_version: str,
        *,
        limit: int,
        cursor: UUID | None = None,
    ) -> tuple[tuple[ProjectedPrincipal, ...], UUID | None, int]:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        try:
            async with self._driver.session(database=self._database) as session:
                result = await session.run(
                    """
                    MATCH (node:Principal:AwsRole {
                        snapshot_id: $snapshot_id, projection_version: $version
                    })
                    WHERE $cursor IS NULL OR node.principal_id > $cursor
                    RETURN properties(node) AS properties
                    ORDER BY node.principal_id
                    LIMIT $fetch_limit
                    """,
                    snapshot_id=str(snapshot_id),
                    version=projection_version,
                    cursor=None if cursor is None else str(cursor),
                    fetch_limit=limit + 1,
                )
                raw = [cast(dict[str, Any], record["properties"]) async for record in result]
                marker_result = await session.run(
                    """
                    MATCH (marker:IdentityMeshProjection {
                        snapshot_id: $snapshot_id, projection_version: $version
                    })
                    RETURN marker.principal_count AS principal_count
                    """,
                    snapshot_id=str(snapshot_id),
                    version=projection_version,
                )
                marker = await marker_result.single(strict=True)
        except (DriverError, Neo4jError) as error:
            raise GraphProjectionError("Neo4j principal query failed") from error

        total_count = None if marker is None else marker["principal_count"]
        if (
            not isinstance(total_count, int)
            or isinstance(total_count, bool)
            or total_count < len(raw)
        ):
            raise GraphProjectionVerificationError(
                "Neo4j projection marker did not match the principal query"
            )

        has_more = len(raw) > limit
        documents = raw[:limit]
        for document in documents:
            document.pop("projection_key", None)
        try:
            principals = tuple(
                ProjectedPrincipal.model_validate_json(json.dumps(document))
                for document in documents
            )
        except (TypeError, ValidationError) as error:
            raise GraphProjectionVerificationError(
                "Neo4j principal data did not match its projection contract"
            ) from error
        next_cursor = principals[-1].principal_id if has_more and principals else None
        return principals, next_cursor, total_count
