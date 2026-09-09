"""Normalize validated AWS IAM evidence without deriving access conclusions."""

from typing import Literal
from uuid import UUID, uuid5

from pydantic import BaseModel, ConfigDict

from identitymesh.collectors.aws_iam import AwsRoleEvidence
from identitymesh.principals import (
    EvidenceClassification,
    Principal,
    PrincipalProvenance,
    PrincipalType,
)

# This namespace is a permanent part of the principal identity contract. Changing it would
# change every derived principal identifier and therefore requires an explicit migration.
PRINCIPAL_ID_NAMESPACE = UUID("7b0f9491-6b56-5d20-a91a-0f43a2d751f8")

AwsRoleDeferredField = Literal[
    "path",
    "assume_role_policy_document",
    "description",
    "max_session_duration",
    "permissions_boundary_arn",
    "tags",
    "last_used_at",
    "last_used_region",
]

_DEFERRED_EVIDENCE_FIELDS: tuple[AwsRoleDeferredField, ...] = (
    "path",
    "assume_role_policy_document",
    "description",
    "max_session_duration",
    "permissions_boundary_arn",
    "tags",
    "last_used_at",
    "last_used_region",
)


class AwsRoleNormalization(BaseModel):
    """Normalized principal plus evidence fields reserved for later models."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    principal: Principal
    deferred_evidence_fields: tuple[AwsRoleDeferredField, ...]


def normalize_aws_role(evidence: AwsRoleEvidence) -> AwsRoleNormalization:
    """Map one validated AWS role fact to a stable, observed principal."""

    if not isinstance(evidence, AwsRoleEvidence):
        raise TypeError("evidence must be validated AwsRoleEvidence")

    identity_key = f"aws:{evidence.account_id}:iam-role:{evidence.role_id}"
    principal = Principal(
        principal_id=uuid5(PRINCIPAL_ID_NAMESPACE, identity_key),
        external_id=evidence.role_id,
        provider=evidence.provider,
        principal_type=PrincipalType.CLOUD_ROLE,
        display_name=evidence.role_name,
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
    return AwsRoleNormalization(
        principal=principal,
        deferred_evidence_fields=_DEFERRED_EVIDENCE_FIELDS,
    )
