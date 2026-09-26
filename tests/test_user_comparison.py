from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest
from httpx import ASGITransport, AsyncClient
from test_aws_user_inventory import ACCOUNT, CALLER, NOW, _collection, _user
from test_aws_user_inventory import database as database
from test_data_api import FakeCoordinator, FakeInventory, _headers, _settings

from identitymesh.api import ApplicationServices
from identitymesh.aws_user_evidence_store import AwsIamUserEvidenceStore
from identitymesh.collectors.aws_iam import CollectionStatus
from identitymesh.collectors.aws_iam_users import COLLECTOR_VERSION, AwsUserCollection
from identitymesh.main import create_app
from identitymesh.snapshot_comparison import ComparisonError
from identitymesh.snapshot_store import SnapshotStore
from identitymesh.user_comparison import (
    UserComparisonService,
    UserComparisonSource,
    compare_user_sources,
)


def source(collection: AwsUserCollection, sequence: int = 1) -> UserComparisonSource:
    return UserComparisonSource(sequence, collection)


def test_rename_recreation_and_safe_evidence_references() -> None:
    a, b = uuid4(), uuid4()
    original = _user(a)
    base = _collection(a, users=(original, _user(a, "Recreated"), _user(a, "Same")))
    later = _collection(
        b,
        users=(
            _user(b, "Renamed", user_id=original.user_id),
            _user(b, "Recreated", user_id="AIDANEWIMMUTABLEID000"),
            _user(b, "Same"),
        ),
    )
    result = compare_user_sources(source(base), source(later, 2))
    assert (result.added_count, result.removed_count, result.changed_count) == (1, 1, 1)
    assert result.unchanged_count == 1 and result.total_count == 3
    changed = next(change for change in result.items if change.kind == "changed")
    assert changed.changed_fields == ("user_name", "arn")
    assert changed.before.snapshot_id == a and changed.after.snapshot_id == b
    assert changed.before.user_id == changed.after.user_id == original.user_id
    assert changed.before.display_name == "Example" and changed.after.display_name == "Renamed"
    assert changed.before.principal_id == changed.after.principal_id == changed.principal_id
    assert "password_last_used" not in result.model_dump_json()
    assert CALLER not in result.model_dump_json()
    assert result.partition == "aws"


def test_path_and_creation_metadata_are_compared_but_usage_and_observation_noise_are_not() -> None:
    a, b = uuid4(), uuid4()
    original = _collection(a)
    later_user = _user(
        b,
        collected_at=NOW + timedelta(days=1),
        collector_principal_arn=CALLER + "-next",
        password_last_used=None,
    )
    later = original.model_copy(
        update={
            "snapshot_id": b,
            "collected_at": later_user.collected_at,
            "collector_principal_arn": later_user.collector_principal_arn,
            "users": (later_user,),
        }
    )
    assert compare_user_sources(source(original), source(later, 2)).unchanged_count == 1
    arn = later_user.arn.replace("user/", "user/team/")
    moved = later_user.model_copy(
        update={
            "path": "/team/",
            "arn": arn,
            "source_id": arn,
            "created_at": NOW - timedelta(days=1),
        }
    )
    result = compare_user_sources(
        source(original), source(later.model_copy(update={"users": (moved,)}), 2)
    )
    assert result.items[0].changed_fields == ("arn", "path", "created_at")


