"""Authenticated HTTP contracts for collection and active identity inventory."""

import hmac
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field

from identitymesh.aws_collection_service import AwsCollectionRunError
from identitymesh.config import Settings
from identitymesh.graph_projection import GraphProjectionError, ProjectedPrincipal
from identitymesh.identity_pipeline import (
    AwsRolePipelineCoordinator,
    CollectionAlreadyRunningError,
    IdentityPipelineRun,
    IdentityPipelineRunError,
)
from identitymesh.inventory import ActiveSnapshotNotFoundError, InventoryService
from identitymesh.snapshots import Snapshot


class ApiError(Exception):
    """A safe structured error intended for the public API boundary."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.headers = headers
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ApplicationServices:
    """Runtime services required by the protected data API."""

    coordinator: AwsRolePipelineCoordinator
    inventory: InventoryService


class SnapshotResponse(BaseModel):
    """Safe lifecycle metadata for one collection snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot_id: UUID
    sequence_id: int
    status: str
    collector_version: str
    projection_version: str | None
    failure_code: str | None
    created_at: datetime
    collected_at: datetime | None
    projection_started_at: datetime | None
    ready_at: datetime | None
    failed_at: datetime | None

    @classmethod
    def from_snapshot(cls, snapshot: Snapshot) -> "SnapshotResponse":
        return cls(
            snapshot_id=snapshot.snapshot_id,
            sequence_id=snapshot.sequence_id,
            status=snapshot.status.value,
            collector_version=snapshot.collector_version,
            projection_version=snapshot.projection_version,
            failure_code=snapshot.failure_code,
            created_at=snapshot.created_at,
            collected_at=snapshot.collected_at,
            projection_started_at=snapshot.projection_started_at,
            ready_at=snapshot.ready_at,
            failed_at=snapshot.failed_at,
        )


class SnapshotListResponse(BaseModel):
    """Bounded newest-first snapshot history."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.snapshot-list/v1"] = "identitymesh.snapshot-list/v1"
    items: tuple[SnapshotResponse, ...]


class CollectionRunResponse(BaseModel):
    """Terminal outcome for a synchronous AWS role pipeline run."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.collection-run/v1"] = "identitymesh.collection-run/v1"
    snapshot_id: UUID
    collection_status: str
    snapshot_status: str
    failure_code: str | None
    role_count: int = Field(ge=0)
    gap_count: int = Field(ge=0)
    principal_count: int = Field(ge=0)
    projection_version: str | None
    activated: bool

    @classmethod
    def from_run(cls, run: IdentityPipelineRun) -> "CollectionRunResponse":
        return cls(
            snapshot_id=run.snapshot_id,
            collection_status=run.collection_status.value,
            snapshot_status=run.snapshot_status.value,
            failure_code=run.failure_code,
            role_count=run.role_count,
            gap_count=run.gap_count,
            principal_count=run.principal_count,
            projection_version=run.projection_version,
            activated=run.activated,
        )


class PrincipalPageResponse(BaseModel):
    """Cursor page pinned to one ready graph projection."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.principal-page/v1"] = "identitymesh.principal-page/v1"
    snapshot_id: UUID
    projection_version: str
    items: tuple[ProjectedPrincipal, ...]
    next_cursor: UUID | None
    total_count: int = Field(ge=0)


class GraphNode(BaseModel):
    """Minimal visualization node derived from a projected principal."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: UUID
    labels: tuple[Literal["Principal", "AwsRole"], ...]
    display_name: str
    provider: str
    principal_type: str
    external_id: str


class GraphRelationship(BaseModel):
    """Reserved typed relationship contract for later graph slices."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    id: str
    relationship_type: str
    source: UUID
    target: UUID


class GraphResponse(BaseModel):
    """Basic active graph view; this slice intentionally contains no edges."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.graph/v1"] = "identitymesh.graph/v1"
    snapshot_id: UUID
    projection_version: str
    nodes: tuple[GraphNode, ...]
    relationships: tuple[GraphRelationship, ...] = ()
    next_cursor: UUID | None
    total_count: int = Field(ge=0)


def _services(request: Request) -> ApplicationServices:
    services = getattr(request.app.state, "services", None)
    if not isinstance(services, ApplicationServices):
        raise ApiError(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "DATA_API_UNAVAILABLE",
            "The identity data service is not available.",
        )
    return services


