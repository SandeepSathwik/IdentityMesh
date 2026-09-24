import os
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import UUID, uuid4

import asyncpg  # type: ignore[import-untyped]
import httpx
import pytest

from identitymesh.api import ApplicationServices
from identitymesh.aws_evidence_store import AwsIamRoleEvidenceStore
from identitymesh.collectors.aws_iam import (
    COLLECTOR_VERSION,
    AwsRoleCollection,
    AwsRoleEvidence,
    CollectionStatus,
)
from identitymesh.comparison_store import SnapshotComparisonService
from identitymesh.config import Settings
from identitymesh.main import create_app
from identitymesh.snapshot_comparison import ComparisonError, ComparisonSource, compare_sources
from identitymesh.snapshot_store import SnapshotStore

NOW = datetime(2026, 9, 24, 12, tzinfo=timezone.utc)
ACCOUNT = "123456789012"
TOKEN = "comparison-test-token-at-least-32-characters"  # noqa: S105
TEST_DSN = os.getenv("IDENTITYMESH_TEST_POSTGRES_DSN")


def role(snapshot_id: UUID, name: str = "Application", role_id: str = "AROAPP") -> AwsRoleEvidence:
    arn = f"arn:aws:iam::{ACCOUNT}:role/{name}"
    return AwsRoleEvidence(
        snapshot_id=snapshot_id,
        source_id=arn,
        account_id=ACCOUNT,
        collector_principal_arn=f"arn:aws:sts::{ACCOUNT}:assumed-role/collector/run",
        collected_at=NOW,
        collector_version=COLLECTOR_VERSION,
        role_id=role_id,
        role_name=name,
        arn=arn,
        path="/",
        created_at=NOW,
        assume_role_policy_document={"Statement": []},
    )


def source(*roles: AwsRoleEvidence, sequence: int = 1) -> ComparisonSource:
    return ComparisonSource(
        snapshot_id=roles[0].snapshot_id if roles else uuid4(),
        sequence_id=sequence,
        account_id=ACCOUNT,
        collector_version=COLLECTOR_VERSION,
        collected_at=NOW,
        roles=roles,
    )


def test_added_removed_changed_unchanged_and_safe_provenance() -> None:
    base_id, target_id = uuid4(), uuid4()
    first = source(role(base_id), role(base_id, "Removed", "ARODELETED"))
    newer = role(target_id).model_copy(
        update={
            "description": "private-description-value",
            "tags": {"Private": "private-tag-value"},
            "assume_role_policy_document": {"Statement": [{"Principal": "private-policy-value"}]},
        }
    )
    result = compare_sources(first, source(newer, role(target_id, "Added", "ARONEW"), sequence=2))
    assert (result.added_count, result.removed_count, result.changed_count) == (1, 1, 1)
    assert result.unchanged_count == 0
    changed = next(item for item in result.items if item.kind == "changed")
    assert changed.changed_fields == ("assume_role_policy_document", "description", "tags")
    assert changed.before.snapshot_id == base_id
    assert changed.after.snapshot_id == target_id
    assert "private-" not in result.model_dump_json()
    assert result.items == tuple(sorted(result.items, key=lambda item: item.principal_id))


def test_observation_and_usage_changes_do_not_create_metadata_changes() -> None:
    original = role(uuid4())
    later = original.model_copy(
        update={
            "snapshot_id": uuid4(),
            "collected_at": NOW + timedelta(days=1),
            "collector_principal_arn": f"arn:aws:sts::{ACCOUNT}:assumed-role/collector/new-session",
            "last_used_at": NOW,
            "last_used_region": "us-east-1",
        }
    )
    result = compare_sources(source(original), source(later, sequence=2))
    assert result.total_count == 0
    assert result.unchanged_count == 1
    assert result.items == ()


def test_recreated_role_with_same_arn_is_removed_and_added() -> None:
    original = role(uuid4())
    recreated = original.model_copy(update={"snapshot_id": uuid4(), "role_id": "ARORECREATED"})
    result = compare_sources(source(original), source(recreated, sequence=2))
    assert (result.added_count, result.removed_count, result.changed_count) == (1, 1, 0)


