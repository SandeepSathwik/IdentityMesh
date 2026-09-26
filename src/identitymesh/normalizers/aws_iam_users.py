"""Normalize IAM user observations without inferring ownership or credential state."""

from typing import Literal
from uuid import uuid5

from pydantic import BaseModel, ConfigDict

from identitymesh.collectors.aws_iam_users import AwsUserEvidence
from identitymesh.normalizers.aws_iam import PRINCIPAL_ID_NAMESPACE
from identitymesh.principals import (
    EvidenceClassification,
    Principal,
    PrincipalProvenance,
    PrincipalType,
)


class AwsUserNormalization(BaseModel):
    """Observed cloud user and attributes retained only in provider evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    principal: Principal
    deferred_evidence_fields: tuple[
        Literal["path"], Literal["password_last_used"], Literal["uncollected_fields"]
    ] = ("path", "password_last_used", "uncollected_fields")


def normalize_aws_user(evidence: AwsUserEvidence) -> AwsUserNormalization:
    if not isinstance(evidence, AwsUserEvidence):
        raise TypeError("evidence must be validated AwsUserEvidence")
    # Include the partition: equal account/user identifiers in separate partitions cannot alias.
    partition = evidence.arn.split(":", 5)[1]
    identity_key = f"aws:{partition}:{evidence.account_id}:iam-user:{evidence.user_id}"
    return AwsUserNormalization(
        principal=Principal(
            principal_id=uuid5(PRINCIPAL_ID_NAMESPACE, identity_key),
            external_id=evidence.user_id,
            provider=evidence.provider,
            principal_type=PrincipalType.CLOUD_USER,
            display_name=evidence.user_name,
            status=None,
            created_at=evidence.created_at,
            discovered_at=evidence.collected_at,
            provenance=PrincipalProvenance(
                source_system=evidence.provider,
                source_object_type=evidence.object_type,
                source_object_id=evidence.source_id,
                snapshot_id=evidence.snapshot_id,
                collected_at=evidence.collected_at,
                collector_version=evidence.collector_version,
                collector_principal_id=evidence.collector_principal_arn,
                evidence_schema_version=evidence.schema_version,
                classification=EvidenceClassification.OBSERVED,
            ),
        )
    )
