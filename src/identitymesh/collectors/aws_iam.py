"""Read-only AWS IAM role collection with explicit partial-failure semantics."""

from collections.abc import Callable, Iterator, Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Protocol, cast
from uuid import UUID

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import BotoCoreError, ClientError  # type: ignore[import-untyped]
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationError,
    field_validator,
    model_validator,
)

COLLECTOR_VERSION = "aws-iam-role/0.1"
AwsOperation = Literal["sts:GetCallerIdentity", "iam:ListRoles"]


class CollectionStatus(str, Enum):
    """Completeness of a provider collection result."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class CollectionReasonCode(str, Enum):
    """Stable reason codes for provider collection gaps."""

    ACCESS_DENIED = "AWS_ACCESS_DENIED"
    AUTHENTICATION_FAILED = "AWS_AUTHENTICATION_FAILED"
    THROTTLED = "AWS_THROTTLED"
    SERVICE_UNAVAILABLE = "AWS_SERVICE_UNAVAILABLE"
    CONNECTION_FAILED = "AWS_CONNECTION_FAILED"
    API_ERROR = "AWS_API_ERROR"
    MALFORMED_RESPONSE = "AWS_MALFORMED_RESPONSE"


class CollectionGap(BaseModel):
    """A provider capability or object that could not be collected safely."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    operation: AwsOperation
    reason_code: CollectionReasonCode
    retryable: bool
    message: str = Field(min_length=1, max_length=200)


class AwsRoleEvidence(BaseModel):
    """Validated provider facts for one IAM role."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["aws.iam.role/v1"] = "aws.iam.role/v1"
    provider: Literal["aws"] = "aws"
    object_type: Literal["iam_role"] = "iam_role"
    snapshot_id: UUID
    source_id: str = Field(min_length=1, max_length=2048)
    account_id: str = Field(pattern=r"^[0-9]{12}$")
    collector_principal_arn: str = Field(min_length=1, max_length=2048)
    collected_at: datetime
    collector_version: str = Field(pattern=r"^[A-Za-z0-9._/+\-]{1,128}$")

    role_id: str = Field(min_length=1, max_length=128)
    role_name: str = Field(min_length=1, max_length=64)
    arn: str = Field(min_length=1, max_length=2048)
    path: str = Field(min_length=1, max_length=512)
    created_at: datetime
    assume_role_policy_document: dict[str, JsonValue]
    description: str | None = Field(default=None, max_length=1000)
    max_session_duration: int | None = Field(default=None, ge=3600, le=43200)
    permissions_boundary_arn: str | None = Field(default=None, max_length=2048)
    tags: dict[str, str] = Field(default_factory=dict)
    last_used_at: datetime | None = None
    last_used_region: str | None = Field(default=None, max_length=64)

    @field_validator("collected_at", "created_at", "last_used_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("timestamps must include a timezone")
        return value

    @model_validator(mode="after")
    def require_consistent_source(self) -> "AwsRoleEvidence":
        if self.source_id != self.arn or _account_from_arn(self.arn) != self.account_id:
            raise ValueError("source identity must match the validated AWS role ARN")
        return self


class AwsRoleCollection(BaseModel):
    """One IAM role collection attempt and its completeness metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["aws.iam.role.collection/v1"] = "aws.iam.role.collection/v1"
    snapshot_id: UUID
    collected_at: datetime
    status: CollectionStatus
    account_id: str | None = Field(default=None, pattern=r"^[0-9]{12}$")
    collector_principal_arn: str | None = Field(default=None, max_length=2048)
    roles: tuple[AwsRoleEvidence, ...] = ()
    gaps: tuple[CollectionGap, ...] = ()

    @field_validator("collected_at")
    @classmethod
    def require_collection_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("collected_at must include a timezone")
        return value

    @model_validator(mode="after")
    def require_consistent_status(self) -> "AwsRoleCollection":
        has_identity = self.account_id is not None and self.collector_principal_arn is not None
        if (self.account_id is None) != (self.collector_principal_arn is None):
            raise ValueError("collector account and principal must be present together")
        if self.status is CollectionStatus.COMPLETE and (self.gaps or not has_identity):
            raise ValueError("complete collection cannot contain gaps or omit identity")
        if self.status is CollectionStatus.PARTIAL and (not self.gaps or not has_identity):
            raise ValueError("partial collection requires identity and collection gaps")
        if self.status is CollectionStatus.FAILED and (self.roles or not self.gaps):
            raise ValueError("failed collection requires gaps and cannot contain roles")
        return self


class AwsIamApi(Protocol):
    """Minimal AWS operations required by the role collector."""

    def get_caller_identity(self) -> Mapping[str, object]: ...

    def iter_role_pages(self) -> Iterator[Mapping[str, object]]: ...