def test_complete_empty_and_same_snapshot_are_valid() -> None:
    populated = source(role(uuid4()))
    empty = source(sequence=2)
    assert compare_sources(populated, empty).removed_count == 1
    assert compare_sources(empty, empty).total_count == 0
    assert compare_sources(populated, populated).unchanged_count == 1


def test_dictionary_key_order_is_ignored_but_policy_array_order_is_conservative() -> None:
    original = role(uuid4()).model_copy(
        update={
            "assume_role_policy_document": {"Version": "2012-10-17", "Statement": ["A", "B"]},
            "tags": {"a": "1", "b": "2"},
        }
    )
    reordered = original.model_copy(
        update={
            "assume_role_policy_document": {"Statement": ["A", "B"], "Version": "2012-10-17"},
            "tags": {"b": "2", "a": "1"},
        }
    )
    assert compare_sources(source(original), source(reordered)).unchanged_count == 1
    reordered = reordered.model_copy(
        update={
            "assume_role_policy_document": {"Version": "2012-10-17", "Statement": ["B", "A"]},
        }
    )
    assert compare_sources(source(original), source(reordered)).changed_count == 1


def test_pagination_has_stable_counts_no_duplicates_and_terminal_empty_page() -> None:
    base = source()
    target_id = uuid4()
    target = source(*(role(target_id, f"Role{i}", f"ARO{i}") for i in range(7)), sequence=2)
    result = compare_sources(base, target, limit=2)
    seen = list(result.items)
    while result.next_cursor:
        result = compare_sources(base, target, limit=2, cursor=result.next_cursor)
        assert result.added_count == result.total_count == 7
        seen.extend(result.items)
    assert len({item.principal_id for item in seen}) == len(seen) == 7
    final = compare_sources(base, target, cursor=UUID(int=(1 << 128) - 1))
    assert final.items == () and final.next_cursor is None and final.total_count == 7
    shuffled = replace(target, roles=tuple(reversed(target.roles)))
    assert compare_sources(base, target) == compare_sources(base, shuffled)


@pytest.mark.parametrize(
    "field,value,code",
    [
        ("account_id", "999999999999", "COMPARISON_SCOPE_MISMATCH"),
        ("collector_version", "aws-iam-role/next", "COMPARISON_SCOPE_MISMATCH"),
        ("sequence_id", 0, "COMPARISON_ORDER_INVALID"),
    ],
)
def test_incompatible_snapshots_are_rejected(field: str, value: object, code: str) -> None:
    first = source()
    with pytest.raises(ComparisonError) as caught:
        compare_sources(first, replace(first, **{field: value}))
    assert caught.value.reason_code == code


def test_size_limit_duplicate_identity_and_invalid_page_limit() -> None:
    original = role(uuid4())
    with pytest.raises(ComparisonError, match="limit"):
        compare_sources(source(), source(*([original] * 10_001)))
    with pytest.raises(ComparisonError, match="Duplicate"):
        compare_sources(source(original, original), source())
    with pytest.raises(ValueError):
        compare_sources(source(), source(), limit=101)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [OSError("private-host"), TimeoutError("private-host"), asyncpg.PostgresError("private-query")],
)
async def test_database_failures_have_safe_reason_codes(failure: Exception) -> None:
    pool = Mock()
    pool.acquire.side_effect = failure
    with pytest.raises(ComparisonError) as caught:
        await SnapshotComparisonService(pool).compare(uuid4(), uuid4())
    assert caught.value.reason_code == "COMPARISON_UNAVAILABLE"
    assert "private" not in str(caught.value)


@pytest.fixture
async def comparison_pool() -> AsyncIterator[asyncpg.Pool]:
    if TEST_DSN is None:
        pytest.skip("IDENTITYMESH_TEST_POSTGRES_DSN is not configured")
    pool = await asyncpg.create_pool(TEST_DSN, min_size=1, max_size=3)
    try:
        async with pool.acquire() as connection:
            await connection.execute("TRUNCATE snapshots CASCADE")
            await connection.execute("INSERT INTO active_snapshot (singleton) VALUES (TRUE)")
        yield pool
    finally:
        await pool.close()


