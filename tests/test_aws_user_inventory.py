import asyncio
import os
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from uuid import UUID, uuid4

import asyncpg  # type: ignore[import-untyped]
import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from test_data_api import FakeCoordinator, FakeInventory, _headers, _settings

from identitymesh.api import ApplicationServices
from identitymesh.aws_collection_service import AwsCollectionRunError
from identitymesh.aws_evidence_store import (
    CollectionPersistenceConflictError,
    CollectorVersionMismatchError,
    SnapshotNotCollectingError,
)
from identitymesh.aws_user_evidence_store import AwsIamUserEvidenceStore
from identitymesh.aws_user_inventory import AwsUserInventoryService, UserInventoryError
from identitymesh.collectors.aws_iam import CollectionGap, CollectionReasonCode, CollectionStatus
from identitymesh.collectors.aws_iam_users import (
    COLLECTOR_VERSION,
    AwsUserCollection,
    AwsUserEvidence,
)
from identitymesh.comparison_store import SnapshotComparisonService
from identitymesh.graph_projection import GraphProjectionError, project_principal
from identitymesh.identity_pipeline import (
    _AWS_COLLECTION_ADVISORY_LOCK,
    CollectionAlreadyRunningError,
)
from identitymesh.main import create_app
from identitymesh.normalizers.aws_iam_users import normalize_aws_user
from identitymesh.principals import PrincipalType
from identitymesh.snapshot_comparison import ComparisonError
from identitymesh.snapshot_store import SnapshotStore
from identitymesh.snapshots import SnapshotNotFoundError, SnapshotStatus

NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
ACCOUNT = "123456789012"
CALLER = f"arn:aws:sts::{ACCOUNT}:assumed-role/Collector/test"


def _user(snapshot_id: UUID, name: str = "Example", **changes: object) -> AwsUserEvidence:
    arn = f"arn:aws:iam::{ACCOUNT}:user/{name}"
    return AwsUserEvidence.model_validate(
        {
            "snapshot_id": snapshot_id,
            "source_id": arn,
            "account_id": ACCOUNT,
            "collector_principal_arn": CALLER,
            "collected_at": NOW,
            "user_id": f"AIDAEXAMPLE000000{name}",
            "user_name": name,
            "arn": arn,
            "path": "/",
            "created_at": NOW,
            "password_last_used": NOW,
            **changes,
        }
    )


def _gap() -> CollectionGap:
    return CollectionGap(
        operation="iam:ListUsers",
        reason_code=CollectionReasonCode.ACCESS_DENIED,
        retryable=False,
        message="AWS denied the required read-only operation.",
    )


def _collection(
    snapshot_id: UUID,
    status: CollectionStatus = CollectionStatus.COMPLETE,
    users: tuple[AwsUserEvidence, ...] | None = None,
) -> AwsUserCollection:
    return AwsUserCollection(
        snapshot_id=snapshot_id,
        collected_at=NOW,
        status=status,
        account_id=ACCOUNT,
        collector_principal_arn=CALLER,
        users=(_user(snapshot_id),) if users is None else users,
        gaps=() if status is CollectionStatus.COMPLETE else (_gap(),),
    )


def test_normalized_identity_is_stable_across_snapshot_and_rename() -> None:
    evidence = _user(uuid4())
    first = normalize_aws_user(evidence)
    renamed = normalize_aws_user(_user(uuid4(), "Renamed", user_id=evidence.user_id))
    assert first.principal.principal_id == renamed.principal.principal_id
    assert first.principal.principal_type is PrincipalType.CLOUD_USER
    assert first.principal.status is None
    assert first.principal.provenance.source_object_type == "iam_user"
    assert first.principal.provenance.snapshot_id == evidence.snapshot_id
    assert first.principal.provenance.classification.value == "observed"
    assert first.principal.external_id == evidence.user_id
    assert first.deferred_evidence_fields == ("path", "password_last_used", "uncollected_fields")
    assert "password_last_used" not in first.principal.model_dump_json()


def test_recreated_users_and_other_partitions_do_not_alias() -> None:
    evidence = _user(uuid4())
    first = normalize_aws_user(evidence).principal
    recreated = normalize_aws_user(_user(uuid4(), user_id="AIDARECREATED0000000")).principal
    china = normalize_aws_user(
        _user(
            uuid4(),
            arn=evidence.arn.replace("arn:aws:", "arn:aws-cn:"),
            source_id=evidence.arn.replace("arn:aws:", "arn:aws-cn:"),
            collector_principal_arn=CALLER.replace("arn:aws:", "arn:aws-cn:"),
        )
    ).principal
    assert len({first.principal_id, recreated.principal_id, china.principal_id}) == 3


