"""Bounded, deterministic changes between complete AWS role observations."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from identitymesh.collectors.aws_iam import AwsRoleEvidence
from identitymesh.normalizers.aws_iam import normalize_aws_role

MAX_COMPARISON_ROLES = 10_000
ComparedField = Literal[
    "role_name",
    "arn",
    "path",
    "created_at",
    "assume_role_policy_document",
    "description",
    "max_session_duration",
    "permissions_boundary_arn",
    "tags",
]
COMPARED_FIELDS: tuple[ComparedField, ...] = (
    "role_name",
    "arn",
    "path",
    "created_at",
    "assume_role_policy_document",
    "description",
    "max_session_duration",
    "permissions_boundary_arn",
    "tags",
)


class ComparisonError(Exception):
    """A safe failure that never turns missing evidence into removed roles."""

    def __init__(self, code: str, message: str, status_code: int = 409) -> None:
        self.reason_code = code
        self.status_code = status_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class ComparisonSource:
    """An internally validated, complete observation with a bounded role set."""

    snapshot_id: UUID
    sequence_id: int
    account_id: str
    collector_version: str
    collected_at: datetime
    roles: tuple[AwsRoleEvidence, ...]


class RoleReference(BaseModel):
    """Safe reference to evidence; raw policy, tag, and description values stay private."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    snapshot_id: UUID
    principal_id: UUID
    role_id: str
    display_name: str
    source_id: str
    collected_at: datetime

    @classmethod
    def from_role(cls, role: AwsRoleEvidence) -> "RoleReference":
        return cls(
            snapshot_id=role.snapshot_id,
            principal_id=normalize_aws_role(role).principal.principal_id,
            role_id=role.role_id,
            display_name=role.role_name,
            source_id=role.source_id,
            collected_at=role.collected_at,
        )


class RoleChange(BaseModel):
    """An observation difference, never an effective-access finding."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    principal_id: UUID
    kind: Literal["added", "removed", "changed"]
    changed_fields: tuple[ComparedField, ...] = ()
    before: RoleReference | None
    after: RoleReference | None


class ComparisonResponse(BaseModel):
    """A UUID-ordered page pinned to two explicit immutable snapshots."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.snapshot-comparison/v1"] = (
        "identitymesh.snapshot-comparison/v1"
    )
    base_snapshot_id: UUID
    target_snapshot_id: UUID
    account_id: str
    base_collected_at: datetime
    target_collected_at: datetime
    compared_fields: tuple[ComparedField, ...] = COMPARED_FIELDS
    added_count: int = Field(ge=0)
    removed_count: int = Field(ge=0)
    changed_count: int = Field(ge=0)
    unchanged_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    items: tuple[RoleChange, ...]
    next_cursor: UUID | None


def compare_sources(
    base: ComparisonSource,
    target: ComparisonSource,
    *,
    limit: int = 50,
    cursor: UUID | None = None,
) -> ComparisonResponse:
    """Compare validated sources using stable identity, ignoring observation noise."""

    if not 1 <= limit <= 100:
        raise ValueError("limit must be between 1 and 100")
    if base.sequence_id > target.sequence_id:
        raise ComparisonError(
            "COMPARISON_ORDER_INVALID", "The base must not be newer than the target."
        )
    if base.account_id != target.account_id or base.collector_version != target.collector_version:
        raise ComparisonError(
            "COMPARISON_SCOPE_MISMATCH", "Snapshots must share an account and collector version."
        )
    if max(len(base.roles), len(target.roles)) > MAX_COMPARISON_ROLES:
        raise ComparisonError(
            "COMPARISON_TOO_LARGE", "A snapshot exceeds the comparison limit.", 413
        )

    before = {normalize_aws_role(role).principal.principal_id: role for role in base.roles}
    after = {normalize_aws_role(role).principal.principal_id: role for role in target.roles}
    if len(before) != len(base.roles) or len(after) != len(target.roles):
        raise ComparisonError("COMPARISON_SOURCE_INVALID", "Duplicate role identity detected.", 503)
    changes: list[RoleChange] = []
    counts = {"added": 0, "removed": 0, "changed": 0, "unchanged": 0}
    for principal_id in sorted(before.keys() | after.keys()):
        old = before.get(principal_id)
        new = after.get(principal_id)
        fields: tuple[ComparedField, ...] = ()
        kind: Literal["added", "removed", "changed"]
        if old is None:
            kind = "added"
        elif new is None:
            kind = "removed"
        else:
            changed_fields: list[ComparedField] = []
            for field in COMPARED_FIELDS:
                old_value, new_value = getattr(old, field), getattr(new, field)
                if field == "assume_role_policy_document":
                    # Python equality collapses JSON booleans and numbers (True == 1).
                    old_value = json.dumps(old_value, sort_keys=True)
                    new_value = json.dumps(new_value, sort_keys=True)
                if old_value != new_value:
                    changed_fields.append(field)
            fields = tuple(changed_fields)
            if not fields:
                counts["unchanged"] += 1
                continue
            kind = "changed"
        counts[kind] += 1
        if cursor is None or principal_id > cursor:
            # Counts cover the whole comparison; only the next page is materialized.
            if len(changes) <= limit:
                changes.append(
                    RoleChange(
                        principal_id=principal_id,
                        kind=kind,
                        changed_fields=fields,
                        before=RoleReference.from_role(old) if old else None,
                        after=RoleReference.from_role(new) if new else None,
                    )
                )
    page = tuple(changes[:limit])
    return ComparisonResponse(
        base_snapshot_id=base.snapshot_id,
        target_snapshot_id=target.snapshot_id,
        account_id=base.account_id,
        base_collected_at=base.collected_at,
        target_collected_at=target.collected_at,
        added_count=counts["added"],
        removed_count=counts["removed"],
        changed_count=counts["changed"],
        unchanged_count=counts["unchanged"],
        total_count=counts["added"] + counts["removed"] + counts["changed"],
        items=page,
        next_cursor=page[-1].principal_id if len(changes) > limit else None,
    )
