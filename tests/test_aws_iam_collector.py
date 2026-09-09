from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from pydantic import ValidationError

from identitymesh.collectors.aws_iam import (
    AwsIamRoleCollector,
    AwsRoleCollection,
    Boto3AwsIamApi,
    CollectionGap,
    CollectionReasonCode,
    CollectionStatus,
)

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
ACCOUNT_ID = "123456789012"
CALLER_ARN = f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/IdentityMeshCollector/run"


def _role(name: str = "ApplicationRole") -> dict[str, object]:
    return {
        "Path": "/application/",
        "RoleName": name,
        "RoleId": "AROABCDEFGHIJKLMNOP",
        "Arn": f"arn:aws:iam::{ACCOUNT_ID}:role/application/{name}",
        "CreateDate": NOW,
        "AssumeRolePolicyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                }
            ],
        },
        "Description": "Synthetic application role",
        "MaxSessionDuration": 3600,
        "PermissionsBoundary": {
            "PermissionsBoundaryType": "Policy",
            "PermissionsBoundaryArn": f"arn:aws:iam::{ACCOUNT_ID}:policy/Boundary",
        },
        "Tags": [{"Key": "Environment", "Value": "test"}],
        "RoleLastUsed": {"LastUsedDate": NOW, "Region": "us-east-1"},
    }


def _client_error(code: str, operation: str = "ListRoles") -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "provider detail must not be exposed"}},
        operation,
    )


class FakeAwsIamApi:
    def __init__(
        self,
        pages: list[Mapping[str, object] | Exception],
        identity: Mapping[str, object] | Exception | None = None,
    ) -> None:
        self.pages = pages
        self.identity = {"Account": ACCOUNT_ID, "Arn": CALLER_ARN} if identity is None else identity

    def get_caller_identity(self) -> Mapping[str, object]:
        if isinstance(self.identity, Exception):
            raise self.identity
        return self.identity

    def iter_role_pages(self) -> Iterator[Mapping[str, object]]:
        for page in self.pages:
            if isinstance(page, Exception):
                raise page
            yield page


def test_collects_paginated_roles_with_provenance() -> None:
    snapshot_id = uuid4()
    api = FakeAwsIamApi([{"Roles": [_role("First")]}, {"Roles": [_role("Second")]}])

    result = AwsIamRoleCollector(api, clock=lambda: NOW).collect(snapshot_id)

    assert result.status is CollectionStatus.COMPLETE
    assert result.gaps == ()
    assert [role.role_name for role in result.roles] == ["First", "Second"]
    assert all(role.snapshot_id == snapshot_id for role in result.roles)
    assert all(role.source_id == role.arn for role in result.roles)
    assert result.roles[0].tags == {"Environment": "test"}
    assert result.roles[0].permissions_boundary_arn is not None
    assert result.roles[0].permissions_boundary_arn.endswith(":policy/Boundary")


def test_complete_empty_collection_distinguishes_absence_from_unavailability() -> None:
    result = AwsIamRoleCollector(FakeAwsIamApi([{"Roles": []}]), clock=lambda: NOW).collect(uuid4())

    assert result.status is CollectionStatus.COMPLETE
    assert result.roles == ()
    assert result.gaps == ()


def test_malformed_role_is_reported_while_valid_evidence_is_retained() -> None:
    malformed = _role("Malformed")
    malformed["Arn"] = "arn:aws:iam::999999999999:role/Malformed"
    result = AwsIamRoleCollector(
        FakeAwsIamApi([{"Roles": [_role("Valid"), malformed]}]), clock=lambda: NOW
    ).collect(uuid4())

    assert result.status is CollectionStatus.PARTIAL
    assert [role.role_name for role in result.roles] == ["Valid"]
    assert result.gaps[0].reason_code is CollectionReasonCode.MALFORMED_RESPONSE


def test_repeated_malformed_objects_produce_one_bounded_gap() -> None:
    result = AwsIamRoleCollector(
        FakeAwsIamApi([{"Roles": [object(), object()]}, {}]), clock=lambda: NOW
    ).collect(uuid4())

    assert result.status is CollectionStatus.FAILED
    assert len(result.gaps) == 1
    assert result.gaps[0].reason_code is CollectionReasonCode.MALFORMED_RESPONSE


def test_access_denied_does_not_claim_roles_are_absent() -> None:
    result = AwsIamRoleCollector(
        FakeAwsIamApi([_client_error("AccessDenied")]), clock=lambda: NOW
    ).collect(uuid4())

    assert result.status is CollectionStatus.FAILED
    assert result.roles == ()
    assert result.gaps[0].reason_code is CollectionReasonCode.ACCESS_DENIED
    assert result.gaps[0].retryable is False
    assert "provider detail" not in result.gaps[0].message


