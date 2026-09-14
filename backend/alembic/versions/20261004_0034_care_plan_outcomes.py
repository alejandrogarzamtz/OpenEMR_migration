"""Add append-only care-plan progress and outcomes."""
from alembic import op
import sqlalchemy as sa

revision = "20261004_0034"
down_revision = "20261003_0033"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "care_plan_outcomes", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("care_plan_id",sa.Integer(),sa.ForeignKey("care_plans.id"),nullable=False), sa.Column("event_type",sa.String(20),nullable=False),
        sa.Column("plan_status",sa.String(32),nullable=True), sa.Column("achievement_status",sa.String(32),nullable=True),
        sa.Column("measure_code",sa.String(100),nullable=True), sa.Column("measure_system",sa.String(255),nullable=True), sa.Column("measure_display",sa.String(255),nullable=True),
        sa.Column("value_numeric",sa.Numeric(18,6),nullable=True), sa.Column("value_unit",sa.String(50),nullable=True), sa.Column("note",sa.Text(),nullable=True),
        sa.Column("recorded_at",sa.DateTime(timezone=True),nullable=False), sa.Column("recorded_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("source",sa.String(30),nullable=False,server_default="staff"), sa.Column("legacy_payload",sa.JSON(),nullable=True), sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),
    )
    for column in ("uuid","care_plan_id","event_type","plan_status","achievement_status","recorded_at"):op.create_index(f"ix_care_plan_outcomes_{column}","care_plan_outcomes",[column],unique=column=="uuid")


def downgrade():
    op.drop_table("care_plan_outcomes")