class Boto3AwsIamApi:
    """Boto3 adapter configured with bounded timeouts and adaptive retries."""

    def __init__(
        self,
        session: Any | None = None,
        *,
        connect_timeout_seconds: float = 3.0,
        read_timeout_seconds: float = 10.0,
        max_attempts: int = 5,
    ) -> None:
        if connect_timeout_seconds <= 0 or read_timeout_seconds <= 0:
            raise ValueError("AWS client timeouts must be positive")
        if not 1 <= max_attempts <= 10:
            raise ValueError("AWS retry attempts must be between 1 and 10")

        aws_session = session or boto3.Session()
        configuration = Config(
            connect_timeout=connect_timeout_seconds,
            read_timeout=read_timeout_seconds,
            retries={"mode": "adaptive", "max_attempts": max_attempts},
            user_agent_extra=f"IdentityMesh/{COLLECTOR_VERSION}",
        )
        self._sts = aws_session.client("sts", config=configuration)
        self._iam = aws_session.client("iam", config=configuration)

    def get_caller_identity(self) -> Mapping[str, object]:
        return cast(Mapping[str, object], self._sts.get_caller_identity())

    def iter_role_pages(self) -> Iterator[Mapping[str, object]]:
        paginator = self._iam.get_paginator("list_roles")
        yield from paginator.paginate()


