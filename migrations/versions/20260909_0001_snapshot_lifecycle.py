"""Create the authoritative snapshot lifecycle tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260909_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "snapshots",
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column(
            "sequence_id",
            sa.BigInteger(),
            sa.Identity(always=True),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("collector_version", sa.String(length=128), nullable=False),
        sa.Column("projection_version", sa.String(length=128), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("projection_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('collecting', 'collected', 'projecting', 'ready', 'failed')",
            name="ck_snapshots_status",
        ),
        sa.CheckConstraint(
            "length(btrim(collector_version)) > 0",
            name="ck_snapshots_collector_version_nonempty",
        ),
        sa.CheckConstraint(
            "projection_version IS NULL OR length(btrim(projection_version)) > 0",
            name="ck_snapshots_projection_version_nonempty",
        ),
        sa.CheckConstraint(
            "failure_code IS NULL OR failure_code ~ '^[A-Z][A-Z0-9_]{0,63}$'",
            name="ck_snapshots_failure_code_format",
        ),
        sa.CheckConstraint(
            "(status = 'collecting' AND collected_at IS NULL "
            "AND projection_started_at IS NULL AND ready_at IS NULL AND failed_at IS NULL "
            "AND projection_version IS NULL AND failure_code IS NULL) OR "
            "(status = 'collected' AND collected_at IS NOT NULL "
            "AND projection_started_at IS NULL AND ready_at IS NULL AND failed_at IS NULL "
            "AND projection_version IS NULL AND failure_code IS NULL) OR "
            "(status = 'projecting' AND collected_at IS NOT NULL "
            "AND projection_started_at IS NOT NULL AND ready_at IS NULL AND failed_at IS NULL "
            "AND projection_version IS NOT NULL AND failure_code IS NULL) OR "
            "(status = 'ready' AND collected_at IS NOT NULL "
            "AND projection_started_at IS NOT NULL AND ready_at IS NOT NULL AND failed_at IS NULL "
            "AND projection_version IS NOT NULL AND failure_code IS NULL) OR "
            "(status = 'failed' AND ready_at IS NULL AND failed_at IS NOT NULL "
            "AND failure_code IS NOT NULL)",
            name="ck_snapshots_state_fields",
        ),
        sa.PrimaryKeyConstraint("snapshot_id", name="pk_snapshots"),
        sa.UniqueConstraint("sequence_id", name="uq_snapshots_sequence_id"),
    )
    op.create_index("ix_snapshots_status_sequence", "snapshots", ["status", "sequence_id"])

    op.create_table(
        "active_snapshot",
        sa.Column("singleton", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("singleton", name="ck_active_snapshot_singleton"),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["snapshots.snapshot_id"],
            name="fk_active_snapshot_snapshot_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("singleton", name="pk_active_snapshot"),
        sa.CheckConstraint(
            "(snapshot_id IS NULL AND activated_at IS NULL) OR "
            "(snapshot_id IS NOT NULL AND activated_at IS NOT NULL)",
            name="ck_active_snapshot_fields",
        ),
    )
    op.execute(sa.text("INSERT INTO active_snapshot (singleton) VALUES (TRUE)"))


def downgrade() -> None:
    op.drop_table("active_snapshot")
    op.drop_index("ix_snapshots_status_sequence", table_name="snapshots")
    op.drop_table("snapshots")
