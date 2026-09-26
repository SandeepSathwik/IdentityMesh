from collections.abc import Iterator, Mapping
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import boto3
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from botocore.stub import Stubber
from pydantic import ValidationError

from identitymesh.collectors import aws_iam_users
from identitymesh.collectors.aws_iam import (
    Boto3AwsIamApi,
    CollectionReasonCode,
    CollectionStatus,
)
from identitymesh.collectors.aws_iam_users import (
    AwsIamUserCollector,
    AwsUserCollection,
    AwsUserEvidence,
)

NOW = datetime(2026, 9, 25, 12, tzinfo=timezone.utc)
ACCOUNT_ID = "123456789012"
CALLER_ARN = f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/Collector/test"


def _user(name: str = "Example") -> dict[str, Any]:
    return {
        "Path": "/engineering/",
        "UserName": name,
        "UserId": f"AIDAEXAMPLE000000{name}",
        "Arn": f"arn:aws:iam::{ACCOUNT_ID}:user/engineering/{name}",
        "CreateDate": NOW,
    }


def _page(*users: object, marker: str | None = None) -> dict[str, Any]:
    page: dict[str, Any] = {"Users": list(users), "IsTruncated": marker is not None}
    if marker is not None:
        page["Marker"] = marker
    return page


class FakeApi:
    def __init__(self, pages: list[Any], identity: Any = None) -> None:
        self.pages = pages
        self.identity = {"Account": ACCOUNT_ID, "Arn": CALLER_ARN} if identity is None else identity
        self.list_calls = 0

    def get_caller_identity(self) -> Mapping[str, object]:
        if isinstance(self.identity, Exception):
            raise self.identity
        return self.identity  # type: ignore[no-any-return]

    def iter_user_pages(self) -> Iterator[Mapping[str, object]]:
        self.list_calls += 1
        for page in self.pages:
            if isinstance(page, Exception):
                raise page
            yield page


def _collect(pages: list[Any]) -> AwsUserCollection:
    return AwsIamUserCollector(
        FakeApi(pages), allowed_account_id=ACCOUNT_ID, clock=lambda: NOW
    ).collect(uuid4())


def _error(code: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": code, "Message": "sensitive-provider-detail"}}, "ListUsers"
    )


def test_collects_all_pages_and_preserves_observed_provenance() -> None:
    first = _user()
    first["PasswordLastUsed"] = NOW
    result = _collect([_page(first, marker="next"), _page(_user("Second"))])
    assert result.status is CollectionStatus.COMPLETE
    assert [user.user_name for user in result.users] == ["Example", "Second"]
    assert result.users[0].password_last_used == NOW
    assert result.users[1].password_last_used is None
    for user in result.users:
        assert user.snapshot_id == result.snapshot_id
        assert user.collected_at == NOW
        assert user.collector_principal_arn == CALLER_ARN
        assert user.collector_version == "aws-iam-user/0.1"
        assert user.account_id == ACCOUNT_ID
        assert user.source_id == user.arn
    assert AwsUserCollection.model_validate_json(result.model_dump_json()) == result


def test_only_a_terminal_empty_page_proves_complete_empty_listing() -> None:
    assert _collect([_page()]).status is CollectionStatus.COMPLETE
    for pages in [[], [_page(marker="missing-next")], [{}]]:
        result = _collect(pages)
        assert result.status is CollectionStatus.FAILED
        assert result.users == ()
        assert result.gaps[0].reason_code is CollectionReasonCode.MALFORMED_RESPONSE


def test_empty_intermediate_page_does_not_end_listing() -> None:
    result = _collect([_page(marker="next"), _page(_user())])
    assert result.status is CollectionStatus.COMPLETE
    assert len(result.users) == 1


def test_uncollected_attributes_and_unknown_fields_do_not_claim_absence_or_leak() -> None:
    user = _user()
    user.update(
        {"Tags": [{"Key": "secret", "Value": "sensitive-provider-detail"}], "Secret": "do-not-copy"}
    )
    result = _collect([_page(user)])
    assert result.users[0].uncollected_fields == ("tags", "permissions_boundary")
    assert "sensitive-provider-detail" not in result.model_dump_json()
    assert "do-not-copy" not in result.model_dump_json()


@pytest.mark.parametrize("allowed", ["999999999999", "123", "１２３４５６７８９０１２"])
def test_account_allowlist_is_required_and_enforced_before_listing(allowed: str) -> None:
    api = FakeApi([_page(_user())])
    if allowed == "999999999999":
        result = AwsIamUserCollector(api, allowed_account_id=allowed).collect(uuid4())
        assert result.status is CollectionStatus.FAILED
        assert result.account_id is None
        assert result.gaps[0].reason_code is CollectionReasonCode.ACCOUNT_NOT_ALLOWED
    else:
        with pytest.raises(ValueError, match="12-digit"):
            AwsIamUserCollector(api, allowed_account_id=allowed)
    assert api.list_calls == 0