def test_empty_same_snapshot_and_stable_pagination() -> None:
    a, b = uuid4(), uuid4()
    empty = source(_collection(a, users=()))
    full = source(_collection(b, users=tuple(_user(b, f"U{i}") for i in range(7))), 2)
    assert compare_user_sources(empty, empty).total_count == 0
    assert compare_user_sources(full, full).unchanged_count == 7
    assert compare_user_sources(full, replace(empty, sequence_id=3)).removed_count == 7
    page = compare_user_sources(empty, full, limit=2)
    seen = list(page.items)
    while page.next_cursor:
        page = compare_user_sources(empty, full, limit=2, cursor=page.next_cursor)
        assert page.total_count == page.added_count == 7
        seen.extend(page.items)
    assert len(seen) == len({item.principal_id for item in seen}) == 7
    assert seen == sorted(seen, key=lambda item: item.principal_id)
    final = compare_user_sources(empty, full, cursor=UUID(int=(1 << 128) - 1))
    assert final.items == () and final.next_cursor is None and final.total_count == 7
    shuffled = replace(
        full,
        collection=full.collection.model_copy(
            update={"users": tuple(reversed(full.collection.users))}
        ),
    )
    assert compare_user_sources(empty, full) == compare_user_sources(empty, shuffled)


@pytest.mark.parametrize("status", [CollectionStatus.PARTIAL, CollectionStatus.FAILED])
def test_incomplete_observations_never_establish_absence(status: CollectionStatus) -> None:
    incomplete = _collection(uuid4(), status, () if status is CollectionStatus.FAILED else None)
    for base, target in [(incomplete, _collection(uuid4())), (_collection(uuid4()), incomplete)]:
        with pytest.raises(ComparisonError) as caught:
            compare_user_sources(source(base), source(target))
        assert caught.value.reason_code == "COMPARISON_INCOMPLETE"


@pytest.mark.parametrize("account,partition", [("999999999999", "aws"), (ACCOUNT, "aws-cn")])
def test_empty_observations_still_require_matching_scope(account: str, partition: str) -> None:
    first = _collection(uuid4(), users=())
    second = first.model_copy(
        update={
            "account_id": account,
            "collector_principal_arn": (
                f"arn:{partition}:sts::{account}:assumed-role/Collector/test"
            ),
        }
    )
    with pytest.raises(ComparisonError) as caught:
        compare_user_sources(source(first), source(second))
    assert caught.value.reason_code == "COMPARISON_SCOPE_MISMATCH"


def test_order_limit_and_corrupt_nested_sources_are_rejected() -> None:
    original = _collection(uuid4())
    with pytest.raises(ComparisonError) as caught:
        compare_user_sources(source(original, 2), source(original))
    assert caught.value.reason_code == "COMPARISON_ORDER_INVALID"
    for limit in (0, 101):
        with pytest.raises(ValueError):
            compare_user_sources(source(original), source(original), limit=limit)
    for users in (
        original.users * 2,
        (original.users[0].model_copy(update={"user_name": "Wrong"}),),
        (original.users[0].model_copy(update={"snapshot_id": uuid4()}),),
    ):
        with pytest.raises(ComparisonError) as caught:
            compare_user_sources(
                source(original.model_copy(update={"users": users})), source(original)
            )
        assert caught.value.reason_code == "COMPARISON_SOURCE_INVALID"
    with pytest.raises(ComparisonError) as oversized:
        compare_user_sources(
            source(original.model_copy(update={"users": original.users * 10_001})), source(original)
        )
    assert oversized.value.status_code == 413


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [OSError("private-host"), TimeoutError("private-host"), asyncpg.PostgresError("private-query")],
)
async def test_dependency_failures_are_safe(failure: Exception) -> None:
    pool = Mock()
    pool.acquire.side_effect = failure
    with pytest.raises(ComparisonError) as caught:
        await UserComparisonService(pool).compare(uuid4(), uuid4())
    assert caught.value.reason_code == "COMPARISON_UNAVAILABLE"
    assert "private" not in str(caught.value)
    with pytest.raises(ValueError):
        await UserComparisonService(pool).compare(uuid4(), uuid4(), limit=0)


async def persist(
    pool: asyncpg.Pool,
    *,
    names: tuple[str, ...] = ("Example",),
    status: CollectionStatus = CollectionStatus.COMPLETE,
) -> UUID:
    snapshot = await SnapshotStore(pool).create(COLLECTOR_VERSION)
    await AwsIamUserEvidenceStore(pool).persist_and_finalize(
        _collection(
            snapshot.snapshot_id, status, tuple(_user(snapshot.snapshot_id, name) for name in names)
        )
    )
    return snapshot.snapshot_id