async def persist(pool: asyncpg.Pool, *, empty: bool = False, ready: bool = True) -> UUID:
    snapshots = SnapshotStore(pool)
    snapshot = await snapshots.create(COLLECTOR_VERSION)
    evidence = role(snapshot.snapshot_id)
    collection = AwsRoleCollection(
        snapshot_id=snapshot.snapshot_id,
        collected_at=NOW,
        status=CollectionStatus.COMPLETE,
        account_id=ACCOUNT,
        collector_principal_arn=evidence.collector_principal_arn,
        roles=() if empty else (evidence,),
    )
    await AwsIamRoleEvidenceStore(pool).persist_and_finalize(collection)
    if ready:
        await snapshots.start_projection(snapshot.snapshot_id, "test-projection/v1")
        await snapshots.complete_projection(snapshot.snapshot_id)
    return snapshot.snapshot_id


@pytest.mark.anyio
async def test_postgres_comparison_pins_history_and_retains_active_snapshot(
    comparison_pool,
) -> None:
    base = await persist(comparison_pool)
    target = await persist(comparison_pool, empty=True)
    active = await persist(comparison_pool)
    service = SnapshotComparisonService(comparison_pool)
    result = await service.compare(base, target)
    assert result.removed_count == 1
    assert result.base_snapshot_id == base and result.target_snapshot_id == target
    assert (await SnapshotStore(comparison_pool).get_active()).snapshot_id == active
    assert (await service.compare(active, active)).unchanged_count == 1
    with pytest.raises(ComparisonError) as caught:
        await service.compare(target, base)
    assert caught.value.reason_code == "COMPARISON_ORDER_INVALID"


@pytest.mark.anyio
async def test_postgres_missing_and_unready_do_not_imply_absence(comparison_pool) -> None:
    base = await persist(comparison_pool)
    unready = await persist(comparison_pool, ready=False)
    service = SnapshotComparisonService(comparison_pool)
    with pytest.raises(ComparisonError) as caught:
        await service.compare(base, unready)
    assert caught.value.reason_code == "COMPARISON_NOT_READY"
    await SnapshotStore(comparison_pool).mark_failed(unready, "AWS_COLLECTION_PARTIAL")
    with pytest.raises(ComparisonError) as caught:
        await service.compare(base, unready)
    assert caught.value.reason_code == "COMPARISON_NOT_READY"
    with pytest.raises(ComparisonError) as caught:
        await service.compare(base, uuid4())
    assert caught.value.status_code == 404


@pytest.mark.anyio
async def test_postgres_empty_scope_and_collector_version_are_checked(comparison_pool) -> None:
    base = await persist(comparison_pool, empty=True)
    target = await persist(comparison_pool, empty=True)
    service = SnapshotComparisonService(comparison_pool)
    async with comparison_pool.acquire() as connection:
        await connection.execute(
            "UPDATE aws_iam_role_collection_attempts SET account_id = '999999999999', "
            "collector_principal_arn = 'arn:aws:iam::999999999999:role/collector' "
            "WHERE snapshot_id = $1",
            target,
        )
    with pytest.raises(ComparisonError) as caught:
        await service.compare(base, target)
    assert caught.value.reason_code == "COMPARISON_SCOPE_MISMATCH"
    async with comparison_pool.acquire() as connection:
        await connection.execute(
            "UPDATE snapshots SET collector_version = 'future/1' WHERE snapshot_id = $1",
            target,
        )
    with pytest.raises(ComparisonError) as caught:
        await service.compare(base, target)
    assert caught.value.reason_code == "COMPARISON_SCOPE_MISMATCH"