@pytest.mark.parametrize(
    "identity",
    [
        {},
        [],
        {"Account": ACCOUNT_ID, "Arn": "not-an-arn"},
        {"Account": ACCOUNT_ID, "Arn": f"arn::sts::{ACCOUNT_ID}:assumed-role/Collector/test"},
        {"Account": ACCOUNT_ID, "Arn": f"arn:aws:sts:us-east-1:{ACCOUNT_ID}:assumed-role/C/test"},
    ],
)
def test_malformed_identity_fails_before_listing(identity: Any) -> None:
    api = FakeApi([_page(_user())], identity)
    result = AwsIamUserCollector(api, allowed_account_id=ACCOUNT_ID).collect(uuid4())
    assert result.status is CollectionStatus.FAILED
    assert result.gaps[0].operation == "sts:GetCallerIdentity"
    assert api.list_calls == 0


@pytest.mark.parametrize(
    ("code", "reason", "retryable"),
    [
        ("AccessDenied", CollectionReasonCode.ACCESS_DENIED, False),
        ("ExpiredToken", CollectionReasonCode.AUTHENTICATION_FAILED, False),
        ("Throttling", CollectionReasonCode.THROTTLED, True),
        ("ServiceFailure", CollectionReasonCode.SERVICE_UNAVAILABLE, True),
        ("Unknown", CollectionReasonCode.API_ERROR, False),
    ],
)
@pytest.mark.parametrize("stage", ["identity", "first_page", "later_page"])
def test_provider_failures_retain_evidence_without_claiming_completeness(
    code: str, reason: CollectionReasonCode, retryable: bool, stage: str
) -> None:
    api = FakeApi(
        [_page(_user(), marker="next"), _error(code)] if stage == "later_page" else [_error(code)],
        _error(code) if stage == "identity" else None,
    )
    result = AwsIamUserCollector(api, allowed_account_id=ACCOUNT_ID).collect(uuid4())
    assert result.status is (
        CollectionStatus.PARTIAL if stage == "later_page" else CollectionStatus.FAILED
    )
    assert len(result.users) == (1 if stage == "later_page" else 0)
    assert result.gaps[0].reason_code is reason
    assert result.gaps[0].retryable is retryable
    assert "sensitive-provider-detail" not in result.model_dump_json()


@pytest.mark.parametrize("stage", ["identity", "listing"])
def test_connection_failures_exclude_endpoint_details(stage: str) -> None:
    error = EndpointConnectionError(endpoint_url="https://sensitive-provider-detail.invalid")
    api = FakeApi([error], error if stage == "identity" else None)
    result = AwsIamUserCollector(api, allowed_account_id=ACCOUNT_ID).collect(uuid4())
    assert result.status is CollectionStatus.FAILED
    assert result.gaps[0].reason_code is CollectionReasonCode.CONNECTION_FAILED
    assert "sensitive-provider-detail" not in result.model_dump_json()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("Arn", "arn:aws:iam::999999999999:user/engineering/Example"),
        ("Arn", f"arn:aws:iam::{ACCOUNT_ID}:role/engineering/Example"),
        ("Arn", f"arn:aws-cn:iam::{ACCOUNT_ID}:user/engineering/Example"),
        ("Arn", f"arn:aws:iam:us-east-1:{ACCOUNT_ID}:user/engineering/Example"),
        ("UserName", "Different"),
        ("UserName", "invalid name"),
        ("UserId", "short"),
        ("UserId", 123),
        ("Path", "/different/"),
        ("CreateDate", NOW.replace(tzinfo=None)),
        ("CreateDate", "2026-09-25T12:00:00Z"),
        ("PasswordLastUsed", NOW.replace(tzinfo=None)),
        ("PasswordLastUsed", False),
    ],
)
def test_invalid_user_fields_produce_safe_partial_result(field: str, value: Any) -> None:
    malformed = _user()
    malformed[field] = value
    result = _collect([_page(malformed, _user("Valid"))])
    assert result.status is CollectionStatus.PARTIAL
    assert [user.user_name for user in result.users] == ["Valid"]
    assert result.gaps[0].reason_code is CollectionReasonCode.MALFORMED_RESPONSE


def test_missing_and_non_object_users_are_bounded_gaps() -> None:
    result = _collect([_page({}, None, "bad", {})])
    assert result.status is CollectionStatus.FAILED
    assert len(result.gaps) == 1


