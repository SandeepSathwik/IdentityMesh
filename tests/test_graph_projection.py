from datetime import datetime, timezone
from uuid import UUID, uuid4

from identitymesh.graph_projection import (
    PROJECTION_VERSION,
    _canonical_digest,
    _node_properties,
    project_principal,
)
from identitymesh.principals import (
    EvidenceClassification,
    Principal,
    PrincipalProvenance,
    PrincipalType,
)

NOW = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _principal(snapshot_id: UUID, name: str = "ApplicationRole") -> Principal:
    return Principal(
        principal_id=uuid4(),
        external_id=f"arn:aws:iam::123456789012:role/{name}",
        provider="aws",
        principal_type=PrincipalType.CLOUD_ROLE,
        display_name=name,
        created_at=NOW,
        discovered_at=NOW,
        provenance=PrincipalProvenance(
            source_system="aws",
            source_object_type="iam_role",
            source_object_id=f"arn:aws:iam::123456789012:role/{name}",
            snapshot_id=snapshot_id,
            collected_at=NOW,
            collector_version="aws-iam-role/0.1",
            collector_principal_id=(
                "arn:aws:sts::123456789012:assumed-role/IdentityMeshCollector/run"
            ),
            evidence_schema_version="aws.iam.role/v1",
            classification=EvidenceClassification.OBSERVED,
        ),
    )


def test_projects_only_normalized_observed_principal_properties() -> None:
    snapshot_id = uuid4()
    projected = project_principal(_principal(snapshot_id))
    properties = _node_properties(projected)

    assert projected.snapshot_id == snapshot_id
    assert projected.projection_version == PROJECTION_VERSION
    assert projected.evidence_classification == "observed"
    assert properties["projection_key"].startswith(f"{snapshot_id}:{PROJECTION_VERSION}:")
    assert "assume_role_policy_document" not in properties
    assert "permissions_boundary_arn" not in properties
    assert "tags" not in properties


def test_projection_digest_is_order_independent_and_content_sensitive() -> None:
    snapshot_id = uuid4()
    first = _node_properties(project_principal(_principal(snapshot_id, "First")))
    second = _node_properties(project_principal(_principal(snapshot_id, "Second")))

    expected = _canonical_digest([first, second])

    assert _canonical_digest([second, first]) == expected
    second["display_name"] = "Changed"
    assert _canonical_digest([first, second]) != expected


def test_empty_projection_has_deterministic_digest() -> None:
    assert _canonical_digest([]) == _canonical_digest([])