def test_role_graph_explicitly_rejects_user_principals() -> None:
    with pytest.raises(GraphProjectionError):
        project_principal(normalize_aws_user(_user(uuid4())).principal)


def test_normalizer_rejects_unvalidated_input() -> None:
    with pytest.raises(TypeError, match="validated"):
        normalize_aws_user({})  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_store_rejects_unvalidated_or_bypassed_models_before_database_access() -> None:
    store = AwsIamUserEvidenceStore(object())
    with pytest.raises(TypeError, match="validated"):
        await store.persist_and_finalize({})  # type: ignore[arg-type]
    collection = _collection(uuid4())
    forged = collection.model_copy(
        update={"users": (collection.users[0].model_copy(update={"account_id": "999999999999"}),)}
    )
    with pytest.raises(ValidationError):
        await store.persist_and_finalize(forged)


@pytest.fixture
async def database() -> AsyncIterator[asyncpg.Pool]:
    dsn = os.getenv("IDENTITYMESH_TEST_POSTGRES_DSN")
    if dsn is None:
        pytest.skip("IDENTITYMESH_TEST_POSTGRES_DSN is not configured")
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    try:
        async with pool.acquire() as connection:
            await connection.execute("TRUNCATE snapshots CASCADE")
            await connection.execute(
                "INSERT INTO active_snapshot (singleton) VALUES (TRUE) "
                "ON CONFLICT (singleton) DO NOTHING"
            )
        yield pool
    finally:
        await pool.close()


class FakeCollector:
    def __init__(self, status: CollectionStatus = CollectionStatus.COMPLETE) -> None:
        self.status = status
        self.thread_id: int | None = None

    def collect(self, snapshot_id: UUID) -> AwsUserCollection:
        self.thread_id = threading.get_ident()
        return _collection(
            snapshot_id, self.status, () if self.status is CollectionStatus.FAILED else None
        )


@pytest.mark.anyio
@pytest.mark.parametrize("status", list(CollectionStatus))
async def test_persistence_finalization_and_concurrent_retry_are_atomic(
    database: asyncpg.Pool, status: CollectionStatus
) -> None:
    snapshots = SnapshotStore(database)
    prior = await snapshots.create("aws-iam-role/0.1")
    await snapshots.mark_collected(prior.snapshot_id)
    await snapshots.start_projection(prior.snapshot_id, "principal-graph/0.1")
    await snapshots.complete_projection(prior.snapshot_id)
    snapshot = await snapshots.create(COLLECTOR_VERSION)
    collection = _collection(
        snapshot.snapshot_id, status, () if status is CollectionStatus.FAILED else None
    )
    store = AwsIamUserEvidenceStore(database)
    results = await asyncio.gather(
        store.persist_and_finalize(collection), store.persist_and_finalize(collection)
    )
    assert sorted(result.created for result in results) == [False, True]
    assert all(
        result.snapshot_status
        is (
            SnapshotStatus.COLLECTED
            if status is CollectionStatus.COMPLETE
            else SnapshotStatus.FAILED
        )
        for result in results
    )
    assert (await snapshots.get_active()).snapshot_id == prior.snapshot_id
    service = AwsUserInventoryService(database, FakeCollector())
    page = await service.users(snapshot.snapshot_id)
    assert page.collection_status == status.value
    assert page.total_count == len(collection.users)
    assert len(page.gaps) == len(collection.gaps)
    assert "password_last_used" not in page.model_dump_json()
    async with database.acquire() as connection:
        for query in (
            "SELECT count(*) FROM provider_evidence WHERE snapshot_id = $1",
            "SELECT count(*) FROM principals WHERE snapshot_id = $1",
        ):
            assert await connection.fetchval(query, snapshot.snapshot_id) == len(collection.users)