def build_data_router(settings: Settings) -> APIRouter:
    """Build protected routes using the validated application configuration."""

    router = APIRouter(prefix="/api/v1")

    async def require_bearer(request: Request) -> None:
        if not settings.data_api_enabled or settings.api_token is None:
            raise ApiError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "DATA_API_NOT_CONFIGURED",
                "The identity data API is not configured.",
            )
        authorization = request.headers.get("Authorization", "")
        scheme, separator, supplied = authorization.partition(" ")
        expected = settings.api_token.get_secret_value()
        if (
            separator != " "
            or scheme.lower() != "bearer"
            or not supplied
            or not hmac.compare_digest(supplied.encode(), expected.encode())
        ):
            raise ApiError(
                status.HTTP_401_UNAUTHORIZED,
                "AUTHENTICATION_FAILED",
                "A valid bearer token is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    auth = Depends(require_bearer)

    @router.post(
        "/collections/aws/iam/roles",
        response_model=CollectionRunResponse,
        dependencies=[auth],
        tags=["collection"],
    )
    async def collect_aws_roles(request: Request) -> CollectionRunResponse:
        try:
            run = await _services(request).coordinator.run()
        except CollectionAlreadyRunningError as error:
            raise ApiError(
                status.HTTP_409_CONFLICT,
                error.reason_code,
                "An AWS role collection is already running.",
            ) from error
        except (AwsCollectionRunError, IdentityPipelineRunError) as error:
            raise ApiError(
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                error.reason_code,
                "The AWS role collection could not be completed safely.",
            ) from error
        return CollectionRunResponse.from_run(run)

    @router.get(
        "/snapshots",
        response_model=SnapshotListResponse,
        dependencies=[auth],
        tags=["inventory"],
    )
    async def list_snapshots(
        request: Request,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> SnapshotListResponse:
        snapshots = await _services(request).inventory.recent_snapshots(limit)
        return SnapshotListResponse(
            items=tuple(SnapshotResponse.from_snapshot(snapshot) for snapshot in snapshots)
        )

    @router.get(
        "/snapshots/active",
        response_model=SnapshotResponse,
        dependencies=[auth],
        tags=["inventory"],
    )
    async def get_active_snapshot(request: Request) -> SnapshotResponse:
        try:
            snapshot = await _services(request).inventory.active_snapshot()
        except ActiveSnapshotNotFoundError as error:
            raise ApiError(
                status.HTTP_404_NOT_FOUND,
                error.reason_code,
                "No ready active identity snapshot exists.",
            ) from error
        return SnapshotResponse.from_snapshot(snapshot)

    @router.get(
        "/principals",
        response_model=PrincipalPageResponse,
        dependencies=[auth],
        tags=["inventory"],
    )
    async def list_principals(
        request: Request,
        limit: int = Query(default=50, ge=1, le=100),
        cursor: UUID | None = Query(default=None),
    ) -> PrincipalPageResponse:
        try:
            page = await _services(request).inventory.principals(limit=limit, cursor=cursor)
        except ActiveSnapshotNotFoundError as error:
            raise ApiError(
                status.HTTP_404_NOT_FOUND,
                error.reason_code,
                "No ready active identity snapshot exists.",
            ) from error
        except GraphProjectionError as error:
            raise ApiError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                error.reason_code,
                "The active identity projection could not be read.",
            ) from error
        projection_version = page.snapshot.projection_version
        if projection_version is None:  # pragma: no cover - protected by inventory service
            raise RuntimeError("active snapshot projection version is missing")
        return PrincipalPageResponse(
            snapshot_id=page.snapshot.snapshot_id,
            projection_version=projection_version,
            items=page.items,
            next_cursor=page.next_cursor,
            total_count=page.total_count,
        )

    @router.get(
        "/graph",
        response_model=GraphResponse,
        dependencies=[auth],
        tags=["inventory"],
    )
    async def get_graph(
        request: Request,
        limit: int = Query(default=100, ge=1, le=100),
        cursor: UUID | None = Query(default=None),
    ) -> GraphResponse:
        try:
            page = await _services(request).inventory.principals(limit=limit, cursor=cursor)
        except ActiveSnapshotNotFoundError as error:
            raise ApiError(
                status.HTTP_404_NOT_FOUND,
                error.reason_code,
                "No ready active identity snapshot exists.",
            ) from error
        except GraphProjectionError as error:
            raise ApiError(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                error.reason_code,
                "The active identity projection could not be read.",
            ) from error
        projection_version = page.snapshot.projection_version
        if projection_version is None:  # pragma: no cover - protected by inventory service
            raise RuntimeError("active snapshot projection version is missing")
        return GraphResponse(
            snapshot_id=page.snapshot.snapshot_id,
            projection_version=projection_version,
            nodes=tuple(
                GraphNode(
                    id=principal.principal_id,
                    labels=("Principal", "AwsRole"),
                    display_name=principal.display_name,
                    provider=principal.provider,
                    principal_type=principal.principal_type,
                    external_id=principal.external_id,
                )
                for principal in page.items
            ),
            next_cursor=page.next_cursor,
            total_count=page.total_count,
        )

    return router
