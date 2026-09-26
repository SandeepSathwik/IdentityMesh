"""Evidence-backed differences between complete retained IAM user observations."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

import asyncpg  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field

from identitymesh.aws_user_inventory import UserInventoryError, _load_users
from identitymesh.collectors.aws_iam import CollectionStatus
from identitymesh.collectors.aws_iam_users import MAX_USERS, AwsUserCollection, AwsUserEvidence
from identitymesh.normalizers.aws_iam_users import normalize_aws_user
from identitymesh.principal_store import PrincipalSourceError
from identitymesh.snapshot_comparison import ComparisonError

ComparedUserField = Literal["user_name", "arn", "path", "created_at"]
COMPARED_USER_FIELDS: tuple[ComparedUserField, ...] = ("user_name", "arn", "path", "created_at")


@dataclass(frozen=True, slots=True)
class UserComparisonSource:
    sequence_id: int
    collection: AwsUserCollection


class UserReference(BaseModel):
    """Safe evidence reference without password usage or collector session details."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot_id: UUID
    principal_id: UUID
    user_id: str
    display_name: str
    source_id: str
    collected_at: datetime

    @classmethod
    def from_user(cls, user: AwsUserEvidence) -> "UserReference":
        return cls(
            snapshot_id=user.snapshot_id,
            principal_id=normalize_aws_user(user).principal.principal_id,
            user_id=user.user_id,
            display_name=user.user_name,
            source_id=user.source_id,
            collected_at=user.collected_at,
        )


class UserChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    principal_id: UUID
    kind: Literal["added", "removed", "changed"]
    changed_fields: tuple[ComparedUserField, ...] = ()
    before: UserReference | None
    after: UserReference | None


class UserComparisonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.user-comparison/v1"] = "identitymesh.user-comparison/v1"
    base_snapshot_id: UUID
    target_snapshot_id: UUID
    account_id: str
    partition: str
    base_collected_at: datetime
    target_collected_at: datetime
    compared_fields: tuple[ComparedUserField, ...] = COMPARED_USER_FIELDS
    added_count: int = Field(ge=0)
    removed_count: int = Field(ge=0)
    changed_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    items: tuple[UserChange, ...]
    next_cursor: UUID | None


def _complete_collection(source: UserComparisonSource) -> AwsUserCollection:
    if len(source.collection.users) > MAX_USERS:
        raise ComparisonError("COMPARISON_TOO_LARGE", "A snapshot exceeds the user limit.", 413)
    try:
        # Revalidate nested models as well as the envelope at this read boundary.
        collection = AwsUserCollection.model_validate_json(source.collection.model_dump_json())
    except ValueError as error:
        raise ComparisonError(
            "COMPARISON_SOURCE_INVALID", "Stored user evidence is inconsistent.", 503
        ) from error
    if collection.status is not CollectionStatus.COMPLETE:
        raise ComparisonError("COMPARISON_INCOMPLETE", "Both user observations must be complete.")
    return collection


def compare_user_sources(
    base: UserComparisonSource,
    target: UserComparisonSource,
    *,
    limit: int = 50,
    cursor: UUID | None = None,
) -> UserComparisonResponse:
    """Compare stable user identities; observation noise never implies an access change."""

    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    first, second = _complete_collection(base), _complete_collection(target)
    # Complete envelopes require account and caller, including complete-empty observations.
    assert first.collector_principal_arn is not None  # noqa: S101
    assert second.collector_principal_arn is not None  # noqa: S101
    assert first.account_id is not None  # noqa: S101
    partition = first.collector_principal_arn.split(":", 5)[1]
    if (
        first.account_id != second.account_id
        or partition != second.collector_principal_arn.split(":", 5)[1]
    ):
        raise ComparisonError(
            "COMPARISON_SCOPE_MISMATCH", "User observations must share an account and partition."
        )
    if base.sequence_id > target.sequence_id:
        raise ComparisonError(
            "COMPARISON_ORDER_INVALID", "The base must not be newer than the target."
        )

    before = {normalize_aws_user(user).principal.principal_id: user for user in first.users}
    after = {normalize_aws_user(user).principal.principal_id: user for user in second.users}
    counts = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    changes: list[UserChange] = []
    for principal_id in sorted(before.keys() | after.keys()):
        old, new = before.get(principal_id), after.get(principal_id)
        fields: tuple[ComparedUserField, ...] = ()
        kind: Literal["added", "removed", "changed"]
        if old is None:
            kind = "added"
        elif new is None:
            kind = "removed"
        else:
            fields = tuple(
                field
                for field in COMPARED_USER_FIELDS
                if getattr(old, field) != getattr(new, field)
            )
            if not fields:
                counts["unchanged"] += 1
                continue
            kind = "changed"
        counts[kind] += 1
        if (cursor is None or principal_id > cursor) and len(changes) <= limit:
            changes.append(
                UserChange(
                    principal_id=principal_id,
                    kind=kind,
                    changed_fields=fields,
                    before=UserReference.from_user(old) if old else None,
                    after=UserReference.from_user(new) if new else None,
                )
            )
    page = tuple(changes[:limit])
    return UserComparisonResponse(
        base_snapshot_id=first.snapshot_id,
        target_snapshot_id=second.snapshot_id,
        account_id=first.account_id,
        partition=partition,
        base_collected_at=first.collected_at,
        target_collected_at=second.collected_at,
        added_count=counts["added"],
        removed_count=counts["removed"],
        changed_count=counts["changed"],
        unchanged_count=counts["unchanged"],
        total_count=counts["added"] + counts["removed"] + counts["changed"],
        items=page,
        next_cursor=page[-1].principal_id if len(changes) > limit else None,
    )


class UserComparisonService:
    """Validate both observations in one consistent, bounded, read-only transaction."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def compare(
        self, base_id: UUID, target_id: UUID, *, limit: int = 50, cursor: UUID | None = None
    ) -> UserComparisonResponse:
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        try:
            async with self._pool.acquire() as connection:
                async with connection.transaction(isolation="repeatable_read", readonly=True):
                    await connection.execute("SET LOCAL statement_timeout = '5s'")
                    base = await _load_source(connection, base_id)
                    target = (
                        base if base_id == target_id else await _load_source(connection, target_id)
                    )
            return compare_user_sources(base, target, limit=limit, cursor=cursor)
        except UserInventoryError as error:
            code = {
                "SNAPSHOT_NOT_FOUND": "SNAPSHOT_NOT_FOUND",
                "USER_INVENTORY_SCOPE_MISMATCH": "COMPARISON_SCOPE_MISMATCH",
                "USER_INVENTORY_NOT_COLLECTED": "COMPARISON_NOT_READY",
            }.get(error.reason_code, "COMPARISON_SOURCE_INVALID")
            raise ComparisonError(code, str(error), error.status_code) from error
        except (PrincipalSourceError, ValueError, TypeError, KeyError) as error:
            raise ComparisonError(
                "COMPARISON_SOURCE_INVALID", "Stored user comparison evidence is inconsistent.", 503
            ) from error
        except (asyncpg.PostgresError, OSError, asyncio.TimeoutError) as error:
            raise ComparisonError(
                "COMPARISON_UNAVAILABLE", "User comparison is temporarily unavailable.", 503
            ) from error


async def _load_source(connection: asyncpg.Connection, snapshot_id: UUID) -> UserComparisonSource:
    collection, _, _ = await _load_users(connection, snapshot_id)
    sequence_id = await connection.fetchval(
        "SELECT sequence_id FROM snapshots WHERE snapshot_id = $1", snapshot_id
    )
    return UserComparisonSource(sequence_id=sequence_id, collection=collection)
