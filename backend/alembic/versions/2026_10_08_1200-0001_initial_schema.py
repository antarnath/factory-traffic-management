"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-10-08 12:00:00.000000

Creates the six tables required by the factory traffic-management system:
    junction, junction_config, signal, queue_entry, pending_command, audit_event
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "junction",
        sa.Column("id", sa.String(length=16), primary_key=True),
        sa.Column("name", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("mode", sa.String(length=16), nullable=False, server_default="AUTOMATIC"),
        sa.Column("phase", sa.String(length=16), nullable=False, server_default="ALL_RED"),
        sa.Column("controller_status", sa.String(length=16), nullable=False, server_default="UNKNOWN"),
        sa.Column("manual_override_dir", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("manual_override_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("emergency_dir", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "junction_config",
        sa.Column("junction_id", sa.String(length=16),
                  sa.ForeignKey("junction.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("green_duration_sec", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("yellow_duration_sec", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("all_red_duration_sec", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("min_green_sec", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("starvation_threshold_sec", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("phases_json", sa.JSON(), nullable=False, server_default="[]"),
    )

    op.create_table(
        "signal",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("junction_id", sa.String(length=16),
                  sa.ForeignKey("junction.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("desired_state", sa.String(length=8), nullable=False, server_default="RED"),
        sa.Column("actual_state", sa.String(length=8), nullable=False, server_default="RED"),
        sa.Column("last_known_good", sa.String(length=8), nullable=False, server_default="RED"),
        sa.Column("last_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("junction_id", "direction", name="uq_signal_junction_dir"),
    )
    op.create_index("ix_signal_junction_id", "signal", ["junction_id"])

    op.create_table(
        "queue_entry",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("junction_id", sa.String(length=16),
                  sa.ForeignKey("junction.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("vehicle_type", sa.String(length=16), nullable=False),
        sa.Column("vehicle_id", sa.String(length=64), nullable=False, server_default=""),
        sa.Column("arrived_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False, unique=True),
        sa.Column("sequence_no", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cleared", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_queue_junction_dir_cleared", "queue_entry",
                    ["junction_id", "direction", "cleared"])

    op.create_table(
        "pending_command",
        sa.Column("command_id", sa.String(length=64), primary_key=True),
        sa.Column("junction_id", sa.String(length=16),
                  sa.ForeignKey("junction.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("requested_state", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="PENDING"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ack_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_cmd_junction_status", "pending_command", ["junction_id", "status"])

    op.create_table(
        "audit_event",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("junction_id", sa.String(length=16),
                  sa.ForeignKey("junction.id", ondelete="CASCADE"), nullable=True),
        sa.Column("direction", sa.String(length=8), nullable=False, server_default=""),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_junction_ts", "audit_event", ["junction_id", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_audit_junction_ts", table_name="audit_event")
    op.drop_table("audit_event")

    op.drop_index("ix_cmd_junction_status", table_name="pending_command")
    op.drop_table("pending_command")

    op.drop_index("ix_queue_junction_dir_cleared", table_name="queue_entry")
    op.drop_table("queue_entry")

    op.drop_index("ix_signal_junction_id", table_name="signal")
    op.drop_table("signal")

    op.drop_table("junction_config")
    op.drop_table("junction")