@pytest.mark.anyio
async def test_complete_empty_and_failed_empty_remain_distinct(database: asyncpg.Pool) -> None:
    snapshots = SnapshotStore(database)
    store = AwsIamUserEvidenceStore(database)
    service = AwsUserInventoryService(database, FakeCollector())
    for status in (CollectionStatus.COMPLETE, CollectionStatus.FAILED):
        snapshot = await snapshots.create(COLLECTOR_VERSION)
        await store.persist_and_finalize(_collection(snapshot.snapshot_id, status, ()))
        page = await service.users(snapshot.snapshot_id)
        assert page.collection_status == status.value
        assert page.total_count == 0
        assert bool(page.gaps) is (status is CollectionStatus.FAILED)


@pytest.mark.anyio
async def test_conflicting_retry_and_wrong_scope_preserve_original(database: asyncpg.Pool) -> None:
    snapshots = SnapshotStore(database)
    store = AwsIamUserEvidenceStore(database)
    snapshot = await snapshots.create(COLLECTOR_VERSION)
    await store.persist_and_finalize(_collection(snapshot.snapshot_id))
    with pytest.raises(CollectionPersistenceConflictError):
        await store.persist_and_finalize(_collection(snapshot.snapshot_id, users=()))
    role_snapshot = await snapshots.create("aws-iam-role/0.1")
    with pytest.raises(CollectorVersionMismatchError):
        await store.persist_and_finalize(_collection(role_snapshot.snapshot_id))
    with pytest.raises(SnapshotNotFoundError):
        await store.persist_and_finalize(_collection(uuid4()))
    collecting = await snapshots.create(COLLECTOR_VERSION)
    await snapshots.mark_collected(collecting.snapshot_id)
    await snapshots.start_projection(collecting.snapshot_id, "test/1")
    with pytest.raises(SnapshotNotCollectingError):
        await store.persist_and_finalize(_collection(collecting.snapshot_id))


@pytest.mark.anyio
async def test_conflicting_principal_rolls_back_attempt_evidence_and_lifecycle(
    database: asyncpg.Pool,
) -> None:
    snapshot = await SnapshotStore(database).create(COLLECTOR_VERSION)
    # Seed inconsistent retained state to force a real database uniqueness failure.
    collection = _collection(snapshot.snapshot_id)
    user = collection.users[0]
    async with database.acquire() as connection:
        await connection.execute(
            """INSERT INTO provider_evidence (
                snapshot_id, provider, object_type, source_id, schema_version, provider_object_id,
                collected_at, collector_version, collector_principal_id, evidence
            ) VALUES ($1, 'aws', 'iam_user', $2, $3, $4, $5, $6, $7, $8::jsonb)""",
            snapshot.snapshot_id,
            user.source_id,
            user.schema_version,
            user.user_id,
            user.collected_at,
            user.collector_version,
            user.collector_principal_arn,
            user.model_dump_json(),
        )
    with pytest.raises(CollectionPersistenceConflictError):
        await AwsIamUserEvidenceStore(database).persist_and_finalize(collection)
    async with database.acquire() as connection:
        assert (
            await connection.fetchval("SELECT count(*) FROM aws_iam_user_collection_attempts") == 0
        )
        assert await connection.fetchval("SELECT count(*) FROM principals") == 0
        assert (
            await connection.fetchval(
                "SELECT status FROM snapshots WHERE snapshot_id = $1", snapshot.snapshot_id
            )
            == "collecting"
        )


@pytest.mark.anyio
async def test_collection_runs_off_event_loop_and_shares_role_lock(database: asyncpg.Pool) -> None:
    collector = FakeCollector()
    service = AwsUserInventoryService(database, collector)
    async with database.acquire() as connection:
        await connection.fetchval("SELECT pg_advisory_lock($1)", _AWS_COLLECTION_ADVISORY_LOCK)
        try:
            with pytest.raises(CollectionAlreadyRunningError):
                await service.run()
            assert collector.thread_id is None
        finally:
            await connection.fetchval(
                "SELECT pg_advisory_unlock($1)", _AWS_COLLECTION_ADVISORY_LOCK
            )
    run = await service.run()
    assert collector.thread_id != threading.get_ident()
    assert run.snapshot_status == "collected"
    assert run.activated is False
    assert await SnapshotStore(database).get_active() is None
    assert (await service.users(run.snapshot_id)).total_count == 1