class AwsIamRoleCollector:
    """Collect IAM role facts without deriving access or trust conclusions."""

    def __init__(
        self,
        api: AwsIamApi,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._api = api
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def collect(self, snapshot_id: UUID) -> AwsRoleCollection:
        collected_at = self._clock()
        try:
            identity = self._api.get_caller_identity()
            account_id, principal_arn = _parse_caller_identity(identity)
        except ClientError as error:
            gap = _gap_from_client_error("sts:GetCallerIdentity", error)
            return _failed_collection(snapshot_id, collected_at, gap)
        except BotoCoreError:
            gap = _connection_gap("sts:GetCallerIdentity")
            return _failed_collection(snapshot_id, collected_at, gap)
        except (KeyError, TypeError, ValueError):
            gap = _malformed_gap("sts:GetCallerIdentity")
            return _failed_collection(snapshot_id, collected_at, gap)

        roles: list[AwsRoleEvidence] = []
        gaps: list[CollectionGap] = []
        try:
            for page in self._api.iter_role_pages():
                if not isinstance(page, Mapping):
                    _append_gap(gaps, _malformed_gap("iam:ListRoles"))
                    continue
                raw_roles = page.get("Roles")
                if not isinstance(raw_roles, list):
                    _append_gap(gaps, _malformed_gap("iam:ListRoles"))
                    continue
                for raw_role in raw_roles:
                    try:
                        roles.append(
                            _parse_role(
                                raw_role,
                                snapshot_id=snapshot_id,
                                account_id=account_id,
                                principal_arn=principal_arn,
                                collected_at=collected_at,
                            )
                        )
                    except (KeyError, TypeError, ValueError, ValidationError):
                        _append_gap(gaps, _malformed_gap("iam:ListRoles"))
        except ClientError as error:
            _append_gap(gaps, _gap_from_client_error("iam:ListRoles", error))
        except BotoCoreError:
            _append_gap(gaps, _connection_gap("iam:ListRoles"))

        status = CollectionStatus.PARTIAL if gaps else CollectionStatus.COMPLETE
        if gaps and not roles:
            status = CollectionStatus.FAILED
        return AwsRoleCollection(
            snapshot_id=snapshot_id,
            collected_at=collected_at,
            status=status,
            account_id=account_id,
            collector_principal_arn=principal_arn,
            roles=tuple(roles),
            gaps=tuple(gaps),
        )


def _parse_caller_identity(identity: Mapping[str, object]) -> tuple[str, str]:
    account_id = identity["Account"]
    principal_arn = identity["Arn"]
    if not isinstance(account_id, str) or not account_id.isdigit() or len(account_id) != 12:
        raise ValueError("AWS returned an invalid account identifier")
    if not isinstance(principal_arn, str):
        raise ValueError("AWS returned an invalid caller ARN")
    arn_parts = principal_arn.split(":", 5)
    if (
        len(arn_parts) != 6
        or arn_parts[0] != "arn"
        or arn_parts[2] not in {"iam", "sts"}
        or arn_parts[4] != account_id
        or not arn_parts[5]
    ):
        raise ValueError("AWS caller ARN did not match the collected account")
    return account_id, principal_arn


def _parse_role(
    raw_role: object,
    *,
    snapshot_id: UUID,
    account_id: str,
    principal_arn: str,
    collected_at: datetime,
) -> AwsRoleEvidence:
    if not isinstance(raw_role, Mapping):
        raise TypeError("AWS role must be a mapping")

    arn = raw_role["Arn"]
    if not isinstance(arn, str) or _account_from_arn(arn) != account_id:
        raise ValueError("AWS role ARN did not match the collected account")

    trust_policy = raw_role["AssumeRolePolicyDocument"]
    if not isinstance(trust_policy, dict):
        raise TypeError("AWS role trust policy must be an object")

    permissions_boundary = raw_role.get("PermissionsBoundary")
    boundary_arn: str | None = None
    if permissions_boundary is not None:
        if not isinstance(permissions_boundary, Mapping):
            raise TypeError("AWS permissions boundary must be an object")
        raw_boundary_arn = permissions_boundary.get("PermissionsBoundaryArn")
        if raw_boundary_arn is not None and not isinstance(raw_boundary_arn, str):
            raise TypeError("AWS permissions boundary ARN must be text")
        boundary_arn = raw_boundary_arn

    last_used = raw_role.get("RoleLastUsed")
    last_used_at: datetime | None = None
    last_used_region: str | None = None
    if last_used is not None:
        if not isinstance(last_used, Mapping):
            raise TypeError("AWS last-used metadata must be an object")
        raw_last_used_at = last_used.get("LastUsedDate")
        raw_last_used_region = last_used.get("Region")
        if raw_last_used_at is not None and not isinstance(raw_last_used_at, datetime):
            raise TypeError("AWS last-used date must be a timestamp")
        if raw_last_used_region is not None and not isinstance(raw_last_used_region, str):
            raise TypeError("AWS last-used region must be text")
        last_used_at = raw_last_used_at
        last_used_region = raw_last_used_region

    return AwsRoleEvidence(
        snapshot_id=snapshot_id,
        source_id=arn,
        account_id=account_id,
        collector_principal_arn=principal_arn,
        collected_at=collected_at,
        collector_version=COLLECTOR_VERSION,
        role_id=raw_role["RoleId"],
        role_name=raw_role["RoleName"],
        arn=arn,
        path=raw_role["Path"],
        created_at=raw_role["CreateDate"],
        assume_role_policy_document=trust_policy,
        description=raw_role.get("Description"),
        max_session_duration=raw_role.get("MaxSessionDuration"),
        permissions_boundary_arn=boundary_arn,
        tags=_parse_tags(raw_role.get("Tags", [])),
        last_used_at=last_used_at,
        last_used_region=last_used_region,
    )


def _parse_tags(raw_tags: object) -> dict[str, str]:
    if not isinstance(raw_tags, list):
        raise TypeError("AWS tags must be a list")
    tags: dict[str, str] = {}
    for raw_tag in raw_tags:
        if not isinstance(raw_tag, Mapping):
            raise TypeError("AWS tag must be an object")
        key = raw_tag.get("Key")
        value = raw_tag.get("Value")
        if not isinstance(key, str) or not isinstance(value, str) or key in tags:
            raise ValueError("AWS tag was invalid or duplicated")
        tags[key] = value
    return tags


def _account_from_arn(arn: str) -> str:
    parts = arn.split(":", 5)
    valid = (
        len(parts) == 6 and parts[0] == "arn" and parts[2] == "iam" and parts[5].startswith("role/")
    )
    if not valid:
        raise ValueError("AWS returned an invalid IAM role ARN")
    return parts[4]


def _failed_collection(
    snapshot_id: UUID,
    collected_at: datetime,
    gap: CollectionGap,
) -> AwsRoleCollection:
    return AwsRoleCollection(
        snapshot_id=snapshot_id,
        collected_at=collected_at,
        status=CollectionStatus.FAILED,
        gaps=(gap,),
    )


def _append_gap(gaps: list[CollectionGap], gap: CollectionGap) -> None:
    if not any(
        existing.operation == gap.operation and existing.reason_code is gap.reason_code
        for existing in gaps
    ):
        gaps.append(gap)


def _gap_from_client_error(operation: AwsOperation, error: ClientError) -> CollectionGap:
    error_data = error.response.get("Error", {})
    provider_code = error_data.get("Code", "") if isinstance(error_data, Mapping) else ""

    if provider_code in {"AccessDenied", "AccessDeniedException", "UnauthorizedOperation"}:
        reason_code = CollectionReasonCode.ACCESS_DENIED
        retryable = False
        message = "AWS denied the required read-only operation."
    elif provider_code in {"ExpiredToken", "InvalidClientTokenId", "UnrecognizedClientException"}:
        reason_code = CollectionReasonCode.AUTHENTICATION_FAILED
        retryable = False
        message = "AWS credentials could not authenticate the collection request."
    elif provider_code in {"Throttling", "ThrottlingException", "TooManyRequestsException"}:
        reason_code = CollectionReasonCode.THROTTLED
        retryable = True
        message = "AWS throttled the collection request after configured retries."
    elif provider_code in {"InternalFailure", "ServiceFailure", "ServiceUnavailable"}:
        reason_code = CollectionReasonCode.SERVICE_UNAVAILABLE
        retryable = True
        message = "AWS could not complete the collection request."
    else:
        reason_code = CollectionReasonCode.API_ERROR
        retryable = False
        message = "AWS returned an unclassified error for the collection request."

    return CollectionGap(
        operation=operation,
        reason_code=reason_code,
        retryable=retryable,
        message=message,
    )


def _connection_gap(operation: AwsOperation) -> CollectionGap:
    return CollectionGap(
        operation=operation,
        reason_code=CollectionReasonCode.CONNECTION_FAILED,
        retryable=True,
        message="The AWS endpoint could not be reached after configured retries.",
    )


def _malformed_gap(operation: AwsOperation) -> CollectionGap:
    return CollectionGap(
        operation=operation,
        reason_code=CollectionReasonCode.MALFORMED_RESPONSE,
        retryable=False,
        message="AWS returned data that did not match the expected schema.",
    )