@pytest.mark.anyio
async def test_real_retained_history_pagination_and_active_role_preservation(
    database: asyncpg.Pool,
) -> None:
    snapshots = SnapshotStore(database)
    role = await snapshots.create("aws-iam-role/0.1")
    await snapshots.mark_collected(role.snapshot_id)
    await snapshots.start_projection(role.snapshot_id, "test/1")
    await snapshots.complete_projection(role.snapshot_id)
    a = await persist(database, names=("Same", "Removed"))
    b = await persist(database, names=("Same", "Added", "Another"))
    # A newer user collection must not change the explicit historical pair.
    await persist(database, names=())
    service = UserComparisonService(database)
    first = await service.compare(a, b, limit=2)
    last = await service.compare(a, b, limit=2, cursor=first.next_cursor)
    assert first.added_count == 2 and first.removed_count == 1 and first.unchanged_count == 1
    assert first.total_count == last.total_count == 3
    assert len(first.items + last.items) == 3 and last.next_cursor is None
    assert (await snapshots.get_active()).snapshot_id == role.snapshot_id
    assert (await snapshots.get(a)).status.value == "collected"
    assert (await service.compare(a, a)).unchanged_count == 2
    with pytest.raises(ComparisonError) as wrong_order:
        await service.compare(b, a)
    assert wrong_order.value.reason_code == "COMPARISON_ORDER_INVALID"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "kind,code",
    [
        ("missing", "SNAPSHOT_NOT_FOUND"),
        ("role", "COMPARISON_SCOPE_MISMATCH"),
        ("version", "COMPARISON_SCOPE_MISMATCH"),
        ("unfinished", "COMPARISON_NOT_READY"),
        ("partial", "COMPARISON_INCOMPLETE"),
        ("failed", "COMPARISON_INCOMPLETE"),
        ("no_evidence", "COMPARISON_SOURCE_INVALID"),
    ],
)
async def test_unusable_snapshots_are_rejected(
    database: asyncpg.Pool, kind: str, code: str
) -> None:
    base = await persist(database)
    snapshots = SnapshotStore(database)
    if kind == "missing":
        target = uuid4()
    elif kind in {"partial", "failed"}:
        target = await persist(
            database, status=CollectionStatus(kind), names=() if kind == "failed" else ("Example",)
        )
    else:
        version = {"role": "aws-iam-role/0.1", "version": "aws-iam-user/next"}.get(
            kind, COLLECTOR_VERSION
        )
        snapshot = await snapshots.create(version)
        target = snapshot.snapshot_id
        if kind == "no_evidence":
            await snapshots.mark_failed(target, "AWS_COLLECTION_INTERNAL_ERROR")
    with pytest.raises(ComparisonError) as caught:
        await UserComparisonService(database).compare(base, target)
    assert caught.value.reason_code == code