def test_later_throttling_retains_roles_and_marks_collection_partial() -> None:
    result = AwsIamRoleCollector(
        FakeAwsIamApi([{"Roles": [_role()]}, _client_error("Throttling")]),
        clock=lambda: NOW,
    ).collect(uuid4())

    assert result.status is CollectionStatus.PARTIAL
    assert len(result.roles) == 1
    assert result.gaps[0].reason_code is CollectionReasonCode.THROTTLED
    assert result.gaps[0].retryable is True


@pytest.mark.parametrize(
    ("code", "reason", "retryable"),
    [
        ("ExpiredToken", CollectionReasonCode.AUTHENTICATION_FAILED, False),
        ("ServiceUnavailable", CollectionReasonCode.SERVICE_UNAVAILABLE, True),
        ("Unexpected", CollectionReasonCode.API_ERROR, False),
    ],
)
def test_provider_errors_map_to_safe_stable_reasons(
    code: str,
    reason: CollectionReasonCode,
    retryable: bool,
) -> None:
    result = AwsIamRoleCollector(
        FakeAwsIamApi([], identity=_client_error(code, "GetCallerIdentity")),
        clock=lambda: NOW,
    ).collect(uuid4())

    assert result.status is CollectionStatus.FAILED
    assert result.gaps[0].reason_code is reason
    assert result.gaps[0].retryable is retryable


def test_connection_failure_is_retryable_and_contains_no_endpoint() -> None:
    error = EndpointConnectionError(endpoint_url="https://sts.example.invalid/private")
    result = AwsIamRoleCollector(FakeAwsIamApi([], identity=error), clock=lambda: NOW).collect(
        uuid4()
    )

    assert result.gaps[0].reason_code is CollectionReasonCode.CONNECTION_FAILED
    assert result.gaps[0].retryable is True
    assert "example.invalid" not in result.gaps[0].message


@pytest.mark.parametrize(
    "identity",
    [
        {},
        {"Account": "not-an-account", "Arn": CALLER_ARN},
        {"Account": ACCOUNT_ID, "Arn": "not-an-arn"},
        {"Account": ACCOUNT_ID, "Arn": "arn:aws:sts::999999999999:assumed-role/Other/run"},
    ],
)
def test_malformed_caller_identity_fails_closed(identity: Mapping[str, object]) -> None:
    result = AwsIamRoleCollector(FakeAwsIamApi([], identity=identity), clock=lambda: NOW).collect(
        uuid4()
    )

    assert result.status is CollectionStatus.FAILED
    assert result.gaps[0].reason_code is CollectionReasonCode.MALFORMED_RESPONSE


def test_collection_model_rejects_complete_status_with_a_gap() -> None:
    gap = CollectionGap(
        operation="iam:ListRoles",
        reason_code=CollectionReasonCode.ACCESS_DENIED,
        retryable=False,
        message="AWS denied the required read-only operation.",
    )

    with pytest.raises(ValidationError, match="complete collection"):
        AwsRoleCollection(
            snapshot_id=uuid4(),
            collected_at=NOW,
            status=CollectionStatus.COMPLETE,
            account_id=ACCOUNT_ID,
            collector_principal_arn=CALLER_ARN,
            gaps=(gap,),
        )


class FakePaginator:
    def paginate(self) -> Iterator[Mapping[str, object]]:
        yield {"Roles": []}


class FakeClient:
    def __init__(self, service: str) -> None:
        self.service = service

    def get_caller_identity(self) -> Mapping[str, object]:
        return {"Account": ACCOUNT_ID, "Arn": CALLER_ARN}

    def get_paginator(self, operation: str) -> FakePaginator:
        assert self.service == "iam"
        assert operation == "list_roles"
        return FakePaginator()


class FakeSession:
    def __init__(self) -> None:
        self.services: list[str] = []

    def client(self, service: str, *, config: Any) -> FakeClient:
        assert config.connect_timeout == 3.0
        assert config.read_timeout == 10.0
        assert config.user_agent_extra == "IdentityMesh/aws-iam-role/0.1"
        self.services.append(service)
        return FakeClient(service)


def test_boto3_adapter_uses_only_sts_and_iam_clients() -> None:
    session = FakeSession()
    api = Boto3AwsIamApi(session)

    assert api.get_caller_identity()["Account"] == ACCOUNT_ID
    assert list(api.iter_role_pages()) == [{"Roles": []}]
    assert session.services == ["sts", "iam"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"connect_timeout_seconds": 0},
        {"read_timeout_seconds": -1},
        {"max_attempts": 0},
        {"max_attempts": 11},
    ],
)
def test_boto3_adapter_rejects_unsafe_retry_and_timeout_configuration(
    kwargs: dict[str, int],
) -> None:
    with pytest.raises(ValueError):
        Boto3AwsIamApi(FakeSession(), **kwargs)
