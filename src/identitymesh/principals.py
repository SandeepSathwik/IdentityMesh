"""Provider-neutral principal contracts."""

from datetime import datetime
from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class PrincipalType(str, Enum):
    """Supported normalized principal classifications."""

    CLOUD_ROLE = "cloud_role"


class EvidenceClassification(str, Enum):
    """How a normalized record relates to its source evidence."""

    OBSERVED = "observed"


class PrincipalProvenance(BaseModel):
    """Trace a normalized principal back to validated provider evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    source_system: str = Field(min_length=1, max_length=64)
    source_object_type: str = Field(min_length=1, max_length=64)
    source_object_id: str = Field(min_length=1, max_length=2048)
    snapshot_id: UUID
    collected_at: datetime
    collector_version: str = Field(pattern=r"^[A-Za-z0-9._/+\-]{1,128}$")
    collector_principal_id: str = Field(min_length=1, max_length=2048)
    evidence_schema_version: str = Field(min_length=1, max_length=128)
    classification: EvidenceClassification

    @field_validator("collected_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("collected_at must include a timezone")
        return value


class Principal(BaseModel):
    """A normalized actor capable of receiving or exercising authority."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["identitymesh.principal/v1"] = "identitymesh.principal/v1"
    principal_id: UUID
    external_id: str = Field(min_length=1, max_length=2048)
    provider: str = Field(min_length=1, max_length=64)
    principal_type: PrincipalType
    display_name: str = Field(min_length=1, max_length=256)
    status: str | None = Field(default=None, min_length=1, max_length=64)
    created_at: datetime | None = None
    discovered_at: datetime
    provenance: PrincipalProvenance

    @field_validator("created_at", "discovered_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("principal timestamps must include a timezone")
        return value