@pytest.mark.anyio
@pytest.mark.parametrize(
    "corruption",
    [
        "principal",
        "evidence",
        "count",
        "missing",
        "gap",
        "lifecycle",
        "invalid_json",
        "caller",
        "oversize",
    ],
)
async def test_comparison_revalidates_sources_on_every_page(
    database: asyncpg.Pool, corruption: str
) -> None:
    a, b = await persist(database, names=()), await persist(database, names=("One", "Two"))
    service = UserComparisonService(database)
    first = await service.compare(a, b, limit=1)
    sql = {
        "principal": "UPDATE principals SET display_name = 'Wrong' WHERE snapshot_id = $1",
        "evidence": "UPDATE provider_evidence SET object_type = 'iam_role' WHERE snapshot_id = $1",
        "count": (
            "UPDATE aws_iam_user_collection_attempts SET user_count = 1 WHERE snapshot_id = $1"
        ),
        "missing": "DELETE FROM provider_evidence WHERE snapshot_id = $1",
        "gap": (
            "INSERT INTO aws_iam_user_collection_gaps (snapshot_id, operation, "
            "reason_code, retryable, message) VALUES ($1, 'iam:ListUsers', "
            "'AWS_ACCESS_DENIED', FALSE, 'denied')"
        ),
        "lifecycle": (
            "UPDATE snapshots SET status = 'failed', failed_at = now(), "
            "failure_code = 'UNEXPECTED' WHERE snapshot_id = $1"
        ),
        "invalid_json": (
            "UPDATE provider_evidence SET evidence = '{}'::jsonb WHERE snapshot_id = $1"
        ),
        "caller": (
            "UPDATE aws_iam_user_collection_attempts SET collector_principal_arn "
            "= 'private-invalid-value' WHERE snapshot_id = $1"
        ),
        "oversize": (
            "UPDATE aws_iam_user_collection_attempts SET user_count = 10001 WHERE snapshot_id = $1"
        ),
    }[corruption]
    async with database.acquire() as connection:
        await connection.execute(sql, b)
    with pytest.raises(ComparisonError) as caught:
        await service.compare(a, b, limit=1, cursor=first.next_cursor)
    assert caught.value.reason_code == "COMPARISON_SOURCE_INVALID"
    assert "private" not in str(caught.value)


@pytest.mark.anyio
async def test_authenticated_http_contract_and_failures(database: asyncpg.Pool) -> None:
    a, b = await persist(database, names=()), await persist(database, names=("One", "Two"))
    app = create_app(
        _settings(),
        readiness_probes={},
        services=ApplicationServices(
            coordinator=FakeCoordinator(),
            inventory=FakeInventory(),
            user_comparisons=UserComparisonService(database),
        ),
    )
    path = "/api/v1/snapshots/users/compare"
    query = {"base_snapshot_id": str(a), "target_snapshot_id": str(b), "limit": 1}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path, params=query)).status_code == 401
        response = await client.get(path, params=query, headers=_headers())
        assert response.status_code == 200
        body = response.json()
        assert body["schema_version"] == "identitymesh.user-comparison/v1"
        assert body["added_count"] == 2 and body["next_cursor"]
        assert body["compared_fields"] == ["user_name", "arn", "path", "created_at"]
        assert "password_last_used" not in response.text
        page = await client.get(
            path, params={**query, "cursor": body["next_cursor"]}, headers=_headers()
        )
        assert page.json()["next_cursor"] is None
        assert page.json()["items"][0]["principal_id"] != body["items"][0]["principal_id"]
        for invalid in (
            {"limit": 0},
            {"limit": 101},
            {"cursor": "invalid"},
            {"base_snapshot_id": "invalid"},
        ):
            response = await client.get(path, params={**query, **invalid}, headers=_headers())
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
        response = await client.get(
            path, params={**query, "target_snapshot_id": str(uuid4())}, headers=_headers()
        )
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "SNAPSHOT_NOT_FOUND"
        partial = await persist(database, status=CollectionStatus.PARTIAL)
        response = await client.get(
            path, params={**query, "target_snapshot_id": str(partial)}, headers=_headers()
        )
        assert (
            response.status_code == 409
            and response.json()["error"]["code"] == "COMPARISON_INCOMPLETE"
        )


@pytest.mark.anyio
async def test_http_missing_service_is_safe() -> None:
    app = create_app(
        _settings(),
        readiness_probes={},
        services=ApplicationServices(coordinator=FakeCoordinator(), inventory=FakeInventory()),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/v1/snapshots/users/compare",
            params={"base_snapshot_id": str(uuid4()), "target_snapshot_id": str(uuid4())},
            headers=_headers(),
        )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "COMPARISON_UNAVAILABLE"
