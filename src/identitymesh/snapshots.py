"""Snapshot lifecycle domain model and transition rules."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class SnapshotStatus(str, Enum):
    """Persisted lifecycle states for an evidence snapshot."""

    COLLECTING = "collecting"
    COLLECTED = "collected"
    PROJECTING = "projecting"
    READY = "ready"
    FAILED = "failed"


LEGAL_TRANSITIONS: dict[SnapshotStatus, frozenset[SnapshotStatus]] = {
    SnapshotStatus.COLLECTING: frozenset({SnapshotStatus.COLLECTED, SnapshotStatus.FAILED}),
    SnapshotStatus.COLLECTED: frozenset({SnapshotStatus.PROJECTING, SnapshotStatus.FAILED}),
    SnapshotStatus.PROJECTING: frozenset({SnapshotStatus.READY, SnapshotStatus.FAILED}),
    SnapshotStatus.READY: frozenset(),
    SnapshotStatus.FAILED: frozenset(),
}


class SnapshotError(Exception):
    """Base class for safe, reason-coded snapshot errors."""

    reason_code = "SNAPSHOT_ERROR"


class SnapshotNotFoundError(SnapshotError):
    """Raised when a requested snapshot does not exist."""

    reason_code = "SNAPSHOT_NOT_FOUND"

    def __init__(self, snapshot_id: UUID) -> None:
        self.snapshot_id = snapshot_id
        super().__init__(f"snapshot {snapshot_id} was not found")


class InvalidSnapshotTransitionError(SnapshotError):
    """Raised when a lifecycle transition would violate the state machine."""

    reason_code = "INVALID_SNAPSHOT_TRANSITION"

    def __init__(
        self,
        snapshot_id: UUID,
        current: SnapshotStatus,
        target: SnapshotStatus,
    ) -> None:
        self.snapshot_id = snapshot_id
        self.current = current
        self.target = target
        super().__init__(f"snapshot {snapshot_id} cannot transition from {current} to {target}")


def require_transition(
    snapshot_id: UUID,
    current: SnapshotStatus,
    target: SnapshotStatus,
) -> None:
    """Reject lifecycle changes that are not explicitly allowed."""

    if target not in LEGAL_TRANSITIONS[current]:
        raise InvalidSnapshotTransitionError(snapshot_id, current, target)


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Authoritative snapshot lifecycle record."""

    snapshot_id: UUID
    sequence_id: int
    status: SnapshotStatus
    collector_version: str
    projection_version: str | None
    failure_code: str | None
    created_at: datetime
    collected_at: datetime | None
    projection_started_at: datetime | None
    ready_at: datetime | None
    failed_at: datetime | None


@dataclass(frozen=True, slots=True)
class PromotionResult:
    """Result of completing a projection and evaluating active promotion."""

    snapshot: Snapshot
    activated: bool