@pytest.mark.anyio
async def test_postgres_role_bound_is_checked_before_loading(comparison_pool, monkeypatch) -> None:
    base = await persist(comparison_pool)
    monkeypatch.setattr("identitymesh.comparison_store.MAX_COMPARISON_ROLES", 0)
    with pytest.raises(ComparisonError) as caught:
        await SnapshotComparisonService(comparison_pool).compare(base, base)
    assert caught.value.reason_code == "COMPARISON_TOO_LARGE"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "mutation",
    [
        "DELETE FROM principals WHERE snapshot_id = $1",
        "UPDATE principals SET display_name = 'corrupt' WHERE snapshot_id = $1",
        "UPDATE principals SET principal = '{}'::jsonb WHERE snapshot_id = $1",
        "UPDATE provider_evidence SET evidence = '{}'::jsonb WHERE snapshot_id = $1",
        "UPDATE provider_evidence SET provider_object_id = 'corrupt' WHERE snapshot_id = $1",
        "UPDATE provider_evidence SET evidence = jsonb_set(evidence, '{role_name}', "
        "'\"corrupt\"'::jsonb) WHERE snapshot_id = $1",
        "UPDATE aws_iam_role_collection_attempts SET account_id = '999999999999' "
        "WHERE snapshot_id = $1",
        "DELETE FROM aws_iam_role_collection_attempts WHERE snapshot_id = $1",
    ],
)
async def test_postgres_corruption_never_returns_success(comparison_pool, mutation: str) -> None:
    base = await persist(comparison_pool)
    target = await persist(comparison_pool)
    async with comparison_pool.acquire() as connection:
        await connection.execute(mutation, target)
    with pytest.raises(ComparisonError) as caught:
        await SnapshotComparisonService(comparison_pool).compare(base, target)
    assert caught.value.reason_code == "COMPARISON_SOURCE_INVALID"
    assert caught.value.status_code == 503


def app_with_comparisons(service: object):
    settings = Settings(
        data_api_enabled=True,
        api_token=TOKEN,
        aws_allowed_account_id=ACCOUNT,
        postgres_dsn="postgresql://unused:unused@localhost/unused",
        neo4j_uri="bolt://localhost:7687",
        neo4j_username="neo4j",
        neo4j_password="unused",  # noqa: S106 - synthetic test configuration
        _env_file=None,
    )
    return create_app(
        settings,
        readiness_probes={},
        services=ApplicationServices(
            coordinator=object(),
            inventory=object(),
            comparisons=service,
        ),
    )


@pytest.mark.anyio
async def test_authenticated_api_reads_authoritative_comparison(comparison_pool) -> None:
    base = await persist(comparison_pool)
    target = await persist(comparison_pool, empty=True)
    app = app_with_comparisons(SnapshotComparisonService(comparison_pool))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        result = await client.get(
            "/api/v1/snapshots/compare",
            params={
                "base_snapshot_id": str(base),
                "target_snapshot_id": str(target),
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert result.status_code == 200
    assert result.json()["schema_version"] == "identitymesh.snapshot-comparison/v1"
    assert result.json()["removed_count"] == 1
    assert result.json()["items"][0]["after"] is None


@pytest.mark.anyio
async def test_api_auth_validation_and_unavailable_service() -> None:
    app = app_with_comparisons(None)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        params = {"base_snapshot_id": str(uuid4()), "target_snapshot_id": str(uuid4())}
        assert (await client.get("/api/v1/snapshots/compare", params=params)).status_code == 401
        headers = {"Authorization": f"Bearer {TOKEN}"}
        for bad in ({"limit": 101}, {"limit": 0}, {"cursor": "bad"}, {"base_snapshot_id": "bad"}):
            response = await client.get(
                "/api/v1/snapshots/compare", params=params | bad, headers=headers
            )
            assert response.status_code == 422
            assert response.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"
        response = await client.get("/api/v1/snapshots/compare", params=params, headers=headers)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "COMPARISON_UNAVAILABLE"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "code,status",
    [
        ("COMPARISON_NOT_READY", 409),
        ("COMPARISON_SCOPE_MISMATCH", 409),
        ("COMPARISON_SOURCE_INVALID", 503),
        ("SNAPSHOT_NOT_FOUND", 404),
        ("COMPARISON_TOO_LARGE", 413),
        ("COMPARISON_UNAVAILABLE", 503),
    ],
)
async def test_api_comparison_errors_are_reason_coded(code: str, status: int) -> None:
    class FailingService:
        async def compare(self, *args, **kwargs):
            raise ComparisonError(code, "Safe comparison failure.", status)

    app = app_with_comparisons(FailingService())
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/api/v1/snapshots/compare",
            params={
                "base_snapshot_id": str(uuid4()),
                "target_snapshot_id": str(uuid4()),
            },
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
