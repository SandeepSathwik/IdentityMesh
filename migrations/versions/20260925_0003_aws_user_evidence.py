"""Add independent IAM user collection attempts and gaps."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260925_0003"
down_revision: str | None = "20260915_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "aws_iam_user_collection_attempts",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("schema_version", sa.String(length=128), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("account_id", sa.String(length=12), nullable=True),
        sa.Column("collector_principal_arn", sa.String(length=2048), nullable=True),
        sa.Column("user_count", sa.Integer(), nullable=False),
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
            name="ck_aws_user_attempt_status",
        ),
        sa.CheckConstraint(
            "account_id IS NULL OR account_id ~ '^[0-9]{12}$'",
            name="ck_aws_user_attempt_account_id",
        ),
        sa.CheckConstraint(
            "(account_id IS NULL) = (collector_principal_arn IS NULL)",
            name="ck_aws_user_attempt_identity_pair",
        ),
        sa.CheckConstraint(
            "status = 'failed' OR account_id IS NOT NULL",
            name="ck_aws_user_attempt_identity_required",
        ),
        sa.CheckConstraint(
            "(status = 'complete' AND gap_count = 0) OR "
            "(status = 'partial' AND user_count > 0 AND gap_count > 0) OR "
            "(status = 'failed' AND user_count = 0 AND gap_count > 0)",
            name="ck_aws_user_attempt_counts",
        ),
        sa.CheckConstraint(
            "user_count >= 0 AND gap_count >= 0",
            name="ck_aws_user_attempt_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_aws_user_attempt_digest",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.snapshot_id"],
            name="fk_aws_user_attempt_snapshot",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("snapshot_id", name="pk_aws_user_collection_attempts"),
    )

    op.create_table(
        "aws_iam_user_collection_gaps",
        sa.Column("gap_id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("message", sa.String(length=200), nullable=False),
        sa.CheckConstraint(
            "length(btrim(operation)) > 0",
            name="ck_aws_user_gap_operation_nonempty",
        ),
        sa.CheckConstraint(
            "reason_code ~ '^[A-Z][A-Z0-9_]{0,63}$'",
            name="ck_aws_user_gap_reason_code",
        ),
        sa.CheckConstraint(
            "length(btrim(message)) > 0",
            name="ck_aws_user_gap_message_nonempty",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["aws_iam_user_collection_attempts.snapshot_id"],
            name="fk_aws_user_gap_attempt",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("gap_id", name="pk_aws_iam_user_collection_gaps"),
        sa.UniqueConstraint(
            "snapshot_id",
            "operation",
            "reason_code",
            name="uq_aws_user_gap_snapshot_operation_reason",
        ),
    )


def downgrade() -> None:
    # Shared evidence/principal records must not outlive the attempt describing their scope.
    if (
        op.get_bind()
        .execute(sa.text("SELECT EXISTS (SELECT 1 FROM aws_iam_user_collection_attempts)"))
        .scalar()
    ):
        raise RuntimeError("cannot downgrade while IAM user collection evidence is retained")
    op.drop_table("aws_iam_user_collection_gaps")
    op.drop_table("aws_iam_user_collection_attempts")
