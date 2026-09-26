"""IAM user listing evidence with explicit completeness and attribute coverage."""

import re
from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timezone
from typing import Literal, Protocol
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from identitymesh.collectors.aws_iam import (
    CollectionGap,
    CollectionReasonCode,
    CollectionStatus,
    _append_gap,
    _connection_gap,
    _gap_from_client_error,
    _malformed_gap,
    _parse_caller_identity,
)

COLLECTOR_VERSION: Literal["aws-iam-user/0.1"] = "aws-iam-user/0.1"
MAX_USERS = 10_000
MAX_PAGES = 1_000


class AwsUserEvidence(BaseModel):
    """Facts supplied by ListUsers, with explicit limits on attribute coverage."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["aws.iam.user/v1"] = "aws.iam.user/v1"
    provider: Literal["aws"] = "aws"
    object_type: Literal["iam_user"] = "iam_user"
    snapshot_id: UUID
    source_id: str = Field(min_length=20, max_length=2048)
    account_id: str = Field(pattern=r"^[0-9]{12}$")
    collector_principal_arn: str = Field(min_length=20, max_length=2048)
    collected_at: datetime
    collector_version: Literal["aws-iam-user/0.1"] = COLLECTOR_VERSION
    user_id: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_]+$")
    user_name: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_+=,.@-]+$")
    arn: str = Field(min_length=20, max_length=2048)
    path: str = Field(min_length=1, max_length=512, pattern=r"^(/|/[\x21-\x7e]+/)$")
    created_at: datetime
    password_last_used: datetime | None = None
    uncollected_fields: tuple[Literal["tags"], Literal["permissions_boundary"]] = (
        "tags",
        "permissions_boundary",
    )

    @field_validator("collected_at", "created_at", "password_last_used")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.utcoffset() is None:
            raise ValueError("timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def require_consistent_source(self) -> "AwsUserEvidence":
        parts = self.arn.split(":", 5)
        if (
            len(parts) != 6
            or parts[0] != "arn"
            or re.fullmatch(r"aws(?:-[a-z0-9]+)*", parts[1]) is None
            or parts[2] != "iam"
            or parts[3] != ""
            or parts[4] != self.account_id
            or parts[5] != f"user{self.path}{self.user_name}"
            or self.source_id != self.arn
        ):
            raise ValueError("source identity must match the AWS user ARN, path, and name")
        _parse_user_caller({"Account": self.account_id, "Arn": self.collector_principal_arn})
        if self.collector_principal_arn.split(":", 5)[1] != parts[1]:
            raise ValueError("user and collector must belong to the same AWS partition")
        return self


class AwsUserCollection(BaseModel):
    """Complete means complete user listing, never complete entitlement coverage."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["aws.iam.user.collection/v1"] = "aws.iam.user.collection/v1"
    snapshot_id: UUID
    collected_at: datetime
    status: CollectionStatus
    account_id: str | None = Field(default=None, pattern=r"^[0-9]{12}$")
    collector_principal_arn: str | None = Field(default=None, max_length=2048)
    users: tuple[AwsUserEvidence, ...] = Field(default=(), max_length=MAX_USERS)
    gaps: tuple[CollectionGap, ...] = ()

    @field_validator("collected_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.utcoffset() is None:
            raise ValueError("collected_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_consistent_collection(self) -> "AwsUserCollection":
        if (self.account_id is None) != (self.collector_principal_arn is None):
            raise ValueError("collector account and principal must be present together")
        if self.account_id is not None:
            _parse_user_caller({"Account": self.account_id, "Arn": self.collector_principal_arn})
        if any(
            gap.operation not in {"sts:GetCallerIdentity", "iam:ListUsers"} for gap in self.gaps
        ):
            raise ValueError("user collection gaps must identify a user collector operation")
        if self.status is CollectionStatus.COMPLETE and (self.gaps or self.account_id is None):
            raise ValueError("complete collection requires identity and no gaps")
        if self.status is CollectionStatus.PARTIAL and (
            not self.users or not self.gaps or self.account_id is None
        ):
            raise ValueError("partial collection requires identity, users, and gaps")
        if self.status is CollectionStatus.FAILED and (self.users or not self.gaps):
            raise ValueError("failed collection requires gaps and no users")
        source_ids: set[str] = set()
        user_ids: set[str] = set()
        for user in self.users:
            if (
                user.snapshot_id != self.snapshot_id
                or user.collected_at != self.collected_at
                or user.account_id != self.account_id
                or user.collector_principal_arn != self.collector_principal_arn
            ):
                raise ValueError("user evidence must match its collection envelope")
            if user.source_id in source_ids or user.user_id in user_ids:
                raise ValueError("collection cannot contain duplicate user identities")
            source_ids.add(user.source_id)
            user_ids.add(user.user_id)
        return self


class AwsIamUserApi(Protocol):
    """Provider boundary shared by the SDK adapter and synthetic tests."""

    def get_caller_identity(self) -> Mapping[str, object]: ...

    def iter_user_pages(self) -> Iterator[Mapping[str, object]]: ...


class AwsIamUserCollector:
    """Collect account-scoped user metadata without inferring human ownership or access."""

    def __init__(
        self,
        api: AwsIamUserApi,
        *,
        allowed_account_id: str,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if re.fullmatch(r"[0-9]{12}", allowed_account_id) is None:
            raise ValueError("allowed_account_id must be a 12-digit AWS account ID")
        self._api = api
        self._allowed_account_id = allowed_account_id
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def collect(self, snapshot_id: UUID) -> AwsUserCollection:
        collected_at = self._clock()
        if collected_at.utcoffset() is None:
            raise ValueError("collection clock must include a timezone")
        try:
            account_id, principal_arn = _parse_user_caller(self._api.get_caller_identity())
        except ClientError as error:
            return _failed(
                snapshot_id, collected_at, _gap_from_client_error("sts:GetCallerIdentity", error)
            )
        except BotoCoreError:
            return _failed(snapshot_id, collected_at, _connection_gap("sts:GetCallerIdentity"))
        except (KeyError, TypeError, ValueError):
            return _failed(snapshot_id, collected_at, _malformed_gap("sts:GetCallerIdentity"))
        if account_id != self._allowed_account_id:
            return _failed(
                snapshot_id,
                collected_at,
                CollectionGap(
                    operation="sts:GetCallerIdentity",
                    reason_code=CollectionReasonCode.ACCOUNT_NOT_ALLOWED,
                    retryable=False,
                    message=(
                        "AWS credentials belong to an account that is not approved for collection."
                    ),
                ),
            )

        users: list[AwsUserEvidence] = []
        gaps: list[CollectionGap] = []
        source_ids: set[str] = set()
        user_ids: set[str] = set()
        markers: set[str] = set()
        finished = False
        try:
            for page_number, page in enumerate(self._api.iter_user_pages(), start=1):
                if page_number > MAX_PAGES:
                    _append_gap(gaps, _limit_gap())
                    break
                if finished or not isinstance(page, Mapping):
                    _append_gap(gaps, _malformed_gap("iam:ListUsers"))
                    break
                raw_users = page.get("Users")
                truncated = page.get("IsTruncated")
                if not isinstance(raw_users, list) or not isinstance(truncated, bool):
                    _append_gap(gaps, _malformed_gap("iam:ListUsers"))
                    break
                for raw_user in raw_users:
                    if len(users) >= MAX_USERS:
                        _append_gap(gaps, _limit_gap())
                        break
                    try:
                        user = _parse_user(
                            raw_user, snapshot_id, account_id, principal_arn, collected_at
                        )
                        if user.source_id in source_ids or user.user_id in user_ids:
                            raise ValueError("duplicate user identity")
                        users.append(user)
                        source_ids.add(user.source_id)
                        user_ids.add(user.user_id)
                    except (KeyError, TypeError, ValueError):
                        _append_gap(gaps, _malformed_gap("iam:ListUsers"))
                if any(gap.reason_code is CollectionReasonCode.LIMIT_EXCEEDED for gap in gaps):
                    break
                if truncated:
                    marker = page.get("Marker")
                    if not isinstance(marker, str) or not marker or marker in markers:
                        _append_gap(gaps, _malformed_gap("iam:ListUsers"))
                        break
                    markers.add(marker)
                else:
                    finished = True
        except ClientError as error:
            _append_gap(gaps, _gap_from_client_error("iam:ListUsers", error))
        except BotoCoreError:
            _append_gap(gaps, _connection_gap("iam:ListUsers"))
        if not finished and not gaps:
            _append_gap(gaps, _malformed_gap("iam:ListUsers"))

        status = CollectionStatus.COMPLETE
        if gaps:
            status = CollectionStatus.PARTIAL if users else CollectionStatus.FAILED
        return AwsUserCollection(
            snapshot_id=snapshot_id,
            collected_at=collected_at,
            status=status,
            account_id=account_id,
            collector_principal_arn=principal_arn,
            users=tuple(users),
            gaps=tuple(gaps),
        )


def _parse_user_caller(identity: Mapping[str, object]) -> tuple[str, str]:
    account_id, principal_arn = _parse_caller_identity(identity)
    parts = principal_arn.split(":", 5)
    if (
        re.fullmatch(r"[0-9]{12}", account_id) is None
        or re.fullmatch(r"aws(?:-[a-z0-9]+)*", parts[1]) is None
        or parts[3] != ""
        or len(principal_arn) > 2048
    ):
        raise ValueError("AWS returned an invalid caller identity")
    return account_id, principal_arn


def _parse_user(
    raw_user: object,
    snapshot_id: UUID,
    account_id: str,
    principal_arn: str,
    collected_at: datetime,
) -> AwsUserEvidence:
    if not isinstance(raw_user, Mapping):
        raise TypeError("AWS user must be a mapping")
    # Select documented listing attributes; never persist arbitrary provider response fields.
    return AwsUserEvidence(
        snapshot_id=snapshot_id,
        source_id=raw_user["Arn"],
        account_id=account_id,
        collector_principal_arn=principal_arn,
        collected_at=collected_at,
        user_id=raw_user["UserId"],
        user_name=raw_user["UserName"],
        arn=raw_user["Arn"],
        path=raw_user["Path"],
        created_at=raw_user["CreateDate"],
        password_last_used=raw_user.get("PasswordLastUsed"),
    )


def _failed(snapshot_id: UUID, collected_at: datetime, gap: CollectionGap) -> AwsUserCollection:
    return AwsUserCollection(
        snapshot_id=snapshot_id,
        collected_at=collected_at,
        status=CollectionStatus.FAILED,
        gaps=(gap,),
    )


def _limit_gap() -> CollectionGap:
    return CollectionGap(
        operation="iam:ListUsers",
        reason_code=CollectionReasonCode.LIMIT_EXCEEDED,
        retryable=False,
        message="AWS user listing exceeded the configured collection bounds.",
    )