@pytest.mark.parametrize("same_id", [False, True])
def test_duplicate_arn_or_immutable_id_prevents_complete_listing(same_id: bool) -> None:
    duplicate = _user("Renamed") if same_id else _user()
    duplicate["UserId"] = _user()["UserId"]
    result = _collect([_page(_user(), marker="next"), _page(duplicate)])
    assert result.status is CollectionStatus.PARTIAL
    assert len(result.users) == 1
    assert result.gaps[0].reason_code is CollectionReasonCode.MALFORMED_RESPONSE


@pytest.mark.parametrize(
    "pages",
    [
        [None],
        [{"Users": [], "IsTruncated": "false"}],
        [{"Users": {}, "IsTruncated": False}],
        [{"Users": [], "IsTruncated": True}],
        [_page(marker="same"), _page(marker="same")],
        [_page(), _page(_user())],
    ],
)
def test_invalid_pagination_never_claims_completeness(pages: list[Any]) -> None:
    assert _collect(pages).status is CollectionStatus.FAILED


def test_page_and_user_limits_preserve_partial_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(aws_iam_users, "MAX_USERS", 1)
    result = _collect([_page(_user(), _user("Second"))])
    assert result.status is CollectionStatus.PARTIAL
    assert len(result.users) == 1
    assert result.gaps[0].reason_code is CollectionReasonCode.LIMIT_EXCEEDED
    monkeypatch.setattr(aws_iam_users, "MAX_PAGES", 1)
    result = _collect([_page(_user(), marker="next"), _page()])
    assert result.status is CollectionStatus.PARTIAL
    assert result.gaps[0].reason_code is CollectionReasonCode.LIMIT_EXCEEDED
    assert _collect([_page(_user())]).status is CollectionStatus.COMPLETE


def test_naive_clock_is_rejected_before_provider_calls() -> None:
    api = FakeApi([])
    with pytest.raises(ValueError, match="timezone"):
        AwsIamUserCollector(
            api, allowed_account_id=ACCOUNT_ID, clock=lambda: NOW.replace(tzinfo=None)
        ).collect(uuid4())


@pytest.mark.parametrize(
    "changes",
    [
        {"snapshot_id": uuid4()},
        {"account_id": "999999999999"},
        {"status": CollectionStatus.FAILED},
        {"status": CollectionStatus.PARTIAL},
        {"collector_principal_arn": None},
        {"collected_at": NOW.replace(tzinfo=None)},
    ],
)
def test_collection_envelope_rejects_inconsistent_evidence(changes: dict[str, Any]) -> None:
    values = _collect([_page(_user())]).model_dump()
    values.update(changes)
    with pytest.raises(ValidationError):
        AwsUserCollection.model_validate(values)


def test_envelope_rejects_complete_with_gaps_and_duplicate_identity() -> None:
    values = _collect([_page(_user())]).model_dump()
    values["users"] *= 2
    with pytest.raises(ValidationError, match="duplicate"):
        AwsUserCollection.model_validate(values)
    values = _collect([_error("AccessDenied")]).model_dump()
    values["status"] = CollectionStatus.COMPLETE
    with pytest.raises(ValidationError, match="complete"):
        AwsUserCollection.model_validate(values)


def test_evidence_rejects_forged_source_and_changed_coverage() -> None:
    values = _collect([_page(_user())]).users[0].model_dump()
    for updates in [
        {"source_id": "arn:aws:iam::123456789012:user/Other"},
        {"uncollected_fields": ()},
    ]:
        with pytest.raises(ValidationError):
            AwsUserEvidence.model_validate({**values, **updates})


def test_sdk_paginator_requests_every_page_without_extra_operations() -> None:
    # Explicit synthetic credentials prevent credential-chain or metadata network access.
    session = boto3.Session(
        aws_access_key_id="synthetic-access-id",
        aws_secret_access_key="synthetic-secret",  # noqa: S106
        region_name="us-east-1",
    )
    api = Boto3AwsIamApi(session)
    with Stubber(api._sts) as sts, Stubber(api._iam) as iam:
        sts.add_response(
            "get_caller_identity",
            {"Account": ACCOUNT_ID, "Arn": CALLER_ARN, "UserId": "synthetic"},
            {},
        )
        iam.add_response("list_users", _page(_user(), marker="next"), {})
        iam.add_response("list_users", _page(_user("Second")), {"Marker": "next"})
        result = AwsIamUserCollector(api, allowed_account_id=ACCOUNT_ID).collect(uuid4())
        assert result.status is CollectionStatus.COMPLETE
        assert len(result.users) == 2
        sts.assert_no_pending_responses()
        iam.assert_no_pending_responses()
