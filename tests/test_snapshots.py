from datetime import datetime, timezone
from uuid import uuid4

import pytest

from identitymesh.snapshots import (
    LEGAL_TRANSITIONS,
    InvalidSnapshotTransitionError,
    PromotionResult,
    Snapshot,
    SnapshotStatus,
    require_transition,
)


def test_state_machine_allows_only_forward_lifecycle_transitions() -> None:
    assert LEGAL_TRANSITIONS == {
        SnapshotStatus.COLLECTING: frozenset({SnapshotStatus.COLLECTED, SnapshotStatus.FAILED}),
        SnapshotStatus.COLLECTED: frozenset({SnapshotStatus.PROJECTING, SnapshotStatus.FAILED}),
        SnapshotStatus.PROJECTING: frozenset({SnapshotStatus.READY, SnapshotStatus.FAILED}),
        SnapshotStatus.READY: frozenset(),
        SnapshotStatus.FAILED: frozenset(),
    }


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (SnapshotStatus.COLLECTING, SnapshotStatus.READY),
        (SnapshotStatus.COLLECTED, SnapshotStatus.READY),
        (SnapshotStatus.PROJECTING, SnapshotStatus.COLLECTED),
        (SnapshotStatus.READY, SnapshotStatus.FAILED),
        (SnapshotStatus.FAILED, SnapshotStatus.COLLECTING),
    ],
)
def test_invalid_transitions_return_a_stable_reason_code(
    current: SnapshotStatus,
    target: SnapshotStatus,
) -> None:
    snapshot_id = uuid4()

    with pytest.raises(InvalidSnapshotTransitionError) as error:
        require_transition(snapshot_id, current, target)

    assert error.value.reason_code == "INVALID_SNAPSHOT_TRANSITION"
    assert error.value.snapshot_id == snapshot_id
    assert error.value.current is current
    assert error.value.target is target


def test_promotion_result_preserves_snapshot_and_activation_outcome() -> None:
    now = datetime.now(timezone.utc)
    snapshot = Snapshot(
        snapshot_id=uuid4(),
        sequence_id=1,
        status=SnapshotStatus.READY,
        collector_version="collector-v1",
        projection_version="projection-v1",
        failure_code=None,
        created_at=now,
        collected_at=now,
        projection_started_at=now,
        ready_at=now,
        failed_at=None,
    )

    assert PromotionResult(snapshot=snapshot, activated=True).snapshot is snapshot
