"""Read-only inventory queries pinned to the authoritative active snapshot."""

from dataclasses import dataclass
from uuid import UUID

from identitymesh.graph_projection import Neo4jPrincipalProjector, ProjectedPrincipal
from identitymesh.snapshot_store import SnapshotStore
from identitymesh.snapshots import Snapshot


class ActiveSnapshotNotFoundError(Exception):
    """Raised when graph-backed inventory has not been promoted yet."""

    reason_code = "ACTIVE_SNAPSHOT_NOT_FOUND"


@dataclass(frozen=True, slots=True)
class PrincipalPage:
    """One page of principals from a single ready projection."""

    snapshot: Snapshot
    items: tuple[ProjectedPrincipal, ...]
    next_cursor: UUID | None
    total_count: int


class InventoryService:
    """Keep every graph read pinned to one PostgreSQL-owned active version."""

    def __init__(self, snapshots: SnapshotStore, projector: Neo4jPrincipalProjector) -> None:
        self._snapshots = snapshots
        self._projector = projector

    async def active_snapshot(self) -> Snapshot:
        snapshot = await self._snapshots.get_active()
        if snapshot is None or snapshot.projection_version is None:
            raise ActiveSnapshotNotFoundError("no ready active snapshot exists")
        return snapshot

    async def recent_snapshots(self, limit: int) -> tuple[Snapshot, ...]:
        return await self._snapshots.list_recent(limit)

    async def principals(
        self,
        *,
        limit: int,
        cursor: UUID | None,
    ) -> PrincipalPage:
        snapshot = await self.active_snapshot()
        projection_version = snapshot.projection_version
        if projection_version is None:  # pragma: no cover - protected by active_snapshot
            raise ActiveSnapshotNotFoundError("active snapshot has no projection version")
        items, next_cursor, total_count = await self._projector.list_principals(
            snapshot.snapshot_id,
            projection_version,
            limit=limit,
            cursor=cursor,
        )
        return PrincipalPage(
            snapshot=snapshot,
            items=items,
            next_cursor=next_cursor,
            total_count=total_count,
        )
