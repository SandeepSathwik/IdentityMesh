from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from identitymesh.collectors.aws_iam import AwsRoleEvidence
from identitymesh.normalizers.aws_iam import normalize_aws_role
from identitymesh.principals import EvidenceClassification, Principal, PrincipalType

NOW = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
ACCOUNT_ID = "123456789012"
ROLE_ID = "AROABCDEFGHIJKLMNOP"
ROLE_ARN = f"arn:aws:iam::{ACCOUNT_ID}:role/application/ApplicationRole"
CALLER_ARN = f"arn:aws:sts::{ACCOUNT_ID}:assumed-role/IdentityMeshCollector/run"


def _evidence(**changes: object) -> AwsRoleEvidence:
    values: dict[str, object] = {
        "snapshot_id": uuid4(),
        "source_id": ROLE_ARN,
        "account_id": ACCOUNT_ID,
        "collector_principal_arn": CALLER_ARN,
        "collected_at": NOW,
        "collector_version": "aws-iam-role/0.1",
        "role_id": ROLE_ID,
        "role_name": "ApplicationRole",
        "arn": ROLE_ARN,
        "path": "/application/",
        "created_at": NOW,
        "assume_role_policy_document": {"Version": "2012-10-17", "Statement": []},
        "description": "Synthetic application role",
        "max_session_duration": 3600,
        "permissions_boundary_arn": f"arn:aws:iam::{ACCOUNT_ID}:policy/Boundary",
        "tags": {"Environment": "test"},
        "last_used_at": NOW,
        "last_used_region": "us-east-1",
    }
    values.update(changes)
    return AwsRoleEvidence.model_validate(values)


def test_normalizes_role_to_observed_cloud_principal_with_provenance() -> None:
    evidence = _evidence()

    result = normalize_aws_role(evidence)

    assert result.principal.schema_version == "identitymesh.principal/v1"
    assert result.principal.external_id == ROLE_ID
    assert result.principal.provider == "aws"
    assert result.principal.principal_type is PrincipalType.CLOUD_ROLE
    assert result.principal.display_name == "ApplicationRole"
    assert result.principal.status is None
    assert result.principal.created_at == NOW
    assert result.principal.discovered_at == NOW
    assert result.principal.provenance.snapshot_id == evidence.snapshot_id
    assert result.principal.provenance.source_object_id == ROLE_ARN
    assert result.principal.provenance.collector_principal_id == CALLER_ARN
    assert result.principal.provenance.classification is EvidenceClassification.OBSERVED


def test_principal_identity_is_stable_across_snapshots() -> None:
    first = normalize_aws_role(_evidence()).principal
    second = normalize_aws_role(_evidence(snapshot_id=uuid4())).principal

    assert first.principal_id == second.principal_id
    assert first.provenance.snapshot_id != second.provenance.snapshot_id


def test_recreated_role_at_same_arn_receives_a_different_principal_identity() -> None:
    first = normalize_aws_role(_evidence()).principal
    second = normalize_aws_role(_evidence(role_id="ARODIFFERENTIDENTITY")).principal

    assert first.principal_id != second.principal_id


def test_reports_provider_fields_deferred_from_the_principal_contract() -> None:
    result = normalize_aws_role(_evidence())

    assert "assume_role_policy_document" in result.deferred_evidence_fields
    assert "permissions_boundary_arn" in result.deferred_evidence_fields
    assert "tags" in result.deferred_evidence_fields


def test_normalizer_rejects_unvalidated_input() -> None:
    with pytest.raises(TypeError, match="validated AwsRoleEvidence"):
        normalize_aws_role({"role_id": ROLE_ID})  # type: ignore[arg-type]


def test_principal_contract_rejects_naive_discovery_timestamp() -> None:
    principal = normalize_aws_role(_evidence()).principal

    with pytest.raises(ValidationError, match="timestamps must include a timezone"):
        Principal.model_validate(
            {
                **principal.model_dump(),
                "discovered_at": datetime(2026, 9, 9, 12, 0),
            }
        )