@pytest.mark.anyio
@pytest.mark.parametrize("malformed", [False, True])
async def test_collector_failure_records_terminal_state_and_releases_lock(
    database: asyncpg.Pool, malformed: bool
) -> None:
    class BrokenCollector:
        def collect(self, snapshot_id: UUID) -> AwsUserCollection:
            if malformed:
                return _collection(uuid4())
            raise RuntimeError("sensitive-provider-detail")

    with pytest.raises(AwsCollectionRunError) as caught:
        await AwsUserInventoryService(database, BrokenCollector()).run()
    assert caught.value.reason_code == "AWS_COLLECTION_INTERNAL_ERROR"
    assert "sensitive-provider-detail" not in str(caught.value)
    async with database.acquire() as connection:
        assert (
            await connection.fetchval(
                "SELECT status FROM snapshots WHERE snapshot_id = $1", caught.value.snapshot_id
            )
            == "failed"
        )
    assert (
        await AwsUserInventoryService(database, FakeCollector()).run()
    ).snapshot_status == "collected"


@pytest.mark.anyio
async def test_snapshot_pagination_is_stable_and_scope_checked(database: asyncpg.Pool) -> None:
    snapshots = SnapshotStore(database)
    snapshot = await snapshots.create(COLLECTOR_VERSION)
    collection = _collection(
        snapshot.snapshot_id, users=tuple(_user(snapshot.snapshot_id, f"User{n}") for n in range(3))
    )
    await AwsIamUserEvidenceStore(database).persist_and_finalize(collection)
    service = AwsUserInventoryService(database, FakeCollector())
    first = await service.users(snapshot.snapshot_id, limit=2)
    last = await service.users(snapshot.snapshot_id, limit=2, cursor=first.next_cursor)
    assert first.total_count == last.total_count == 3
    assert len(first.items) == 2 and len(last.items) == 1 and last.next_cursor is None
    assert len({p.principal_id for p in first.items + last.items}) == 3
    with pytest.raises(UserInventoryError, match="does not exist"):
        await service.users(uuid4())
    role = await snapshots.create("aws-iam-role/0.1")
    with pytest.raises(UserInventoryError) as scope:
        await service.users(role.snapshot_id)
    assert scope.value.reason_code == "USER_INVENTORY_SCOPE_MISMATCH"
    unfinished = await snapshots.create(COLLECTOR_VERSION)
    with pytest.raises(UserInventoryError) as unfinished_error:
        await service.users(unfinished.snapshot_id)
    assert unfinished_error.value.reason_code == "USER_INVENTORY_NOT_COLLECTED"
    # Even if externally promoted, user scope is never eligible for role comparison.
    await snapshots.start_projection(snapshot.snapshot_id, "test/1")
    await snapshots.complete_projection(snapshot.snapshot_id)
    with pytest.raises(ComparisonError) as comparison:
        await SnapshotComparisonService(database).compare(
            snapshot.snapshot_id, snapshot.snapshot_id
        )
    assert comparison.value.reason_code == "COMPARISON_SCOPE_MISMATCH"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "corruption", ["principal", "evidence", "count", "missing", "gap", "lifecycle"]
)
async def test_reads_reject_inconsistent_retained_data(
    database: asyncpg.Pool, corruption: str
) -> None:
    run = await AwsUserInventoryService(database, FakeCollector()).run()
    sql = {
        "principal": "UPDATE principals SET display_name = 'Wrong' WHERE snapshot_id = $1",
        "evidence": "UPDATE provider_evidence SET object_type = 'iam_role' WHERE snapshot_id = $1",
        "count": (
            "UPDATE aws_iam_user_collection_attempts SET user_count = 2 WHERE snapshot_id = $1"
        ),
        "missing": "DELETE FROM provider_evidence WHERE snapshot_id = $1",
        "gap": """INSERT INTO aws_iam_user_collection_gaps (
                      snapshot_id, operation, reason_code, retryable, message)
                  VALUES ($1, 'iam:ListUsers', 'AWS_ACCESS_DENIED', FALSE, 'denied')""",
        "lifecycle": (
            "UPDATE snapshots SET status = 'failed', failed_at = now(), "
            "failure_code = 'UNEXPECTED' WHERE snapshot_id = $1"
        ),
    }[corruption]
    async with database.acquire() as connection:
        await connection.execute(sql, run.snapshot_id)
    with pytest.raises(UserInventoryError) as caught:
        await AwsUserInventoryService(database, FakeCollector()).users(run.snapshot_id)
    assert caught.value.reason_code == "USER_INVENTORY_SOURCE_INVALID"


