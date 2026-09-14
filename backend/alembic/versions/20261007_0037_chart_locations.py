"""Add append-only physical chart location and custody history."""

from alembic import op
import sqlalchemy as sa

revision = "20261007_0037"
down_revision = "20261006_0036"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chart_location_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.String(length=36), nullable=False),
        sa.Column("legacy_chart_tracker_key", sa.String(length=100), nullable=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("destination_type", sa.String(length=20), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("custodian_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("legacy_custodian_user_id", sa.Integer(), nullable=True),
        sa.Column("custodian_name", sa.String(length=255), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("legacy_payload", sa.JSON(), nullable=True),
        sa.UniqueConstraint("legacy_chart_tracker_key"),
    )
    for column in ("uuid", "patient_id", "destination_type", "custodian_user_id", "legacy_custodian_user_id", "occurred_at", "actor_id"):
        op.create_index(f"ix_chart_location_events_{column}", "chart_location_events", [column], unique=column == "uuid")


def downgrade():
    for column in reversed(("uuid", "patient_id", "destination_type", "custodian_user_id", "legacy_custodian_user_id", "occurred_at", "actor_id")):
        op.drop_index(f"ix_chart_location_events_{column}", table_name="chart_location_events")
    op.drop_table("chart_location_events")
