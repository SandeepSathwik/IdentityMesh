"""Persist AWS IAM role collections and normalized principals."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260915_0002"
down_revision: str | None = "20260909_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aws_iam_role_collection_attempts",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=128), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=12), nullable=True),
        sa.Column("collector_principal_arn", sa.String(length=2048), nullable=True),
        sa.Column("role_count", sa.Integer(), nullable=False),
        sa.Column("gap_count", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "persisted_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('complete', 'partial', 'failed')",
            name="ck_aws_role_attempt_status",
        ),
        sa.CheckConstraint(
            "account_id IS NULL OR account_id ~ '^[0-9]{12}$'",
            name="ck_aws_role_attempt_account_id",
        ),
        sa.CheckConstraint(
            "(account_id IS NULL) = (collector_principal_arn IS NULL)",
            name="ck_aws_role_attempt_identity_pair",
        ),
        sa.CheckConstraint(
            "status = 'failed' OR account_id IS NOT NULL",
            name="ck_aws_role_attempt_identity_required",
        ),
        sa.CheckConstraint(
            "(status = 'complete' AND gap_count = 0) OR "
            "(status = 'partial' AND role_count > 0 AND gap_count > 0) OR "
            "(status = 'failed' AND role_count = 0 AND gap_count > 0)",
            name="ck_aws_role_attempt_counts",
        ),
        sa.CheckConstraint(
            "role_count >= 0 AND gap_count >= 0",
            name="ck_aws_role_attempt_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_aws_role_attempt_digest",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.snapshot_id"],
            name="fk_aws_role_attempt_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("snapshot_id", name="pk_aws_role_collection_attempts"),
    )

    op.create_table(
        "aws_iam_role_collection_gaps",
        sa.Column("gap_id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("message", sa.String(length=200), nullable=False),
        sa.CheckConstraint(
            "length(btrim(operation)) > 0",
            name="ck_aws_role_gap_operation_nonempty",
        ),
        sa.CheckConstraint(
            "reason_code ~ '^[A-Z][A-Z0-9_]{0,63}$'",
            name="ck_aws_role_gap_reason_code",
        ),
        sa.CheckConstraint(
            "length(btrim(message)) > 0",
            name="ck_aws_role_gap_message_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["aws_iam_role_collection_attempts.snapshot_id"],
            name="fk_aws_role_gap_attempt",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("gap_id", name="pk_aws_iam_role_collection_gaps"),
        sa.UniqueConstraint(
            "snapshot_id",
            "operation",
            "reason_code",
            name="uq_aws_role_gap_snapshot_operation_reason",
        ),
    )

    op.create_table(
        "provider_evidence",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("object_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=2048), nullable=False),
        sa.Column("schema_version", sa.String(length=128), nullable=False),
        sa.Column("provider_object_id", sa.String(length=2048), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collector_version", sa.String(length=128), nullable=False),
        sa.Column("collector_principal_id", sa.String(length=2048), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint(
            "length(btrim(provider)) > 0",
            name="ck_provider_evidence_provider_nonempty",
        ),
        sa.CheckConstraint(
            "length(btrim(object_type)) > 0",
            name="ck_provider_evidence_object_type_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.snapshot_id"],
            name="fk_provider_evidence_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "snapshot_id",
            "provider",
            "source_id",
            name="pk_provider_evidence",
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "provider",
            "object_type",
            "provider_object_id",
            name="uq_provider_evidence_snapshot_object_id",
        ),
    )

    op.create_table(
        "principals",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("principal_type", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=2048), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=False),
        sa.Column("evidence_source_id", sa.String(length=2048), nullable=False),
        sa.Column("principal", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.CheckConstraint("length(btrim(provider)) > 0", name="ck_principals_provider_nonempty"),
        sa.CheckConstraint(
            "length(btrim(principal_type)) > 0",
            name="ck_principals_type_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "provider", "evidence_source_id"],
            [
                "provider_evidence.snapshot_id",
                "provider_evidence.provider",
                "provider_evidence.source_id",
            ],
            name="fk_principals_provider_evidence",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("snapshot_id", "principal_id", name="pk_principals"),
        sa.UniqueConstraint(
            "snapshot_id",
            "provider",
            "external_id",
            name="uq_principals_snapshot_provider_external_id",
        ),
    )
    op.create_index(
        "ix_principals_snapshot_type",
        "principals",
        ["snapshot_id", "principal_type"],
    )


def downgrade() -> None:
    op.drop_index("ix_principals_snapshot_type", table_name="principals")
    op.drop_table("principals")
    op.drop_table("provider_evidence")
    op.drop_table("aws_iam_role_collection_gaps")
    op.drop_table("aws_iam_role_collection_attempts")