@pytest.mark.anyio
async def test_authenticated_http_collection_and_paginated_evidence_flow(
    database: asyncpg.Pool,
) -> None:
    service = AwsUserInventoryService(database, FakeCollector())
    app = create_app(
        _settings(),
        readiness_probes={},
        services=ApplicationServices(
            coordinator=FakeCoordinator(),
            inventory=FakeInventory(),
            users=service,
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        denied = await client.post("/api/v1/collections/aws/iam/users")
        assert denied.status_code == 401
        run = await client.post("/api/v1/collections/aws/iam/users", headers=_headers())
        assert run.status_code == 200
        assert run.json()["activated"] is False
        snapshot_id = run.json()["snapshot_id"]
        path = f"/api/v1/snapshots/{snapshot_id}/users"
        assert (await client.get(path)).status_code == 401
        page = await client.get(path, headers=_headers())
        assert page.status_code == 200
        assert page.json()["schema_version"] == "identitymesh.user-inventory-page/v1"
        assert page.json()["items"][0]["principal_type"] == "cloud_user"
        assert page.json()["uncollected_fields"] == ["tags", "permissions_boundary"]
        assert "password_last_used" not in page.text
        for query in ("limit=0", "limit=101", "cursor=not-a-uuid"):
            invalid = await client.get(f"{path}?{query}", headers=_headers())
            assert invalid.status_code == 422
        missing = await client.get(f"/api/v1/snapshots/{uuid4()}/users", headers=_headers())
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "SNAPSHOT_NOT_FOUND"
    assert await SnapshotStore(database).get_active() is None


@pytest.mark.anyio
@pytest.mark.parametrize("failure", ["busy", "collection", "read", "unconfigured"])
async def test_user_api_returns_safe_reason_coded_failures(failure: str) -> None:
    class FailingService:
        async def run(self) -> None:
            if failure == "busy":
                raise CollectionAlreadyRunningError("sensitive-provider-detail")
            raise AwsCollectionRunError(uuid4(), "AWS_COLLECTION_INTERNAL_ERROR")

        async def users(self, snapshot_id: UUID, *, limit: int, cursor: UUID | None) -> None:
            raise UserInventoryError("USER_INVENTORY_SOURCE_INVALID", "Stored evidence is invalid.")

    app = create_app(
        _settings(),
        readiness_probes={},
        services=ApplicationServices(
            coordinator=FakeCoordinator(),
            inventory=FakeInventory(),
            users=None if failure == "unconfigured" else FailingService(),
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = (
            await client.get(f"/api/v1/snapshots/{uuid4()}/users", headers=_headers())
            if failure == "read"
            else await client.post("/api/v1/collections/aws/iam/users", headers=_headers())
        )
        assert (
            response.status_code
            == {"busy": 409, "collection": 500, "read": 503, "unconfigured": 503}[failure]
        )
        assert "sensitive-provider-detail" not in response.text
        assert response.json()["error"]["code"]


@pytest.mark.anyio
async def test_migration_downgrade_refuses_retained_user_data(
    database: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IDENTITYMESH_POSTGRES_DSN", os.environ["IDENTITYMESH_TEST_POSTGRES_DSN"])
    run = await AwsUserInventoryService(database, FakeCollector()).run()
    config = Config(toml_file="pyproject.toml")
    with pytest.raises(RuntimeError, match="retained"):
        await asyncio.to_thread(command.downgrade, config, "20260915_0002")
    assert (
        await AwsUserInventoryService(database, FakeCollector()).users(run.snapshot_id)
    ).total_count == 1


@pytest.mark.anyio
async def test_empty_user_migration_round_trip_preserves_role_snapshot(
    database: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("IDENTITYMESH_POSTGRES_DSN", os.environ["IDENTITYMESH_TEST_POSTGRES_DSN"])
    snapshot = await SnapshotStore(database).create("aws-iam-role/0.1")
    config = Config(toml_file="pyproject.toml")
    try:
        await asyncio.to_thread(command.downgrade, config, "20260915_0002")
        async with database.acquire() as connection:
            assert (
                await connection.fetchval("SELECT to_regclass('aws_iam_user_collection_attempts')")
                is None
            )
            assert (
                await connection.fetchval(
                    "SELECT count(*) FROM snapshots WHERE snapshot_id = $1", snapshot.snapshot_id
                )
                == 1
            )
    finally:
        await asyncio.to_thread(command.upgrade, config, "head")
